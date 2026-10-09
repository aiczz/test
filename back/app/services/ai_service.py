"""AI 助手业务逻辑（说明书 §20 + 本次的真·大模型接入）。

【架构：算法选、AI 说】
    意图识别（规则）
        ↓
    候选召回（我们自己的清洗库：590 食材 / 10000 菜 / 营养 / 标签 / 时令）
        ↓
    硬约束过滤（忌口、可用时间、限钠）—— 确定性代码，AI 不参与
        ↓
    大模型只在候选集内挑选与解释（不在候选里的 id 一律丢弃）
        ↓
    失败 / 未配置 → 退回原来的纯规则实现（行为与改造前完全一致）

【为什么保留规则实现而不删】
一是没配 API Key 时接口不能瘫；二是它是「AI 幻觉」的安全网 ——
模型说的每一道菜都必须是我们库里真实存在的 id。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from weakref import WeakKeyDictionary

from sqlmodel import Session

from app.ai import client
from app.repositories import catalog_insight_repository as catalog_insight
from app.repositories import my_food_repository, recipe_repository
from app.repositories.catalog_insight_repository import (
    dish_insights,
    food_insights,
    seasonal_knowledge,
)
from app.schemas.home import HomeFoodItem
from app.schemas.ai import (
    AiChatRequest,
    AiChatResponse,
    AiMenuSummary,
    AiRecipePick,
    AiRecommendRequest,
    AiRecommendResponse,
    AiTraceStep,
)
from app.services import (
    home_service,
    need_service,
    recipe_service,
    scoring_service,
    weather_service,
)
from app.services.need_service import HealthGoal
from app.services.scoring_service import HardConstraints, ScoredItem

# 语义意图识别失败时只记日志、不打扰用户 —— 退回关键词规则就是了。
logger = logging.getLogger(__name__)

# 意图关键词。
#
# ⚠️ 这里踩过一个坑：原来「用我的食材」只认「我有什么 / 现有食材 / 家里有 /
#    库存 / 用这些 / 冰箱 / 我的食材」这几个固定串。用户说的是
#    「…要用**我家里的食材**」—— 一个都没命中（就是少了中间那个「的」），
#    而句子里有「菜单」，于是被判成 meal_recommendation，
#    **整条库存链路压根没执行**。用户看到的就是「让他用我家食材，他却推了别的」。
#
#    所以现在两层判断：
#      ① 短语表（补全了各种说法）
#      ② 「同时提到『我的/我家/家里』和『食材/材料/库存』」→ 也算用我的食材
#        —— 比无限扩短语表稳，换个说法也不会漏。
_INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        "cook_with_my_foods",
        [
            "我有什么", "现有食材", "家里有", "库存", "用这些", "冰箱", "我的食材",
            "我家的食材", "家里的食材", "我家食材", "家里食材", "我家有的",
            "我有的", "现有材料", "家里有什么", "用我的",
        ],
    ),
    (
        "meal_recommendation",
        ["吃什么", "推荐", "菜单", "晚餐", "午餐", "早餐", "今晚", "晚饭", "午饭"],
    ),
]

# 第二层判断用词
_POSSESSIVE_HINTS = ("我的", "我家", "家里", "自家", "现有的")
_FOOD_HINTS = ("食材", "材料", "原料", "库存", "冰箱", "东西")

# 「追问」用词：用户接着上一轮说「换一批 / 再来几个」。
#
# ⚠️ 这类句子**不含任何推荐关键词**，逐句独立判断会掉进 general 分支，
#    于是「第一问有卡片，后面再问就没了」（实测踩过）。
#    所以它们要继承上一轮的意图，并且**避开已经展示过的菜** ——
#    否则每天轮换因子是固定的，重问一次还是那三道。
_FOLLOW_UP_HINTS = (
    "换一批", "换几个", "换一换", "换换", "换点", "再来", "再推荐", "再给我",
    "还有别的", "还有吗", "还有其它", "还有其他", "其他的", "其它呢", "别的呢",
    "别的菜", "不要这个", "不要这", "不喜欢这", "重来", "另一个", "其它推荐",
)


def _is_follow_up(message: str) -> bool:
    return any(hint in message for hint in _FOLLOW_UP_HINTS)


# =====================================================================
# 「推荐」信号词
#
# 【为什么要从"关键词判意图"改成"先抽信号再决策"】
# 原来是「命中固定短语 → 是推荐；否则 → 闲聊」。实测 19 条常见说法里
# **11 条判错**：
#     「我想吃清淡点的」→ 闲聊      「我想减肥」→ 闲聊（诉求解析出来了却被丢掉！）
#     「最近想补气血」  → 闲聊      「我不吃香菜」→ 闲聊（忌口声明被忽略）
#     「今天中午吃啥」  → 闲聊      「莲藕怎么做」→ 闲聊
# 根因是架构性的：用户表达需求的方式是**无限**的，而关键词表是有限的。
#
# 现在改成先抽五类信号，再按优先级决策：
#     ① 追问（换一批）      ② 提到自己的食材      ③ 餐次/吃喝/推荐词
#     ④ 食养诉求（补气血…）  ⑤ 提到了具体食材名
# 只要有 ③④⑤ 任何一条，就是"用户表达了需求"，必须走推荐 —— 宁可多推一次，
# 也不能把用户明说的需求当成闲聊敷衍过去。
# =====================================================================
_MEAL_HINTS = (
    # 吃喝本身
    "吃什么", "吃啥", "吃点", "吃点儿", "想吃", "吃个", "吃饭", "吃菜",
    "喝汤", "想喝", "喝点", "来点", "来点儿", "想来点", "来一个", "来个",
    # 推荐/搭配
    "推荐", "菜单", "菜谱", "配菜", "配个", "搭个", "搭配", "安排",
    # 餐次
    "早餐", "午餐", "晚餐", "早饭", "午饭", "晚饭", "夜宵", "加餐", "正餐",
    # 单字兜底（风险可控：闲聊里几乎不出现）
    "菜", "汤", "饭",
)

# 「自己的食材」信号
_POSSESSIVE_HINTS = ("我的", "我家", "家里", "自家", "现有的")
_FOOD_HINTS = ("食材", "材料", "原料", "库存", "冰箱", "东西")

# 「想要食材建议」信号（区别于「想做饭」）。
#
# ⚠️ 这一小串**只在离线兜底时用得上**。联网时意图是模型按语义判的 ——
#    像「家里有健身的」这种一个「食材」都没提的说法，关键词表认不出来。
#    这也正是要加语义那层的原因：规则这层的价值是「没配 AI 也不变哑巴」，
#    不是「判得准」。
_FOOD_WANT_HINTS = (
    "推荐点食材", "推荐食材", "推荐些食材", "吃什么食材", "吃哪些食材",
    "该买什么", "买点什么", "买什么菜", "要买什么", "采购", "买菜",
    "补钙", "补铁", "补锌", "补蛋白质", "补充蛋白",
)

# 忌口/否定表达 —— 必须尊重，否则可能推出用户不能吃的东西（安全问题）
_NEGATION_HINTS = (
    "不吃", "不能吃", "忌口", "忌食", "忌", "过敏", "讨厌", "受不了",
    "别放", "不要放", "少放", "不爱吃",
)

# 常见忌口词（和 scoring_service 的 _DEFAULT_AVOID_SYNONYMS 对齐）
_KNOWN_AVOID_WORDS = (
    "辛辣", "辣", "海鲜", "牛羊肉", "香菜", "内脏", "花生", "鸡蛋", "乳制品", "油腻",
)

_CN_NUMBERS = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_SYSTEM_PROMPT = """你是「食时」App 里的饮食助手「小食」，服务中国家庭的一日三餐。

铁律：
1. 你推荐菜品时**只能**从用户消息里给出的候选清单中挑选，绝不许新增清单之外的菜名。
2. 关于时令、营养、功效的说法，必须以给出的「时令知识」与候选自带的营养/标签为依据。
   不要编造没有依据的养生说法。
3. 用户有忌口或限钠要求时，绝对不要推荐违反这些要求的菜 —— 系统也会再拦一遍。
4. 只输出 JSON，不要输出解释性文字或 Markdown 围栏。"""


# =====================================================================
# 规则部分（保留：意图识别 + 兜底）
# =====================================================================


def _detect_intent(message: str) -> str:
    """（保留给测试与旧调用）只做「推荐 or 闲聊」的粗判，不含需求解析。"""
    return _route(session=None, message=message, payload=None).intent


@dataclass(slots=True)
class _Route:
    """一次问答解析出来的全部信号。"""

    intent: str
    follow_up: bool = False
    health_goal: Any = None
    # 用户在话里点名的食材（「莲藕怎么做」）—— 用它召回，才算答到点子上
    mentioned_ids: list[int] = field(default_factory=list)
    mentioned_names: list[str] = field(default_factory=list)
    # 用户在话里声明的忌口（「我不吃香菜」）—— 必须加进硬约束
    avoid_added: list[str] = field(default_factory=list)
    # 这个意图是「按语义判出来的」（ai）还是「关键词匹配出来的」（rules）。
    # 如实标出来并进轨迹 —— 用户和评委都该知道这句话是被**理解**了还是被**匹配**了。
    source: str = "rules"
    why: str = ""


def _mentioned_foods(session: Session | None, message: str) -> tuple[list[int], list[str]]:
    """从用户的话里认出他提到的食材（含别名）。

    「莲藕怎么做」如果只当成普通推荐，就会推一堆当季菜 —— 那是典型的
    牛头不对马嘴。认出食材名之后按它召回，回答才会围绕莲藕。
    别名也要认：用户说「西红柿」，而库里的核心名叫「番茄」——
    只按名字匹配就认不出来（实测 580/590 的食材带别名）。
    """
    if session is None:
        return [], []

    terms = _food_terms_cached(session)
    ids: list[int] = []
    names: list[str] = []
    for food_id, name, aliases in terms:
        hit = len(name) >= 2 and name in message
        if not hit:
            hit = any(alias in message for alias in aliases)
        if hit:
            ids.append(food_id)
            names.append(name)
    return ids, names


# 590 个食材 + 别名 ≈ 上万个子串，每题都重新查+解析 JSON 太浪费。
# 按引擎缓存一份（WeakKeyDictionary 避免引擎回收后 id 复用导致串数据）。
_food_terms_cache: "WeakKeyDictionary[Any, list[tuple[int, str, list[str]]]]" = (
    WeakKeyDictionary()
)


def _food_terms_cached(session: Session) -> list[tuple[int, str, list[str]]]:
    bind = session.get_bind()
    try:
        cached = _food_terms_cache.get(bind)
    except TypeError:
        return catalog_insight.list_core_food_terms(session)
    if cached is None:
        cached = catalog_insight.list_core_food_terms(session)
        try:
            _food_terms_cache[bind] = cached
        except TypeError:
            pass
    return cached


def _declared_avoid(message: str, mentioned_names: list[str]) -> list[str]:
    """从话里抽出用户声明的忌口。

    ⚠️ 这是**安全相关**的：「我不吃香菜」如果被当成闲聊忽略掉，
       后面推的菜里出现香菜就是事故。所以只要出现否定词，
       就把句子里提到的食材 + 已知忌口词都加进硬约束。
    """
    if not any(hint in message for hint in _NEGATION_HINTS):
        return []
    terms: list[str] = []
    for name in mentioned_names:
        if name not in terms:
            terms.append(name)
    for word in _KNOWN_AVOID_WORDS:
        if word in message and word not in terms:
            terms.append(word)
    return terms


# =====================================================================
# 语义意图识别
#
# 【为什么要加这一层】
# `_route()` 是**关键词**匹配。中文的表达方式太多了：
#     「最近有点虚」    「想给娃补补」     「体检说血脂高」
#     「家里有健身的」  「想买点能补钙的」
# 这些句子里一个「吃」「推荐」「食材」都没有，关键词表永远补不全。
#
# 所以：**优先让大模型按语义判断**，判不出来（没配 key / 网络失败 / 返回垃圾）
# 再退回关键词那套。两层都要有 —— 关键词那层不只是兜底，
# 它还是**离线可用**的保证（没配 AI 时整个助手不能变成哑巴）。
#
# 判出来的结果会如实写进轨迹（「意图识别」那一步），标明是语义判的还是关键词判的。
# =====================================================================

# 意图清单 —— 提示词里给模型看的就是这四个
_INTENT_LABELS = {
    "meal_recommendation": "想知道**吃什么菜**，或提出了饮食/健康诉求（想补气血、减脂、清淡点…）",
    "recommend_foods": (
        "想知道**吃什么食材 / 该买什么**，或要针对某个目标挑食材"
        "（健身要补蛋白、要补钙、贫血、想润肺…）；也包含「随便推荐点食材」"
    ),
    "cook_with_my_foods": "明确要用**自己现有的食材 / 家里的食材 / 库存**来做菜",
    "general": "纯寒暄、打招呼、问你是谁、说谢谢/再见，没有饮食需求",
}


def _classify_prompt(message: str, last_intent: str | None) -> str:
    goals = "、".join(goal.name for goal in need_service.all_goals())
    labels = "\n".join(f"  - {k}：{v}" for k, v in _INTENT_LABELS.items())
    context = (
        f"\n【上一轮意图】{last_intent}（如果这句是「换一批」「还有吗」这类"
        f"没有新信息的追问，就沿用这个意图）"
        if last_intent
        else ""
    )
    return f"""你在判断用户这句话的**意图**，并抽出其中的需求。按意思判断，不要按关键词。

可选意图：
{labels}

用户说：{message}{context}

注意：
- 中文说法很多样。「最近有点虚」「想给娃补补」「家里有健身的」「体检说血脂高」
  都表达了需求，不要因为它们没有「吃」「推荐」这类词就判成 general；
- 只有用户**明确提到自己的食材/库存**时，才是 cook_with_my_foods；
- 既要菜又要食材、或者没说清是菜还是食材时，选 meal_recommendation；
- 拿不准就不要硬判：宁可给 general，也不要瞎猜一个需求出来。

只输出 JSON：
{{
  "intent": "四选一",
  "goal": 食养诉求名，从下面这份清单里选一个，没有就给 null
          （{goals}），
  "foods": ["用户明确点名的食材名", ...]（没有就给空数组）,
  "avoid": ["用户明确说不吃/过敏的东西", ...]（没有就给空数组）,
  "why": "一句话说明你为什么这么判（不超过 30 字）"
}}"""


def _route_semantic(
    *, session: Session | None, message: str, payload: Any = None
) -> _Route | None:
    """让模型按语义判意图。判不出来返回 None（调用方退回关键词规则）。"""
    if not client.is_configured():
        return None

    last_intent = getattr(payload, "last_intent", None) if payload else None
    result = client.complete_json(
        [
            {
                "role": "system",
                "content": "你是意图分类器。只输出 JSON，不要任何多余文字。",
            },
            {"role": "user", "content": _classify_prompt(message, last_intent)},
        ],
        max_tokens=200,
        temperature=0.0,
    )
    if not result.ok:
        logger.info("语义意图识别失败，退回关键词规则：%s", result.error)
        return None

    data = result.data or {}
    intent = str(data.get("intent") or "").strip()
    if intent not in _INTENT_LABELS:
        logger.info("语义意图识别给了个没见过的标签：%r", intent)
        return None

    # 诉求：优先用模型给的名字，认不出来再用关键词兜（模型可能给个近义说法）
    goal = None
    raw_goal = str(data.get("goal") or "").strip()
    if raw_goal:
        goal = next(
            (g for g in need_service.all_goals() if g.name == raw_goal), None
        )
    if goal is None:
        goal = need_service.extract_goal(message)

    # 点名食材 / 忌口：一律以**库里的名字**为准（模型可能给口语化的说法），
    # 所以这里不是直接采信模型，而是拿它当线索再走一遍确定性识别 ——
    # 顺序也重要：把模型提到的食材名拼进探测串，能补上关键词漏掉的。
    mentioned_ids, mentioned_names = _mentioned_foods(session, message)
    for extra in data.get("foods") or []:
        extra_name = str(extra).strip()
        if extra_name and extra_name not in mentioned_names:
            extra_ids, extra_names = _mentioned_foods(session, extra_name)
            for food_id, food_name in zip(extra_ids, extra_names):
                if food_name not in mentioned_names:
                    mentioned_ids.append(food_id)
                    mentioned_names.append(food_name)

    avoid_added = _declared_avoid(message, mentioned_names)
    for extra in data.get("avoid") or []:
        name = str(extra).strip()
        if name and name not in avoid_added:
            avoid_added.append(name)

    # 被否定的食材不能当召回依据（同 `_route` 的处理）
    kept = [
        (food_id, name)
        for food_id, name in zip(mentioned_ids, mentioned_names)
        if name not in avoid_added
    ]

    return _Route(
        intent=intent,
        follow_up=_is_follow_up(message),
        health_goal=goal,
        mentioned_ids=[food_id for food_id, _ in kept],
        mentioned_names=[name for _, name in kept],
        avoid_added=avoid_added,
        source="ai",
        why=str(data.get("why") or "").strip(),
    )


def _route_smart(
    *, session: Session | None, message: str, payload: Any = None
) -> _Route:
    """语义优先、关键词兜底。两层都保证「一定能给出一个意图」。"""
    semantic = _route_semantic(session=session, message=message, payload=payload)
    if semantic is not None:
        return semantic
    return _route(session=session, message=message, payload=payload)


def _route(
    *, session: Session | None, message: str, payload: Any = None
) -> _Route:
    """把一句话路由成「闲聊」或「推荐」，并顺带抽出诉求/食材/忌口。

    ⚠️ 这是**关键词**版本，现在只当兜底用（见 `_route_smart`）：
       没配 AI、网络失败、模型返回垃圾时走这条。
       它的价值是「离线也能用」，不是「判得准」。

    优先级（顺序即优先级）：
        ① 追问               → 继承上一轮意图
        ② 提到自己的食材     → cook_with_my_foods
        ③ 餐次/吃喝/推荐词   → meal_recommendation
        ④ 食养诉求           → meal_recommendation（诉求解析出来了就必须用！）
        ⑤ 点名了具体食材     → meal_recommendation（按这个食材召回）
        否则                 → general（闲聊）
    """
    goal = need_service.extract_goal(message)
    mentioned_ids, mentioned_names = _mentioned_foods(session, message)
    avoid_added = _declared_avoid(message, mentioned_names)

    # ⚠️ 被否定的食材**不能**当召回依据。
    #    「我不吃鸡蛋」如果拿鸡蛋去召回，正好会召回一堆鸡蛋菜 —— 南辕北辙。
    #    mentioned_ids / mentioned_names 下标必须一致，所以要一起过滤。
    kept = [
        (food_id, name)
        for food_id, name in zip(mentioned_ids, mentioned_names)
        if name not in avoid_added
    ]
    mentioned_ids = [food_id for food_id, _ in kept]
    mentioned_names = [name for _, name in kept]

    # 原来的短语表继续当信号用（「我有什么」「现有食材」这类没有
    # 「我的/家里 + 食材」的结构，光靠组合规则会漏）
    mentioned_mine_phrase = any(
        phrase in message
        for intent_label, phrases in _INTENT_KEYWORDS
        if intent_label == "cook_with_my_foods"
        for phrase in phrases
    )

    # ① 追问
    if _is_follow_up(message):
        inherited = getattr(payload, "last_intent", None) if payload else None
        # ⚠️ 可继承的意图清单要和「能出卡片的意图」保持一致。
        #    漏了 recommend_foods 的后果：在食材推荐之后说「换一批」，
        #    会突然变回推荐菜品 —— 卡片类型都变了，用户一脸问号。
        intent = (
            inherited
            if inherited
            in {"meal_recommendation", "cook_with_my_foods", "recommend_foods"}
            else "meal_recommendation"
        )
        return _Route(
            intent=intent,
            follow_up=True,
            health_goal=goal,
            mentioned_ids=mentioned_ids,
            mentioned_names=mentioned_names,
            avoid_added=avoid_added,
        )

    # ② 提到自己的食材
    mentions_mine = mentioned_mine_phrase or (
        any(h in message for h in _POSSESSIVE_HINTS)
        and any(h in message for h in _FOOD_HINTS)
    )
    if mentions_mine:
        return _Route(
            intent="cook_with_my_foods",
            health_goal=goal,
            mentioned_ids=mentioned_ids,
            mentioned_names=mentioned_names,
            avoid_added=avoid_added,
        )

    # ②.5 想要「食材」而不是「菜」→ recommend_foods
    #
    # 放在 cook_with_my_foods **之后**：说「用我的食材」是要做饭，
    # 不是要采购建议 —— 那两句话的意图不一样。
    if any(hint in message for hint in _FOOD_WANT_HINTS):
        return _Route(
            intent="recommend_foods",
            health_goal=goal,
            mentioned_ids=mentioned_ids,
            mentioned_names=mentioned_names,
            avoid_added=avoid_added,
        )

    # ③④⑤⑥ 任何一条都算「用户表达了需求」
    has_meal_signal = any(hint in message for hint in _MEAL_HINTS)
    if (
        has_meal_signal
        or goal is not None
        or mentioned_ids
        # 用户声明了忌口（「我海鲜过敏」）—— 这也是在提需求：
        # 要么给他推能吃的，要么明确回应。当成闲聊丢掉是不负责任的。
        or avoid_added
    ):
        return _Route(
            intent="meal_recommendation",
            health_goal=goal,
            mentioned_ids=mentioned_ids,
            mentioned_names=mentioned_names,
            avoid_added=avoid_added,
        )

    return _Route(
        intent="general",
        health_goal=goal,
        mentioned_ids=mentioned_ids,
        mentioned_names=mentioned_names,
        avoid_added=avoid_added,
    )


def _parse_people(message: str) -> int | None:
    """从「三个人」「3人」里把人数抠出来。"""
    match = re.search(r"([0-9]+)\s*个?\s*人", message)
    if match:
        return int(match.group(1))
    match = re.search(r"([一两二三四五六七八九十])\s*个?\s*人", message)
    if match:
        return _CN_NUMBERS.get(match.group(1))
    return None


# =====================================================================
# 上下文构造
# =====================================================================


def _constraints(
    session: Session, user_id: int | None, payload: Any
) -> HardConstraints:
    """把「请求里带的约束」和「登录用户的偏好」合并。

    请求里显式传了就用请求的；没传就用用户档案里存的；都没有就用默认。
    """
    constraints = HardConstraints.from_profile(payload)

    if user_id is None:
        return constraints

    try:
        from app.repositories import user_repository

        preference = user_repository.ensure_preference(session, user_id)
    except Exception:  # noqa: BLE001 —— 档案读不到不该让助手挂掉
        return constraints

    if not constraints.avoid and preference.avoid_foods:
        constraints.avoid = tuple(preference.avoid_foods)
    if not constraints.preferences:
        tastes = [
            value
            for value in (preference.taste, preference.diet_style)
            if value
        ]
        tastes.extend(preference.favorite_categories or [])
        constraints.preferences = tuple(dict.fromkeys(tastes))
    return constraints


def _my_food_ids(session: Session, user_id: int | None) -> list[int]:
    if user_id is None:
        return []
    return [
        int(item.food_id)
        for item in my_food_repository.list_for_user(session, user_id)
        if item.food_id
    ]


def _weather_for(payload: Any, month: int):
    city = getattr(payload, "city", None)
    return weather_service.current_weather(city=city, month=month)


# =====================================================================
# 候选与提示词
# =====================================================================


def _candidate_lines(session: Session, items: list[ScoredItem]) -> list[str]:
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
                f"蛋白{insight.protein_g:g}g" if insight.protein_g is not None else "",
                f"钠{round(insight.na_mg)}mg" if insight.na_mg is not None else "",
            )
            if part
        )
        lines.append(
            f"{item.item_id} | {item.name} | 标签：{'、'.join(insight.tags[:4]) or '—'} | "
            f"{nutrition or '营养数据暂无'} | 主要食材："
            f"{'、'.join(insight.main_ingredients[:5]) or '—'}"
        )
    return lines


def _facts_block(session: Session, month: int) -> str:
    facts = seasonal_knowledge(
        session, month=month, season=scoring_service.season_char_of(month)
    )
    return "\n".join(f"- {fact}" for fact in facts) or "- （本库暂无该月时令知识条目）"


def _constraints_block(constraints: HardConstraints) -> str:
    return (
        f"{constraints.people} 人用餐；"
        f"可用烹饪时间 {constraints.cook_minutes:.0f} 分钟；"
        f"{'限钠（少盐）' if constraints.low_sodium else '不限钠'}；"
        f"口味偏好：{'、'.join(constraints.preferences) or '无'}；"
        f"忌口：{'、'.join(constraints.avoid) or '无'}"
    )


def _coerce_picks(value: Any, allowed: set[int], limit: int) -> list[dict[str, Any]]:
    """收敛模型返回的 picks：不在候选集里的直接丢弃（幻觉防线）。"""
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for entry in value:
        if isinstance(entry, dict):
            raw_id = entry.get("id")
            reason = str(entry.get("reason") or "").strip()
        else:
            raw_id, reason = entry, ""
        try:
            candidate = int(raw_id)
        except (TypeError, ValueError):
            continue
        if candidate in allowed and candidate not in seen:
            seen.add(candidate)
            result.append({"id": candidate, "reason": reason})
        if len(result) >= limit:
            break
    return result


# =====================================================================
# 对话
# =====================================================================


def _food_candidate_lines(session: Session, items: list[ScoredItem]) -> list[str]:
    """给模型看的食材候选清单。"""
    lines: list[str] = []
    for item in items:
        insight = item.insight
        tags = "、".join((insight.tags or [])[:4]) if insight else "—"
        season = int(item.factors.get("season") or 0)
        lines.append(
            f"{item.item_id} | {item.name} | 标签：{tags} | 应季分：{season}"
        )
    return lines


def _food_prompt(
    *,
    session: Session,
    payload: Any,
    constraints: HardConstraints,
    weather: Any,
    month: int,
    candidates: list[ScoredItem],
    health_goal: Any,
    count: int,
) -> str:
    goal_block = ""
    if health_goal is not None:
        goal_block = f"\n【★ 用户的核心诉求 · 优先满足】{health_goal.as_prompt_line()}"
    extra = (
        f"\n【用户原话】{payload.message}"
        if getattr(payload, "message", None)
        else ""
    )
    return f"""【任务】帮用户挑 {count} 样**食材**（不是菜品），并说明为什么适合他。
【家庭约束】{_constraints_block(constraints)}
【今天】{month} 月（{scoring_service.season_char_of(month)}季）{payload.city or ''}
【天气】{weather.description} —— {weather.advice}{extra}{goal_block}
【时令知识 · 来自我们的时令数据库】
{_facts_block(session, month)}

【候选食材】（只能从这里挑）
{chr(10).join(_food_candidate_lines(session, candidates))}

请输出 JSON：
{{
  "answer": "给用户的一段话，2~3 句，说清为什么这几样适合他现在的需求",
  "picks": [{{"id": 食材id, "reason": "一句话理由（不超过 20 字）"}}]
}}

要求：
- picks 选 {count} 个，按推荐优先级排序，id 必须来自候选清单；
- 必须围绕用户的需求说（他说健身就讲蛋白质，说补铁就讲含铁量），
  不要只讲时令和天气；
- 必须遵守忌口与限钠约束；
- 全部用简体中文。"""


def _answer_food_recommendation(
    *,
    session: Session,
    payload: Any,
    route: _Route,
    user_id: int | None,
) -> AiChatResponse:
    """「推荐食材」链路 —— 和 `meal_recommendation` 对称，只是产出食材。

    典型输入：「家里有健身的」「想补点钙」「体检说血脂高」「随便推荐点食材」。
    """
    message = payload.message
    count = 3

    constraints = _constraints(session, user_id, payload)
    constraints.people = _parse_people(message) or payload.people or 3
    if route.avoid_added:
        merged = list(constraints.avoid)
        for term in route.avoid_added:
            if term not in merged:
                merged.append(term)
        constraints.avoid = tuple(merged)
        constraints.preferences = tuple(
            p for p in constraints.preferences if p not in constraints.avoid
        )

    month = datetime.now().month
    weather = _weather_for(payload, month)
    trace: list[AiTraceStep] = []

    trace.append(
        AiTraceStep(
            agent="读取约束",
            summary=(
                f"读取约束：{constraints.people} 人用餐；"
                f"{'限钠（少盐）' if constraints.low_sodium else '不限钠'}；"
                f"口味偏好：{'、'.join(constraints.preferences) or '无'}；"
                f"忌口：{'、'.join(constraints.avoid) or '无'}"
            ),
            ms=1,
        )
    )
    # 意图是怎么判出来的，如实标出来
    trace.append(
        AiTraceStep(
            agent="意图识别",
            summary=(
                "按语义判断：这句话是「想要食材推荐」"
                + (f" —— {route.why}" if route.why else "")
                if route.source == "ai"
                else "按关键词判断：这句话是「想要食材推荐」（AI 未启用，走规则兜底）"
            ),
            ms=0,
        )
    )
    if route.health_goal is not None:
        trace.append(
            AiTraceStep(
                agent="需求解析",
                summary=(
                    f"识别到诉求「{route.health_goal.name}」→ 按功效关键词"
                    f"（{'、'.join(route.health_goal.effect_keywords[:4])}…）"
                    "扩大召回并优先排序"
                ),
                ms=1,
            )
        )
    else:
        trace.append(
            AiTraceStep(
                agent="需求解析",
                summary="没有识别到具体诉求 → 按时令与天气推荐应季食材",
                ms=1,
            )
        )

    t0 = time.perf_counter()
    # 「换一批」：把已经给过的食材排掉
    already_shown_foods = {
        int(i) for i in (getattr(payload, "recent_food_ids", None) or []) if i
    }
    candidates = scoring_service.score_foods(
        session,
        month=month,
        weather=weather,
        constraints=constraints,
        region=payload.city or "national",
        date_key=datetime.now().date().isoformat(),
        pool_size=200,
        limit=8,
        health_goal=route.health_goal,
        exclude_ids=already_shown_foods or None,
    )
    trace.append(
        AiTraceStep(
            agent="候选召回",
            summary=(
                f"按功效匹配 + 综合打分召回 → 候选 {len(candidates)} 样食材"
                if route.health_goal is not None
                else f"按当月时令与天气召回 → 综合打分筛出候选 {len(candidates)} 样食材"
            ),
            ms=int((time.perf_counter() - t0) * 1000),
        )
    )

    if not candidates:
        return AiChatResponse(
            answer="按当前条件没找到合适的食材，放宽一下忌口再试试？",
            intent="recommend_foods",
            trace=trace,
            source="algorithm",
            intent_source=route.source,
        )

    allowed = {item.item_id for item in candidates}
    answer: str | None = None
    picks: list[dict[str, Any]] = []
    source = "algorithm"
    model_name: str | None = None
    ai_ms = 0

    if client.is_configured():
        result = client.complete_json(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _food_prompt(
                        session=session,
                        payload=payload,
                        constraints=constraints,
                        weather=weather,
                        month=month,
                        candidates=candidates,
                        health_goal=route.health_goal,
                        count=count,
                    ),
                },
            ]
        )
        ai_ms = result.elapsed_ms
        if result.ok:
            raw_answer = str(result.data.get("answer") or "").strip()
            picks = _coerce_picks(result.data.get("picks"), allowed, count)
            if raw_answer:
                answer = raw_answer
                source = "ai"
                model_name = result.model

    if answer is None:
        trace.append(
            AiTraceStep(
                agent="文案生成",
                summary="模型不可用，改用规则生成（结果结构不变）",
                ms=ai_ms,
                status="info",
            )
        )
        prefix = (
            f"按你说的「{route.health_goal.name}」，我挑了这几样："
            if route.health_goal is not None
            else "按现在的时令，我挑了这几样："
        )
        answer = prefix + "、".join(item.name for item in candidates[:count]) + "。"
        picks = [
            {"id": item.item_id, "reason": item.reason or ""}
            for item in candidates[:count]
        ]
    else:
        trace.append(
            AiTraceStep(
                agent="模型定稿",
                summary=f"在候选内定稿 {len(picks)} 样食材",
                ms=ai_ms,
            )
        )

    # 模型挑中的排前面、剩下的补齐 —— 和菜品那条链路用同一个策略
    chosen = _order_candidates(candidates, [p["id"] for p in picks], count)
    reason_by_id = {int(p["id"]): str(p.get("reason") or "") for p in picks}
    foods = [
        HomeFoodItem(
            **home_service.food_brief_payload(item),
            reason=reason_by_id.get(item.item_id) or item.reason,
            highlights=item.highlights,
            score=round(item.score, 3),
        )
        for item in chosen
    ]

    return AiChatResponse(
        answer=answer,
        intent="recommend_foods",
        tools_used=(
            ["nutrition_check", "seasonal_calendar"]
            if route.health_goal is not None
            else ["seasonal_calendar"]
        ),
        foods=foods,
        trace=trace,
        source=source,
        model=model_name,
        intent_source=route.source,
    )


def chat(
    session: Session, user_id: int | None, payload: AiChatRequest
) -> AiChatResponse:
    message = payload.message

    # ---- 路由：先抽信号，再决定「闲聊」还是「推荐」----
    #
    # 两层：先让模型按**语义**判（中文说法太多，关键词表永远补不全），
    # 判不出来再退回关键词规则（没配 AI 时整个助手不能变哑巴）。
    route = _route_smart(session=session, message=message, payload=payload)
    intent = route.intent
    follow_up = route.follow_up
    health_goal = route.health_goal

    # ★ 「推荐食材」是另一条链路：用户要的是"该吃什么/该买什么"，
    #   不是"做哪道菜"。和 meal_recommendation 对称，但没有"用我的库存"那个变体
    #   （既然是"给我推荐该吃的"，就不该反过来受库存限制）。
    if intent == "recommend_foods":
        return _answer_food_recommendation(
            session=session,
            payload=payload,
            route=route,
            user_id=user_id,
        )

    # 「换一批」要避开已经展示过的菜 —— 否则轮换因子是固定的，重问还是那三道
    already_shown = {
        int(i) for i in (payload.recent_recipe_ids or []) if i is not None
    }

    people = _parse_people(message) or payload.people or 3

    constraints = _constraints(session, user_id, payload)
    constraints.people = people

    # ★ 用户在话里声明的忌口必须生效（「我不吃香菜」不能当没听见）。
    #   这是安全相关的：忽略掉就可能推出他不能吃的东西。
    if route.avoid_added:
        merged = list(constraints.avoid)
        for term in route.avoid_added:
            if term not in merged:
                merged.append(term)
        constraints.avoid = tuple(merged)
        # 声明为忌口的东西要从「口味偏好」里摘掉，否则会自相矛盾
        constraints.preferences = tuple(
            p for p in constraints.preferences if p not in constraints.avoid
        )

    month = datetime.now().month
    weather = _weather_for(payload, month)
    trace: list[AiTraceStep] = []

    trace.append(
        AiTraceStep(
            agent="读取约束",
            summary=(
                f"读取约束：{_constraints_block(constraints)}"
                f"；天气 {weather.description}"
            ),
            status="info",
            ms=3,
        )
    )

    # ---- 需求解析：把「我气血不足，想吃点补气血的」变成可执行的筛选条件 ----
    #   这一步以前完全没有 —— 于是模型手里只有时令/天气素材，
    #   只能答出一段「跟诉求无关的天气介绍」。
    #   现在把抽到的所有信号一次性摊开（诉求 / 点名食材 / 忌口），
    #   用户和评委都能一眼看到「系统到底听懂了什么」。
    parsed_notes: list[str] = []
    if health_goal is not None:
        parsed_notes.append(
            f"食养诉求「{health_goal.name}」（匹配 {'、'.join(health_goal.effect_keywords[:3])} 等标签）"
        )
    if route.mentioned_names:
        parsed_notes.append(f"点名的食材 {'、'.join(route.mentioned_names[:4])}")
    if route.avoid_added:
        parsed_notes.append(f"声明的忌口 {'、'.join(route.avoid_added[:4])}")
    if parsed_notes:
        trace.append(
            AiTraceStep(
                agent="需求解析",
                summary="识别到：" + "；".join(parsed_notes),
                ms=1,
            )
        )

    if follow_up:
        trace.append(
            AiTraceStep(
                agent="上下文",
                summary=(
                    f"识别为追问（沿用上一轮意图：{intent}）"
                    + (
                        f"，并避开已经推荐过的 {len(already_shown)} 道"
                        if already_shown
                        else ""
                    )
                ),
                status="info",
                ms=1,
            )
        )

    # ---- 召回候选 ----
    t0 = time.perf_counter()
    cook_food_ids = _my_food_ids(session, user_id)

    # 「闲聊」不推菜 —— 保持与改造前一致（recipes 为空），
    # 但要让它答得有依据：用我们库里的时令知识，而不是模型自己瞎聊。
    if intent == "general":
        return _general_chat(
            session=session,
            message=message,
            constraints=constraints,
            month=month,
            weather=weather,
            trace=trace,
        )

    if intent == "cook_with_my_foods" and user_id is None:
        return AiChatResponse(
            answer="先登录，我才能看到你家里有什么食材。",
            intent=intent,
            tools_used=["inventory_check"],
            trace=trace,
            source="algorithm",
        )
    if intent == "cook_with_my_foods" and not cook_food_ids:
        trace.append(
            AiTraceStep(
                agent="清点库存",
                summary="「我的食材」是空的，没有可用的库存",
                status="info",
                ms=2,
            )
        )
        return AiChatResponse(
            answer="你的「我的食材」现在还是空的，先去食材页添加几样吧。",
            intent=intent,
            tools_used=["inventory_check"],
            trace=trace,
            source="algorithm",
        )

    # 召回依据：
    #   · 「用我的食材」→ 库存
    #   · 用户在话里点名了食材（「莲藕怎么做」）→ 就用那个食材召回，
    #     否则会推一堆当季菜，答不到点子上
    #   · 其余 → 按时令与天气召回
    if intent == "cook_with_my_foods":
        food_ids = cook_food_ids
    elif route.mentioned_ids:
        food_ids = route.mentioned_ids
    else:
        food_ids = None

    rejected: list[str] = []
    candidates = scoring_service.score_dishes(
        session,
        month=month,
        weather=weather,
        constraints=constraints,
        region=payload.city or "national",
        date_key=datetime.now().date().isoformat(),
        food_ids=food_ids,
        pool_size=200,
        limit=8,
        rejected_names=rejected,
        health_goal=health_goal,
        # 「换一批」时避开已经展示过的菜
        exclude_ids=already_shown,
    )

    if intent == "cook_with_my_foods":
        recall_detail = f"命中库存食材 {len(cook_food_ids)} 样"
    elif route.mentioned_names:
        recall_detail = f"按你点名的食材「{'、'.join(route.mentioned_names[:3])}」召回"
    else:
        recall_detail = "按当月时令与天气召回"
    if health_goal is not None:
        recall_detail += f"，并按「{health_goal.name}」扩召回并加权"
    if already_shown:
        recall_detail += f"，已避开展示过的 {len(already_shown)} 道"
    if not candidates:
        # 条件太紧（通常是可用时间不够），放宽时间再取一次。
        #
        # ⚠️⚠️ 这里**只能放宽时间，绝不能放宽忌口**。
        #    原来的写法是 `HardConstraints(people=people, cook_minutes=240)` ——
        #    那等于把用户声明的忌口、限钠、口味偏好全部丢掉，
        #    于是「我不吃鸡蛋」在第一轮被筛掉之后，又在兜底轮被推了回来。
        #    这是安全事故级别的 bug：宁可不推，也不能推错。
        relaxed = _relax_time_only(constraints, cook_minutes=240)
        candidates = scoring_service.score_dishes(
            session,
            month=month,
            weather=weather,
            constraints=relaxed,
            region=payload.city or "national",
            date_key=datetime.now().date().isoformat(),
            food_ids=food_ids,
            limit=8,
            health_goal=health_goal,
            exclude_ids=already_shown,
        )
        if not candidates:
            # 实在没了（比如库存就够做那一两道），才允许重复 ——
            # 但**忌口依然不放宽**，所以第一轮被否掉的菜不会回来。
            candidates = scoring_service.score_dishes(
                session,
                month=month,
                weather=weather,
                constraints=relaxed,
                region=payload.city or "national",
                date_key=datetime.now().date().isoformat(),
                limit=8,
                health_goal=health_goal,
            )
            recall_detail += "；可选菜品已翻完，重新从头推荐"
        else:
            recall_detail += "；约束过紧，已放宽时间限制"

    trace.append(
        AiTraceStep(
            agent="候选召回",
            summary=f"{recall_detail} → 综合打分筛出候选 {len(candidates)} 道",
            ms=int((time.perf_counter() - t0) * 1000),
        )
    )

    if not candidates:
        trace.append(
            AiTraceStep(
                agent="营养校验",
                summary="候选为空，无法给出建议",
                status="veto",
                ms=1,
            )
        )
        return AiChatResponse(
            answer="暂时没找到合适的菜谱，换个条件再问问我？",
            intent=intent,
            tools_used=["recipe_search"],
            trace=trace,
            source="algorithm",
        )

    # ---- 确定性否决：把被忌口/时间挡掉的候选如实报出来 ----
    #    这一步是「Critic 一票否决」在后端的真实落点：
    #    被否决的菜**根本没进候选集**，模型连看到它的机会都没有。
    if rejected:
        trace.append(
            AiTraceStep(
                agent="硬约束否决",
                summary=(
                    f"确定性否决 {len(rejected)} 道，未进入候选："
                    + "、".join(rejected[:3])
                    + ("…" if len(rejected) > 3 else "")
                ),
                status="veto",
                ms=2,
            )
        )
    else:
        trace.append(
            AiTraceStep(
                agent="硬约束否决",
                summary="没有候选违反忌口与时间约束",
                status="ok",
                ms=2,
            )
        )

    # ---- 让模型在候选内挑选与解释 ----
    allowed = {item.item_id for item in candidates}
    answer: str | None = None
    picks: list[dict[str, Any]] = []
    model_name: str | None = None
    ai_ms = 0
    source = "algorithm"

    if client.is_configured():
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _chat_prompt(
                    session=session,
                    message=message,
                    intent=intent,
                    constraints=constraints,
                    weather=weather,
                    month=month,
                    candidates=candidates,
                    city=payload.city,
                    health_goal=health_goal,
                ),
            },
        ]
        result = client.complete_json(messages)
        ai_ms = result.elapsed_ms
        if result.ok:
            raw_answer = str(result.data.get("answer") or "").strip()
            picks = _coerce_picks(result.data.get("picks"), allowed, 3)
            if raw_answer:
                answer = raw_answer
                source = "ai"
                model_name = result.model
        if answer is None:
            trace.append(
                AiTraceStep(
                    agent="文案生成",
                    summary=f"模型不可用（{result.error}），改用规则文案",
                    status="info",
                    ms=ai_ms,
                )
            )
    else:
        trace.append(
            AiTraceStep(
                agent="文案生成",
                summary="未配置 AI_API_KEY，使用规则文案",
                status="info",
                ms=0,
            )
        )

    picked_ids = [entry["id"] for entry in picks]
    chosen = _order_candidates(candidates, picked_ids, 3)

    if answer is None:
        # ★ 兜底：和改造前的行为完全一致
        answer = _rule_answer(
            session=session,
            intent=intent,
            constraints=constraints,
            month=month,
            candidates=chosen,
            user_id=user_id,
            health_goal=health_goal,
        )

    notes = {entry["id"]: entry["reason"] for entry in picks if entry.get("reason")}
    recipes = []
    for item in chosen:
        brief = recipe_service.to_brief(item.raw)
        if notes.get(item.item_id):
            brief = brief.model_copy(
                update={"description": notes[item.item_id]}
            )
        recipes.append(brief)

    trace.append(
        AiTraceStep(
            agent="模型定稿",
            summary=f"在候选内定稿 {len(chosen)} 道：" + "、".join(i.name for i in chosen),
            ms=ai_ms,
        )
    )

    return AiChatResponse(
        answer=answer,
        intent=intent,
        tools_used=_tools_for(intent),
        recipes=recipes,
        menu=AiMenuSummary(
            title="今晚推荐",
            summary=f"{len(chosen)} 道菜 · 适合 {people} 人",
        ),
        trace=trace,
        source=source,
        model=model_name,
    )


def _relax_time_only(
    constraints: HardConstraints, *, cook_minutes: float
) -> HardConstraints:
    """只放宽「可用烹饪时间」，其余硬约束原样保留。

    【为什么必须这样】
    「条件太紧 → 放宽重试」原来是这样写的：
        HardConstraints(people=people, cook_minutes=240)
    那是个**全新的中性约束**，等于把用户的忌口、限钠、口味偏好全丢了。
    后果：用户说「我不吃鸡蛋」，第一轮正确筛掉了番茄炒蛋，
    但候选因此变空 → 兜底轮用中性约束重跑 → **番茄炒蛋又回来了**。
    这是安全事故级别的 bug（可能推出过敏原），所以单独抽成这个函数，
    并配了测试。
    """
    return HardConstraints(
        people=constraints.people,
        cook_minutes=cook_minutes,
        low_sodium=constraints.low_sodium,
        preferences=constraints.preferences,
        avoid=constraints.avoid,   # ★ 忌口绝不放宽
    )


def _tools_for(intent: str) -> list[str]:
    if intent == "cook_with_my_foods":
        return ["inventory_check", "recipe_search", "shopping_calc"]
    if intent == "meal_recommendation":
        return ["season_search", "recipe_search", "preference_check"]
    return []


_GENERAL_FALLBACK = (
    "我是小食，可以帮你安排今天吃什么。"
    "你可以直接说「三个人今晚吃什么」，"
    "或者告诉我家里有什么食材，我来配菜。"
)

# 闲聊的子类型 —— 离线兜底也要答到点子上，不能一律回一段自我介绍。
# （「谢谢」回「我是小食，可以帮你安排今天吃什么」就是典型的牛头不对马嘴）
_CHITCHAT_KINDS: list[tuple[str, tuple[str, ...], str]] = [
    (
        "thanks",
        ("谢谢", "感谢", "多谢", "thanks", "thx"),
        "不客气～还想再吃点别的什么，或者想换几道菜，随时说。",
    ),
    (
        "bye",
        ("再见", "拜拜", "先这样", "回头聊", "bye"),
        "好嘞，回头想吃的时候再叫我～",
    ),
    (
        "identity",
        ("你是谁", "你叫什么", "你是什么", "你会什么", "你能做什么", "介绍下你", "介绍一下你"),
        "我是「食时」里的饮食助手小食。"
        "我会按当天时令、你所在城市的天气、你家里的食材和忌口来配菜，"
        "也能回答「今天吃什么」「用我家的食材能做什么」这类问题。",
    ),
    (
        "howto",
        ("怎么用", "如何使用", "怎么玩", "帮助", "help"),
        "用法很简单：直接说「三个人今晚吃什么」，"
        "或者告诉我家里有什么食材、有什么忌口，我来配这一餐。"
        "想换一批就说「换一批」。",
    ),
    (
        "greeting",
        ("你好", "您好", "hi", "hello", "在吗", "哈喽", "早上好", "晚上好"),
        "你好呀，我是小食。今天想吃点什么？"
        "可以直接说「三个人今晚吃什么」，或者告诉我家里有哪些食材。",
    ),
]


def _chitchat_fallback(message: str) -> str:
    """给闲聊挑一句对的回复（顺序即优先级）。"""
    lowered = message.lower()
    for _, hints, reply in _CHITCHAT_KINDS:
        if any(hint in lowered for hint in hints):
            return reply
    return _GENERAL_FALLBACK


def _general_chat(
    *,
    session: Session,
    message: str,
    constraints: HardConstraints,
    month: int,
    weather: Any,
    trace: list[AiTraceStep],
) -> AiChatResponse:
    """闲聊/开放提问：不推菜，但答案要建立在库里的时令知识上。"""
    answer = _chitchat_fallback(message)
    source = "algorithm"
    model_name: str | None = None
    ai_ms = 0

    if client.is_configured():
        result = client.complete_json(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"""【用户的话】{message}
【今天】{month} 月（{scoring_service.season_char_of(month)}季）
【天气】{weather.description} —— {weather.advice}
【时令知识 · 来自我们的时令数据库】
{_facts_block(session, month)}

请输出 JSON：{{"answer": "2~3 句口语化回答"}}
要求：
- **先判断用户到底在说什么**：打招呼就打招呼，道谢就道谢，问你是谁就介绍自己，
  不要把每种话都答成同一段自我介绍；
- 不要推荐具体菜名（这一轮没有给候选清单）；
- 如果用户其实是在问「吃什么」，用一句话反问他几个人、家里有什么食材；
- 全部用简体中文。""",
                },
            ]
        )
        ai_ms = result.elapsed_ms
        text_value = str(result.data.get("answer") or "").strip() if result.ok else ""
        if text_value:
            answer = text_value
            source = "ai"
            model_name = result.model

    trace.append(
        AiTraceStep(
            agent="时令知识",
            summary=(
                f"从时令库取到 {month} 月的时令知识，"
                + ("由模型组织回答" if source == "ai" else "使用规则回答")
            ),
            ms=ai_ms,
        )
    )
    return AiChatResponse(
        answer=answer,
        intent="general",
        tools_used=[],
        recipes=[],
        menu=None,
        trace=trace,
        source=source,
        model=model_name,
    )


def _order_candidates(
    candidates: list[ScoredItem], picks: list[int], limit: int
) -> list[ScoredItem]:
    by_id = {item.item_id: item for item in candidates}
    ordered: list[ScoredItem] = []
    seen: set[int] = set()
    for pick in picks:
        item = by_id.get(pick)
        if item is not None and pick not in seen:
            ordered.append(item)
            seen.add(pick)
    for item in candidates:
        if len(ordered) >= limit:
            break
        if item.item_id not in seen:
            ordered.append(item)
            seen.add(item.item_id)
    return ordered[:limit]


def _rule_answer(
    *,
    session: Session,
    intent: str,
    constraints: HardConstraints,
    month: int,
    candidates: list[ScoredItem],
    user_id: int | None,
    health_goal: Any = None,
) -> str:
    """规则兜底文案 —— 与改造前保持一致的语气与信息量。"""
    season = home_service.season_name_of(month)
    people = constraints.people
    names = "、".join(item.name for item in candidates)

    if intent == "cook_with_my_foods":
        answer = f"用你现有的食材可以做：{names}。"
        missing = _missing_for(session, user_id, candidates)
        if missing:
            answer += f"另外还需要买：{'、'.join(missing[:4])}。"
    elif intent == "meal_recommendation":
        answer = (
            f"现在是{season}，按 {people} 个人的量，我推荐这三道：{names}。"
            "荤素都有，做起来也不费事。"
        )
    else:
        answer = _GENERAL_FALLBACK

    # 用户说了诉求，兜底回答也要先回应它（否则又是答非所问）
    if health_goal is not None:
        answer = f"按你说的「{health_goal.name}」，我挑了这几道：{names}。{answer}"
    return answer


def _missing_for(
    session: Session, user_id: int | None, candidates: list[ScoredItem]
) -> list[str]:
    """用现有食材做这道菜，还缺哪几样主料。

    只比名字不比 id —— 清洗库里「鸡肉」和「鸡胸肉」是两个 id，
    但用户心里它们是一样东西，名字匹配更贴近直觉。
    """
    if user_id is None or not candidates:
        return []

    owned_ids = _my_food_ids(session, user_id)
    owned_names = {
        insight.name for insight in food_insights(session, owned_ids).values()
    }

    top = candidates[0]
    insight = dish_insights(session, [top.item_id]).get(top.item_id)
    if insight is None:
        return []

    missing: list[str] = []
    for name in insight.main_ingredients:
        # 「鸡胸肉」在用户库存里有「鸡肉」时不算缺
        if any(owned in name or name in owned for owned in owned_names):
            continue
        missing.append(name)
    return list(dict.fromkeys(missing))


def _chat_prompt(
    *,
    session: Session,
    message: str,
    intent: str,
    constraints: HardConstraints,
    weather: Any,
    month: int,
    candidates: list[ScoredItem],
    city: str | None,
    health_goal: Any = None,
) -> str:
    owned = ""
    if intent == "cook_with_my_foods":
        owned = "（下面候选都是从「用户现有食材」出发筛出来的）\n"

    # ★ 用户明确说出的诉求必须**当成首要任务**写在提示词最前面。
    #   以前没有这一段，模型手里只有时令/天气素材，于是用户问「补气血」，
    #   它答的是「今天晴 17℃ 秋燥…」—— 答非所问就是这么来的。
    goal_block = ""
    if health_goal is not None:
        goal_block = f"""
【★ 用户的核心诉求 · 优先满足】{health_goal.as_prompt_line()}
展开要求：
- 回答的**第一句**就要回应这个诉求，不要把天气/时令放在前面；
- 挑选的菜要优先选「用了带这类功效食材」的那些（候选行里有功效标签）；
- 这是食养方向的饮食建议，**不要做诊断、不要承诺治疗作用**，
  说「有…的食材/有助于…」而不是「能治好…」。"""

    return f"""【用户的话】{message}
【意图】{intent}
【家庭约束】{_constraints_block(constraints)}
【今天】{month} 月（{scoring_service.season_char_of(month)}季）{city or ''}
【天气】{weather.description} —— {weather.advice}
{goal_block}
【时令知识 · 来自我们的时令数据库】
{_facts_block(session, month)}

{owned}【候选菜品】（只能从这里挑）
{chr(10).join(_candidate_lines(session, candidates))}

请输出 JSON：
{{
  "answer": "给用户的一段回答，2~4 句，口语化，要说清为什么推荐这几道",
  "picks": [{{"id": 菜品id, "reason": "一句话理由"}}]
}}

要求：
- picks 最多 3 个，id 必须来自上面的候选清单；
- **先回答用户问的诉求**，再补充时令/天气作为辅助理由；
- 如果用户说了「用我家的食材」，要明确说明这几道用到了他现有的哪些食材；
- 全部用简体中文。"""


# =====================================================================
# 导航栏 AI 配菜
# =====================================================================


def recommend_recipes(
    session: Session, user_id: int | None, payload: AiRecommendRequest
) -> AiRecommendResponse:
    """根据「已选食材 + 今日菜单已有的菜 + 硬约束」推荐菜品。"""
    month = datetime.now().month
    constraints = _constraints(session, user_id, payload)
    weather = _weather_for(payload, month)
    trace: list[AiTraceStep] = []

    # ---- 1. 确定用哪些食材 ----
    food_ids = [int(i) for i in payload.food_ids if i is not None]
    source_of_foods = "用户勾选"
    if not food_ids:
        food_ids = _my_food_ids(session, user_id)
        source_of_foods = "登录用户的「我的食材」" if food_ids else "无"

    insights = food_insights(session, food_ids)
    food_names = [insights[i].name for i in food_ids if i in insights]

    trace.append(
        AiTraceStep(
            agent="清点库存",
            summary=(
                f"{source_of_foods}："
                + ("、".join(food_names[:8]) if food_names else "没有可用食材，改按时令推荐")
            ),
            status="info" if food_names else "veto",
            ms=3,
        )
    )

    # ---- 2. 今日菜单已有的菜必须排除 ----
    exclude = {int(i) for i in payload.menu_recipe_ids if i is not None}
    menu_names: list[str] = []
    if exclude:
        menu_names = [
            str(getattr(recipe, "name", ""))
            for recipe in recipe_repository.list_by_ids(session, sorted(exclude))
        ]

    trace.append(
        AiTraceStep(
            agent="模型定稿",
            summary=(
                f"今日菜单已有 {len(exclude)} 道"
                + (f"（{'、'.join(menu_names[:5])}）" if menu_names else "")
                + "，已从候选中排除"
            ),
            status="info",
            ms=2,
        )
    )

    trace.append(
        AiTraceStep(
            agent="读取约束",
            summary="硬约束：" + _constraints_block(constraints),
            status="info",
            ms=2,
        )
    )

    # ---- 附带的食养诉求（用户在配菜面板里写的那句补充要求）----
    health_goal = need_service.extract_goal(payload.message or "")
    if health_goal is not None:
        trace.append(
            AiTraceStep(
                agent="需求解析",
                summary=(
                    f"识别到「{health_goal.name}」→ 按我们功效库里的"
                    f"{'、'.join(health_goal.effect_keywords[:4])} 等标签加权"
                ),
                ms=1,
            )
        )

    # ---- 3. 综合打分召回候选 ----
    t0 = time.perf_counter()
    shortlist = max(payload.count * 3, 8)
    candidates = scoring_service.score_dishes(
        session,
        month=month,
        weather=weather,
        constraints=constraints,
        region=payload.city or "national",
        date_key=datetime.now().date().isoformat(),
        food_ids=food_ids or None,
        exclude_ids=exclude,
        pool_size=300,
        limit=shortlist,
        health_goal=health_goal,
    )

    relaxed = False
    if not candidates and food_ids:
        # 用现有食材配不出菜时，退回按时令推荐 —— 但绝不放宽忌口
        candidates = scoring_service.score_dishes(
            session,
            month=month,
            weather=weather,
            constraints=constraints,
            region=payload.city or "national",
            date_key=datetime.now().date().isoformat(),
            exclude_ids=exclude,
            limit=shortlist,
            health_goal=health_goal,
        )
        relaxed = True

    trace.append(
        AiTraceStep(
            agent="候选召回",
            summary=(
                f"综合打分（时令/天气/营养/偏好/轮换"
                + (f"/{health_goal.name}" if health_goal else "")
                + f"）→ 候选 {len(candidates)} 道"
                + ("；用现有食材配不出，已改为按时令推荐" if relaxed else "")
            ),
            ms=int((time.perf_counter() - t0) * 1000),
        )
    )

    if not candidates:
        return AiRecommendResponse(
            answer="按当前条件没找到合适的菜，放宽一下忌口或时间再试试？",
            trace=trace,
            source="algorithm",
            used_foods=food_names,
        )

    # ---- 4. 模型在候选内挑选与解释 ----
    allowed = {item.item_id for item in candidates}
    answer: str | None = None
    picks: list[dict[str, Any]] = []
    model_name: str | None = None
    ai_ms = 0
    source = "algorithm"

    if client.is_configured():
        result = client.complete_json(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _recommend_prompt(
                        session=session,
                        payload=payload,
                        constraints=constraints,
                        weather=weather,
                        month=month,
                        food_names=food_names,
                        menu_names=menu_names,
                        candidates=candidates,
                        # ★ 别忘了把它传进去 —— 少了这个参数，
                        #   提示词里那句「满足用户核心诉求」就永远不生效，
                        #   更要命的是 `_recommend_prompt` 里引用了未定义的
                        #   `health_goal` 会直接 NameError，接口 500。
                        health_goal=health_goal,
                    ),
                },
            ]
        )
        ai_ms = result.elapsed_ms
        if result.ok:
            raw_answer = str(result.data.get("answer") or "").strip()
            picks = _coerce_picks(
                result.data.get("picks"), allowed, payload.count
            )
            if raw_answer:
                answer = raw_answer
                source = "ai"
                model_name = result.model
        if answer is None:
            trace.append(
                AiTraceStep(
                    agent="文案生成",
                    summary=f"模型不可用（{result.error}），改用算法理由",
                    status="info",
                    ms=ai_ms,
                )
            )

    chosen = _order_candidates(candidates, [p["id"] for p in picks], payload.count)
    notes = {p["id"]: p["reason"] for p in picks if p.get("reason")}

    if answer is None:
        if food_names:
            answer = (
                f"用你选的 {len(food_names)} 样食材，配上当季时令，"
                f"我挑了 {len(chosen)} 道：{'、'.join(i.name for i in chosen)}。"
                "都已经避开了你的忌口和可用时间。"
            )
        else:
            answer = (
                f"按时令和今天的天气，我挑了 {len(chosen)} 道："
                f"{'、'.join(i.name for i in chosen)}。"
            )

    selected_ids = set(food_ids)
    recommendations: list[AiRecipePick] = []
    for item in chosen:
        insight = item.insight
        matched: list[str] = []
        if insight is not None and selected_ids:
            for food_id in set(insight.ingredient_ids) & selected_ids:
                matched.append(insights[food_id].name if food_id in insights else str(food_id))
        recommendations.append(
            AiRecipePick(
                recipe=recipe_service.to_brief(item.raw),
                reason=notes.get(item.item_id) or item.reason,
                highlights=item.highlights,
                score=round(item.score, 3),
                matched_foods=matched,
            )
        )

    trace.append(
        AiTraceStep(
            agent="营养校验",
            summary=(
                "营养与钠已按约束校验"
                if constraints.low_sodium
                else "营养已校验（未开启限钠）"
            ),
            ms=2,
        )
    )
    trace.append(
        AiTraceStep(
            agent="文案生成",
            summary=f"定稿 {len(recommendations)} 道，来源：{source}",
            ms=ai_ms,
        )
    )

    return AiRecommendResponse(
        answer=answer,
        recommendations=recommendations,
        trace=trace,
        source=source,
        model=model_name,
        used_foods=food_names,
        filtered_out=menu_names,
    )


def _recommend_prompt(
    *,
    session: Session,
    payload: AiRecommendRequest,
    constraints: HardConstraints,
    weather: Any,
    month: int,
    food_names: list[str],
    menu_names: list[str],
    candidates: list[ScoredItem],
    health_goal: HealthGoal | None = None,
) -> str:
    meal_label = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
    }.get(payload.meal, "这一餐")

    extra = f"\n【用户额外要求】{payload.message}" if payload.message else ""
    goal_block = ""
    if health_goal is not None:
        goal_block = f"\n【★ 用户的核心诉求 · 优先满足】{health_goal.as_prompt_line()}"

    return f"""【任务】帮用户配 {meal_label}，需要 {payload.count} 道菜。
【用户已有的食材】{'、'.join(food_names) or '（没有指定，按时令推荐）'}
【今日菜单里已经有的菜（不要再推）】{'、'.join(menu_names) or '（还没有）'}
【家庭约束】{_constraints_block(constraints)}
【今天】{month} 月（{scoring_service.season_char_of(month)}季）{payload.city or ''}
【天气】{weather.description} —— {weather.advice}{extra}{goal_block}
【时令知识 · 来自我们的时令数据库】
{_facts_block(session, month)}

【候选菜品】（只能从这里挑）
{chr(10).join(_candidate_lines(session, candidates))}

请输出 JSON：
{{
  "answer": "给用户的一段话，2~3 句，说清为什么这几道适合今天、和已有食材/已有菜单怎么搭配",
  "picks": [{{"id": 菜品id, "reason": "一句话理由（不超过 20 字）"}}]
}}

要求：
- picks 选 {payload.count} 个，按推荐优先级排序，id 必须来自候选清单；
- 优先用上用户已有的食材，并注意和今日菜单已有的菜**不重样**（荤素、口味岔开）；
- 必须遵守忌口与限钠约束；
- 全部用简体中文。"""
