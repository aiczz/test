"""首页的「每日一次」AI 增强层。

【这一层解决什么问题】
首页推荐要同时满足：
  · 同一地区、同一天，所有人看到的完全一样  → 排序与文案必须是 (地区, 日期) 的函数
  · 不同天不一样                            → 日期参与排序与生成
  · 不能每个用户、每次刷新都调一次大模型    → 一个地区一天只调一次，落库复用

所以这里把「问 AI」这件事收敛成一个纯函数：
    key = home:{地区}:{日期}:{季节}:{天气}
命中缓存就直接返回；没命中才真的发一次请求，然后把结果写回缓存。

【为什么候选筛选不带上用户的忌口】
如果候选集因人而异，缓存就没法共享，token 也就省不下来。
所以这一层只做「地区级」的通用推荐（时令 + 天气 + 大众营养），
用户的忌口/限钠在 home_service 里**之后再执行**——安全性不依赖 AI，
也不依赖缓存，永远由确定性代码兜底。
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.ai import client
from app.core.config import settings
from app.models.ai_cache import AiDailyCache
from app.repositories.catalog_insight_repository import (
    dish_insights,
    food_insights,
    seasonal_knowledge,
)
from app.services import scoring_service
from app.services.scoring_service import ScoredItem
from app.services.weather_service import WeatherContext

logger = logging.getLogger(__name__)

# 同一进程内串行化「检查缓存 → 调 AI → 写缓存」，
# 避免并发请求同时 miss 缓存、各调一次模型（token 翻倍）。
_generate_lock = threading.Lock()

_SYSTEM_PROMPT = """你是「食时」App 的时令饮食助手，服务中国家庭的一日三餐。

铁律：
1. 你只能从用户提供的「候选食材」「候选菜品」清单里挑选，**绝对不许**新增清单之外的
   任何食材或菜名。清单之外的 id 会被系统直接丢弃。
2. 所有关于时令、营养、功效的说法，必须以给出的「时令知识」和候选自带的营养/标签为依据，
   不要引入你自己记忆里没有依据的说法。
3. 只输出 JSON，不要输出任何解释性文字或 Markdown 围栏。
"""


@dataclass(slots=True)
class HomeEnhancement:
    """首页的 AI 增强结果。"""

    tip_title: str
    tip_body: str
    food_picks: list[int] = field(default_factory=list)
    dish_picks: list[int] = field(default_factory=list)
    food_notes: dict[int, str] = field(default_factory=dict)
    dish_notes: dict[int, str] = field(default_factory=dict)
    # ai = 这次真的调了模型；cached = 命中当天缓存；algorithm = 没配 AI / 调用失败
    source: str = "algorithm"
    model: str = ""
    elapsed_ms: int = 0
    cache_key: str = ""
    error: str | None = None


# =====================================================================
# 缓存读写
# =====================================================================


# 缓存配方版本。**改提示词、改打分算法、或者换内容目录时把它 +1** ——
# 否则部署后 36 小时内还会命中旧代码生成的推荐（候选集和文案都对不上了）。
# 带上版本号，一次部署就能让旧缓存自然失效，不用手工清库。
#
# ★ v6：换成精选目录（10000 道 → 700 道）。
#   这次比改算法更要紧的原因是：缓存里存的是**菜谱 id**，
#   而换目录之后 id 会被重新占用 —— 旧缓存里的 id 可能指向完全不同的菜。
#   不失效的话，首页会出现「缓存里是 A、显示出来是 B」这种鬼故事。
CACHE_RECIPE_VERSION = "v6"


def build_cache_key(
    *, region: str, date_key: str, month: int, weather: WeatherContext
) -> str:
    return (
        f"home:{CACHE_RECIPE_VERSION}:{region}:{date_key}"
        f":{scoring_service.season_char_of(month)}"
        f":{weather.kind}:{settings.ai_model}"
    )


def _read_cache(session: Session, key: str) -> dict | None:
    if not settings.ai_daily_cache_enabled:
        return None
    try:
        row = session.exec(select(AiDailyCache).where(AiDailyCache.key == key)).first()
    except Exception as exc:  # noqa: BLE001 —— 缓存表还没建好也不能让首页挂
        logger.warning("读 AI 缓存失败：%s", exc)
        return None
    if row is None:
        return None
    if row.expires_at and row.expires_at < datetime.utcnow():
        return None
    try:
        return json.loads(row.payload)
    except (json.JSONDecodeError, TypeError):
        return None


def _write_cache(session: Session, key: str, payload: dict, model: str) -> None:
    if not settings.ai_daily_cache_enabled:
        return
    try:
        row = session.exec(select(AiDailyCache).where(AiDailyCache.key == key)).first()
        # 存 36 小时：跨过当天就够了，key 里的日期保证不会串天
        expires_at = datetime.utcnow() + timedelta(hours=36)
        encoded = json.dumps(payload, ensure_ascii=False)
        if row is None:
            session.add(
                AiDailyCache(
                    key=key, payload=encoded, model=model, expires_at=expires_at
                )
            )
        else:
            row.payload = encoded
            row.model = model
            row.expires_at = expires_at
            session.add(row)
        session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("写 AI 缓存失败：%s", exc)
        session.rollback()


# =====================================================================
# 提示词
# =====================================================================


def _food_lines(session: Session, items: list[ScoredItem]) -> list[str]:
    insights = food_insights(session, [item.item_id for item in items])
    lines: list[str] = []
    for item in items:
        insight = insights.get(item.item_id)
        if insight is None:
            lines.append(f"{item.item_id} | {item.name}")
            continue
        nutrition = "、".join(
            part
            for part in (
                f"能量{round(insight.energy_kcal)}kcal/100g"
                if insight.energy_kcal is not None
                else "",
                f"蛋白{insight.protein:g}g" if insight.protein is not None else "",
                f"钠{round(insight.na_mg)}mg" if insight.na_mg is not None else "",
            )
            if part
        )
        effects = "、".join(insight.tags[:4]) or "—"
        lines.append(
            f"{item.item_id} | {item.name} | {insight.category} | "
            f"{nutrition or '营养数据暂无'} | 功效：{effects}"
        )
    return lines


def _dish_lines(session: Session, items: list[ScoredItem]) -> list[str]:
    insights = dish_insights(session, [item.item_id for item in items])
    lines: list[str] = []
    for item in items:
        insight = insights.get(item.item_id)
        if insight is None:
            lines.append(f"{item.item_id} | {item.name}")
            continue
        nutrition = "、".join(
            part
            for part in (
                f"能量{round(insight.energy_kcal)}kcal"
                if insight.energy_kcal is not None
                else "",
                f"蛋白{insight.protein_g:g}g"
                if insight.protein_g is not None
                else "",
                f"钠{round(insight.na_mg)}mg" if insight.na_mg is not None else "",
            )
            if part
        )
        mains = "、".join(insight.main_ingredients[:5]) or "—"
        lines.append(
            f"{item.item_id} | {item.name} | 标签：{'、'.join(insight.tags[:4]) or '—'} | "
            f"{nutrition or '营养数据暂无'} | 主要食材：{mains}"
        )
    return lines


def _build_messages(
    session: Session,
    *,
    region: str,
    date_key: str,
    month: int,
    weather: WeatherContext,
    foods: list[ScoredItem],
    dishes: list[ScoredItem],
) -> list[dict[str, str]]:
    facts = seasonal_knowledge(
        session, month=month, season=scoring_service.season_char_of(month)
    )
    fact_lines = "\n".join(f"- {fact}" for fact in facts) or "- （本库暂无该月时令知识条目）"

    user_prompt = f"""【今天】{date_key}，{region}，{month} 月（{scoring_service.season_char_of(month)}季）
【天气】{weather.description} —— {weather.advice}
【时令知识 · 来自我们的时令数据库】
{fact_lines}

【候选食材】（id | 名称 | 类别 | 营养 | 功效）
{chr(10).join(_food_lines(session, foods)) or "（无）"}

【候选菜品】（id | 菜名 | 标签 | 整菜营养 | 主要食材）
{chr(10).join(_dish_lines(session, dishes)) or "（无）"}

请从中挑出今天最合适的食材和菜品，并输出 JSON：
{{
  "tip_title": "不超过 10 个字的标题",
  "tip_body": "两句话，说明今天为什么推荐这些，必须引用上面的时令知识",
  "food_picks": [食材id, ...],
  "dish_picks": [菜品id, ...],
  "food_notes": {{"食材id": "一句话理由（不超过 20 字）"}},
  "dish_notes": {{"菜品id": "一句话理由（不超过 20 字）"}}
}}

要求：
- food_picks 选 3 个、dish_picks 选 3 个，按推荐优先级排序；
- id 必须来自上面的候选清单，用整数；
- 理由要具体（提到时令、天气或营养），不要写「营养丰富」这类空话；
- 全部用简体中文。"""

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


# =====================================================================
# 校验
# =====================================================================


def _coerce_id_list(value, allowed: set[int], limit: int) -> list[int]:
    """把模型给的 picks 收敛成「合法、去重、保序」的 id 列表。

    ★ 这一步是「AI 不能自由生成」的落地：不在候选集里的 id 一律丢掉。
    """
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for raw in value:
        try:
            candidate = int(raw)
        except (TypeError, ValueError):
            continue
        if candidate in allowed and candidate not in result:
            result.append(candidate)
        if len(result) >= limit:
            break
    return result


def _coerce_notes(value, allowed: set[int]) -> dict[int, str]:
    if not isinstance(value, dict):
        return {}
    notes: dict[int, str] = {}
    for raw_key, raw_text in value.items():
        try:
            key = int(raw_key)
        except (TypeError, ValueError):
            continue
        if key not in allowed:
            continue
        text_value = str(raw_text).strip()
        if text_value:
            notes[key] = text_value[:60]
    return notes


def _fallback(
    *,
    region: str,
    month: int,
    weather: WeatherContext,
    foods: list[ScoredItem],
    dishes: list[ScoredItem],
    cache_key: str,
    error: str | None,
) -> HomeEnhancement:
    """没配 AI 或调用失败时的确定性结果 —— 文案也是「真」的，只是没润色。"""
    season = scoring_service.season_char_of(month)
    return HomeEnhancement(
        tip_title=f"{month} 月{season}日时令",
        tip_body=(
            f"{region}今天{weather.description}，{weather.advice}。"
            "下面这些是按时令、天气和营养从食材库里算出来的。"
        ),
        food_picks=[item.item_id for item in foods[:3]],
        dish_picks=[item.item_id for item in dishes[:3]],
        food_notes={item.item_id: item.reason for item in foods[:3]},
        dish_notes={item.item_id: item.reason for item in dishes[:3]},
        source="algorithm",
        cache_key=cache_key,
        error=error,
    )


# =====================================================================
# 主入口
# =====================================================================


def enhance_home(
    session: Session,
    *,
    region: str,
    date_key: str,
    month: int,
    weather: WeatherContext,
    food_shortlist: list[ScoredItem],
    dish_shortlist: list[ScoredItem],
    refresh: bool = False,
) -> HomeEnhancement:
    """拿到今天的首页 AI 增强结果（缓存优先）。永不抛异常。"""
    cache_key = build_cache_key(
        region=region, date_key=date_key, month=month, weather=weather
    )

    if not refresh:
        cached = _read_cache(session, cache_key)
        if cached:
            return HomeEnhancement(
                tip_title=str(cached.get("tip_title") or ""),
                tip_body=str(cached.get("tip_body") or ""),
                food_picks=[int(i) for i in cached.get("food_picks") or []],
                dish_picks=[int(i) for i in cached.get("dish_picks") or []],
                food_notes={int(k): str(v) for k, v in (cached.get("food_notes") or {}).items()},
                dish_notes={int(k): str(v) for k, v in (cached.get("dish_notes") or {}).items()},
                source="cached",
                model=str(cached.get("model") or ""),
                cache_key=cache_key,
            )

    if not client.is_configured():
        return _fallback(
            region=region,
            month=month,
            weather=weather,
            foods=food_shortlist,
            dishes=dish_shortlist,
            cache_key=cache_key,
            error="未配置 AI_API_KEY",
        )

    # 双重检查 + 串行化：并发请求只让第一个真去调模型
    with _generate_lock:
        if not refresh:
            cached = _read_cache(session, cache_key)
            if cached:
                return HomeEnhancement(
                    tip_title=str(cached.get("tip_title") or ""),
                    tip_body=str(cached.get("tip_body") or ""),
                    food_picks=[int(i) for i in cached.get("food_picks") or []],
                    dish_picks=[int(i) for i in cached.get("dish_picks") or []],
                    food_notes={
                        int(k): str(v) for k, v in (cached.get("food_notes") or {}).items()
                    },
                    dish_notes={
                        int(k): str(v) for k, v in (cached.get("dish_notes") or {}).items()
                    },
                    source="cached",
                    model=str(cached.get("model") or ""),
                    cache_key=cache_key,
                )

        messages = _build_messages(
            session,
            region=region,
            date_key=date_key,
            month=month,
            weather=weather,
            foods=food_shortlist,
            dishes=dish_shortlist,
        )
        result = client.complete_json(messages)

    if not result.ok:
        # ⚠️ 失败**不写缓存** —— 下一次请求应该再试一次，而不是把降级结果锁一天
        return _fallback(
            region=region,
            month=month,
            weather=weather,
            foods=food_shortlist,
            dishes=dish_shortlist,
            cache_key=cache_key,
            error=result.error,
        )

    data = result.data
    food_ids = {item.item_id for item in food_shortlist}
    dish_ids = {item.item_id for item in dish_shortlist}

    food_picks = _coerce_id_list(data.get("food_picks"), food_ids, 3)
    dish_picks = _coerce_id_list(data.get("dish_picks"), dish_ids, 3)
    # 模型没给够就按算法顺序补齐 —— 首页不能因为模型偷懒而缺卡片
    for item in food_shortlist:
        if len(food_picks) >= 3:
            break
        if item.item_id not in food_picks:
            food_picks.append(item.item_id)
    for item in dish_shortlist:
        if len(dish_picks) >= 3:
            break
        if item.item_id not in dish_picks:
            dish_picks.append(item.item_id)

    enhancement = HomeEnhancement(
        tip_title=str(data.get("tip_title") or "").strip()[:24]
        or f"{month} 月时令推荐",
        tip_body=str(data.get("tip_body") or "").strip()
        or weather.advice,
        food_picks=food_picks[:3],
        dish_picks=dish_picks[:3],
        food_notes=_coerce_notes(data.get("food_notes"), food_ids),
        dish_notes=_coerce_notes(data.get("dish_notes"), dish_ids),
        source="ai",
        model=result.model,
        elapsed_ms=result.elapsed_ms,
        cache_key=cache_key,
    )

    _write_cache(
        session,
        cache_key,
        {
            "tip_title": enhancement.tip_title,
            "tip_body": enhancement.tip_body,
            "food_picks": enhancement.food_picks,
            "dish_picks": enhancement.dish_picks,
            "food_notes": {str(k): v for k, v in enhancement.food_notes.items()},
            "dish_notes": {str(k): v for k, v in enhancement.dish_notes.items()},
            "model": enhancement.model,
            "region": region,
            "date": date_key,
            "weather": weather.description,
        },
        enhancement.model,
    )
    return enhancement
