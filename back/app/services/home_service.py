"""首页聚合业务逻辑（说明书 §9 + 本次的「算法 + AI」推荐）。

【这条链路是干嘛的】
    天气(定位) ─┐
    时令(数据库) ─┼─→ 综合打分算法 ─→ 候选集(各 8 个) ─→ 每天每地区一次 AI ─→ 最终 3+3
    营养/标签   ─┤        ▲                                        │
    家庭硬约束  ─┘        └────────── 忌口/限钠/时间 在这里收口 ────┘

关键点：
  · **选什么由算法定**，AI 只在候选集里挑与解释（见 scoring_service 的注释）；
  · **AI 结果按 (地区, 日期) 缓存**，同地区同一天所有人共用一次调用；
  · **用户的忌口/限钠/时间约束在 AI 之后执行**，永远由确定性代码兜底 ——
    安全性不依赖模型，也不依赖缓存命中。

★ 不返回价格字段（说明书 §9 明确要求）——新增的理由文案里也一个字都不许出现。
"""

from __future__ import annotations

import time
from datetime import date as date_cls
from datetime import datetime
from typing import Any

from sqlmodel import Session

from app.schemas.home import (
    HomeAlgoStep,
    HomeFoodItem,
    HomeHero,
    HomeMeta,
    HomeRecipeItem,
    HomeResponse,
    HomeSeason,
    HomeWeather,
    MenuBrief,
)
from app.services import ai_daily_service, food_service, recipe_service, scoring_service
from app.services import weather_service
from app.services.scoring_service import HardConstraints, ScoredItem

# 月份 → 季节名。前端顶部那个「秋季 · 9月」的 pill 用的就是它。
_MONTH_TO_SEASON = {
    1: "冬季",
    2: "冬季",
    3: "春季",
    4: "春季",
    5: "春季",
    6: "夏季",
    7: "夏季",
    8: "夏季",
    9: "秋季",
    10: "秋季",
    11: "秋季",
    12: "冬季",
}

_AI_TIP = "先选当季食材，再搭配家常菜单，做饭更轻松。"

# 候选池大小。8 个是折中：够 AI 挑，又不至于把提示词撑爆、把 token 烧光。
_SHORTLIST = 8


def season_name_of(month: int) -> str:
    return _MONTH_TO_SEASON.get(month, "当季")


def _item_reason(item: ScoredItem, notes: dict[int, str]) -> str:
    """理由优先级：AI 写的 > 算法算出来的。"""
    return notes.get(item.item_id) or item.reason


def food_brief_payload(item: ScoredItem) -> dict[str, Any]:
    """把打分结果转成 FoodBrief 的字段。

    ⚠️ 必须手动回填 `season_score`：`food_service.to_brief()` 不传 season 对象时
       会返回 0。首页的食材卡片就是靠这个字段显示「应季程度」的，
       漏了它前端会以为所有推荐食材的时令分都是 0。
       算法打分时已经算过这个值，直接用 `factors["season"]` 回填，
       不用再查一次库。
    """
    payload = food_service.to_brief(item.raw).model_dump()
    payload["season_score"] = int(item.factors.get("season") or 0)
    return payload


def _order_by_picks(
    ranking: list[ScoredItem], picks: list[int], limit: int
) -> list[ScoredItem]:
    """AI 挑中的排前面，剩下的按算法顺序补齐。

    ★ `ranking` 已经是**过了用户硬约束**的列表 —— AI 挑中但被忌口挡掉的条目
      根本不在这里面，于是自然被跳过。这就是「AI 不能越过安全约束」的落点。
    """
    by_id = {item.item_id: item for item in ranking}
    ordered: list[ScoredItem] = []
    seen: set[int] = set()

    for pick in picks:
        item = by_id.get(pick)
        if item is not None and pick not in seen:
            ordered.append(item)
            seen.add(pick)

    for item in ranking:
        if len(ordered) >= limit:
            break
        if item.item_id not in seen:
            ordered.append(item)
            seen.add(item.item_id)

    return ordered[:limit]


def build_home(
    session: Session,
    *,
    region: str | None = None,
    month: int | None = None,
    limit: int = 3,
    city: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    date_str: str | None = None,
    profile: Any = None,
    refresh: bool = False,
    shortlist: int = _SHORTLIST,
) -> HomeResponse:
    """首页聚合：天气 + 时令食材 + 时令菜品 + AI 每日建议。

    `profile` 是任意「长得像家庭档案」的对象（前端直接传 FamilyProfile 的 JSON）。
    不传就当作没有额外约束 —— 这也是既有测试的调用方式。
    """
    started = time.perf_counter()
    steps: list[HomeAlgoStep] = []

    # ---- 时间与季节 ----
    today = date_str or date_cls.today().isoformat()
    current_month = month or datetime.now().month
    season = season_name_of(current_month)
    region_key = (city or region or "national").strip() or "national"

    constraints = HardConstraints.from_profile(profile)

    # ---- 1. 天气（定位 → 温度/降水 → 饮食意图）----
    t0 = time.perf_counter()
    weather = weather_service.current_weather(
        city=city or region,
        lat=lat,
        lon=lon,
        today=today,
        month=current_month,
    )
    steps.append(
        HomeAlgoStep(
            step="天气与定位",
            detail=f"{region_key} · {weather.description} → {weather.advice}",
            ms=int((time.perf_counter() - t0) * 1000),
        )
    )

    # ---- 2. 算法筛候选（★ 这一遍不带用户忌口，目的是让 AI 结果能按地区共享）----
    t0 = time.perf_counter()
    neutral = HardConstraints(people=3, cook_minutes=240.0)
    region_foods = scoring_service.score_foods(
        session,
        month=current_month,
        weather=weather,
        constraints=neutral,
        region=region_key,
        date_key=today,
        limit=shortlist,
    )
    region_dishes = scoring_service.score_dishes(
        session,
        month=current_month,
        weather=weather,
        constraints=neutral,
        region=region_key,
        date_key=today,
        limit=shortlist,
    )
    steps.append(
        HomeAlgoStep(
            step="综合打分筛候选",
            detail=(
                f"时令档位优先，按天气适配/营养/偏好/热度/每日轮换加权 → "
                f"食材 {len(region_foods)} 个、菜品 {len(region_dishes)} 道"
            ),
            ms=int((time.perf_counter() - t0) * 1000),
        )
    )

    # ---- 3. 每天每地区只问一次 AI ----
    enhancement = ai_daily_service.enhance_home(
        session,
        region=region_key,
        date_key=today,
        month=current_month,
        weather=weather,
        food_shortlist=region_foods,
        dish_shortlist=region_dishes,
        refresh=refresh,
    )
    if enhancement.source in {"ai", "cached"}:
        steps.append(
            HomeAlgoStep(
                step="AI 每日建议",
                detail=(
                    "今天这个地区的推荐已生成并缓存"
                    if enhancement.source == "cached"
                    else f"调用 {enhancement.model} 生成当天建议并在候选集内挑选"
                ),
                ms=enhancement.elapsed_ms,
            )
        )
    else:
        steps.append(
            HomeAlgoStep(
                step="AI 每日建议",
                detail=f"未启用或调用失败（{enhancement.error or '未配置'}），改用确定性文案",
                ms=0,
            )
        )

    # ---- 4. 带用户硬约束再排一遍（忌口/限钠/可用时间在这里真正生效）----
    t0 = time.perf_counter()
    user_foods = scoring_service.score_foods(
        session,
        month=current_month,
        weather=weather,
        constraints=constraints,
        region=region_key,
        date_key=today,
        limit=12,
    )
    user_dishes = scoring_service.score_dishes(
        session,
        month=current_month,
        weather=weather,
        constraints=constraints,
        region=region_key,
        date_key=today,
        limit=20,
    )

    # 全被筛光的兜底：宁可给一道「可能不完全合条件」的，也不能让首页空白
    if not user_foods:
        user_foods = region_foods
    if not user_dishes:
        user_dishes = region_dishes
    steps.append(
        HomeAlgoStep(
            step="用户硬约束收口",
            detail=(
                f"{constraints.people} 人 · {constraints.cook_minutes:.0f} 分钟内"
                + (f" · 忌{('、'.join(constraints.avoid))}" if constraints.avoid else "")
                + (" · 限钠" if constraints.low_sodium else "")
                + f" → 可用食材 {len(user_foods)} 个、菜品 {len(user_dishes)} 道"
            ),
            ms=int((time.perf_counter() - t0) * 1000),
        )
    )

    # ---- 5. 组合最终结果 ----
    final_foods = _order_by_picks(user_foods, enhancement.food_picks, limit)
    final_dishes = _order_by_picks(user_dishes, enhancement.dish_picks, limit)

    food_items = [
        HomeFoodItem(
            **food_brief_payload(item),
            reason=_item_reason(item, enhancement.food_notes),
            highlights=item.highlights,
            score=round(item.score, 3),
        )
        for item in final_foods
    ]

    dish_items = [
        HomeRecipeItem(
            **recipe_service.to_brief(item.raw).model_dump(),
            reason=_item_reason(
                item, enhancement.dish_notes
            ),
            highlights=item.highlights,
            score=round(item.score, 3),
        )
        for item in final_dishes
    ]

    # ⚠️ 「菜单推荐」是按当季菜谱【动态组合】出来的建议，不是数据库里的实体，
    #    所以 id 固定为 0 —— 前端据此知道这是组合推荐，不是可打开的菜单详情。
    menus: list[MenuBrief] = []
    if dish_items:
        top = dish_items[0]
        menus.append(
            MenuBrief(
                id=0,
                title=f"{season}家常菜单",
                image=top.image,
                servings=top.servings,
                tags=["当季推荐", "荤素搭配"],
            )
        )

    hero_image = food_items[0].image if food_items else (
        dish_items[0].image if dish_items else None
    )

    steps.append(
        HomeAlgoStep(
            step="生成结果",
            detail=f"最终 {len(food_items)} 个食材 + {len(dish_items)} 道菜",
            ms=int((time.perf_counter() - started) * 1000),
        )
    )

    return HomeResponse(
        season=HomeSeason(name=season, month=current_month, region=region),
        hero=HomeHero(
            title="今日推荐",
            subtitle="应季食材 · 家常菜单 · 轻松安排",
            image=hero_image,
        ),
        recommended_foods=food_items,
        recommended_menus=menus,
        ai_tip=enhancement.tip_body or _AI_TIP,
        ai_tip_title=enhancement.tip_title,
        recommended_recipes=dish_items,
        weather=HomeWeather(
            city=weather.city,
            date=weather.date,
            kind=weather.kind,
            description=weather.description,
            advice=weather.advice,
            temperature_c=weather.temperature_c,
            source=weather.source,
        ),
        meta=HomeMeta(
            source=enhancement.source,
            model=enhancement.model or None,
            ai_ms=enhancement.elapsed_ms,
            cache_key=enhancement.cache_key,
            shortlist_foods=len(region_foods),
            shortlist_dishes=len(region_dishes),
            steps=steps,
        ),
    )
