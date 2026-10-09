"""★ 综合打分算法 —— 首页与 AI 配菜的「选什么」全在这里。

【为什么要有这一层：AI 不能从全库自由生成】
清洗库有 590 个核心食材、10000 道菜。如果直接把库交给大模型让它「推荐几道」，
它一定会编出不存在的菜名、或者推荐一道需要炖三小时而家里只有 45 分钟的菜。
所以本项目的分工是：

    算法（本文件）  ── 从我们自己的库里筛候选、打分、排序、执行硬约束
    大模型（app/ai）── 只在算法给出的候选集里挑选与解释，不许新增

这样 AI 的每一步输出都能被验证（返回的 id 不在候选集里就直接丢弃），
也不会出现「AI 幻觉出一道危险的菜」这种事。

【四个输入，全部来自数据库或环境，没有一处是写死的】
  1. 当天时令  ——  seasonal_food / seasonal_calendar（清洗库的时令食材表）
  2. 定位天气  ——  weather_service（温度/降水 → 温热、清爽、祛湿、润燥）
  3. 营养与标签 ——  ingredients 的每 100g 营养 + dishes 的整菜营养、tags_json
  4. 家庭硬约束 ——  忌口（硬过滤）、限钠、人数、可用烹饪时间、口味偏好

【「每天不一样、但同地区同一天一样」是怎么做到的】
每个候选带一个 `daily_salt` —— 用 sha256(地区 + 日期 + 候选名) 归一化到 0~1。
它是**确定性的**：同样的地区 + 同样的日期，算出来永远同一个值，
所以同地区同一天的所有用户看到完全一样的顺序（也因此那一次 AI 调用可以缓存）；
日期一变，salt 全变，排序就换了。

⚠️ 一个刻意的取舍：salt 只在**同一应季档位内**参与排序，不会把 9 月 95 分的
   莲藕挤到 90 分的南瓜后面 —— 时令是主序，轮换是主序内部的调节。
   线上清洗库里同一个档位的候选有几十个（10 月有 46 个 season_score=100 的
   时令食材），所以轮换效果很明显；本地演示种子只有 6 个食材、分数各不相同，
   轮换就看不出来 —— 这是数据量差异，不是算法没生效。
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session

from app.data.dish_images import has_image
from app.repositories import food_repository, recipe_repository
from app.repositories.catalog_insight_repository import (
    DishInsight,
    FoodInsight,
    dish_insights,
    dishes_using_foods,
    food_insights,
    foods_matching_effects,
    seasonal_linked_dish_ids,
)
from app.services.need_service import HealthGoal, effect_keywords_of, goal_fit
from app.services.weather_service import WeatherContext

# =====================================================================
# 权重 —— 全部集中在这里，改权重不用翻代码
# =====================================================================

W_SEASON = 3.0       # 时令（应季程度）
W_WEATHER = 1.6      # 天气适配
W_NUTRITION = 1.2    # 营养均衡 / 限钠
W_PREFERENCE = 1.8   # 家庭成员口味偏好
W_POPULARITY = 0.8   # 大众接受度（被多少道菜用到）
W_DAILY = 0.9        # 每日轮换（同地区同一天恒定）
# 用户明确说出的食养诉求（「想吃点补气血的」）。
# 权重给得比天气还高 —— 用户主动说出口的需求，优先级应该压过环境因素。
W_GOAL = 2.4

# 有配图的菜优先。
#
# 【这是展示层的考量，不是营养/口味判断】
# 精选目录里 700 道有 481 道配了图（69%）。不优先的话，首页那 3 道很容易
# 全落在没图的那 31% 上，卡片就成了三块「暂无配图」。
# 权重刻意给小（0.6，比人气还低）：它只是**同等条件下**的偏好，
# 绝不能盖过时令(3.0)/天气(1.6)/营养(1.2)/口味偏好(1.8)。
W_IMAGE = 0.6

# 每日轮换的「池子」大小。
#
# 【为什么需要池子，而不是直接按总分排序】
# 直接按总分排序的话，第一名永远是同一个（线上 10 月实测：连着 7 天
# 都是「山药、莲藕」打头，只有第三个在换）——「每天不一样」就形同虚设。
# 所以改成：同一应季档位里，先按质量取前 N 个组成池子，**再按当日轮换因子
# 在池子内排序**。这样既保住了质量下限（池子外的差候选永远上不来），
# 又让每天真正换一批。
#
# 太大 → 每天还是那几样；太小 → 质量参差不齐的东西也会被推上来。
ROTATE_POOL_FOOD = 14
ROTATE_POOL_DISH = 18

# 清洗库里混进来的一批「页面营销标题」（如「零难度还巨好吃的日式关东煮or火锅」）。
# 实测：10000 道菜里，标题长度 > 16 的有 383 道，叠加营销关键词后共 461 道（4.6%）。
#
# 处理方式是【从推荐候选中剔除】而不是改库、也不是降权：
#   · 降权试过了，不够 —— 它照样能挤进前 18 名的池子，首页还是会出现
#     「零难度还巨好吃的日式关东煮or火锅or蔬菜汤」这种标题，观感很差；
#   · 但也不能从库里删/改 —— 那是数据交付方的原始数据，
#     而且这些菜本身是正常的，用户在菜谱列表里搜得到就行。
# 所以只在「推荐」这条链路上不认它们。中文菜名极少超过 16 个字，
# 超过的基本都是抓来的页面标题。
_DISH_NAME_NOISE = (
    "零难度", "巨好吃", "就会爱上", "一学就会", "懒人", "手残", "秒杀",
    "好吃到", "绝了", "必备", "秘诀", "超简单", "一锅", "秘制",
    # 抓取页面带下来的品牌/栏目前缀，如「江阿姨菜谱-泰式柠檬酸菜鱼」
    "菜谱", "的做法", "教程", "视频",
)
_DISH_NAME_MAX = 15

# 抓取来的标题里常见的分隔符（真菜名里不会出现「|」）
_DISH_NAME_BAD_CHARS = ("|",)


def is_recommendable_dish_name(name: str) -> bool:
    """菜名是否适合出现在推荐位上。

    注意这是**推荐链路的准入条件**，不是数据清洗 ——
    库里那几百道菜一条都没动，走 /api/recipes 列表和搜索照样能看到。
    """
    if not name:
        return False
    if len(name) > _DISH_NAME_MAX:
        return False
    if any(char in name for char in _DISH_NAME_BAD_CHARS):
        return False
    return not any(noise in name for noise in _DISH_NAME_NOISE)

# 忌口命中直接出局的底线。这些词命中的菜一律不进候选池。
_DEFAULT_AVOID_SYNONYMS: dict[str, list[str]] = {
    "辛辣": ["辣", "辣椒", "花椒", "麻辣", "香辣", "干辣椒", "豆瓣酱", "泡椒", "咖喱"],
    "辣": ["辣", "辣椒", "花椒", "麻辣", "香辣"],
    "海鲜": ["虾", "蟹", "贝", "蛤", "蚝", "鱿鱼", "章鱼", "海参", "鲍"],
    "牛羊肉": ["牛", "羊"],
    "香菜": ["香菜", "芫荽"],
    "内脏": ["肝", "腰", "肚", "肠", "心", "肺"],
    "花生": ["花生", "花生酱"],
    "鸡蛋": ["鸡蛋", "蛋液", "蛋清", "蛋黄"],
    "乳制品": ["牛奶", "奶油", "黄油", "芝士", "奶酪"],
    "油腻": ["红烧肉", "五花肉", "炸", "油焖"],
}

# 天气意图 → 食材/菜品的适配关键词（来自清洗库真实的 effects_json 与 tags_json 词表）
_WEATHER_KEYWORDS: dict[str, list[str]] = {
    "cold": ["温", "暖", "补", "养", "姜", "羊肉", "牛肉", "鸡", "枣", "桂圆", "山药", "南瓜", "驱寒", "气血"],
    "snow": ["温", "暖", "补", "炖", "羊肉", "牛肉", "枣", "桂圆", "姜", "滋补"],
    "hot": ["清热", "解暑", "生津", "止渴", "利尿", "苦瓜", "冬瓜", "黄瓜", "绿豆", "西瓜", "凉", "瘦身", "低脂", "爽口"],
    "rain": ["祛湿", "健脾", "利水", "薏", "赤小豆", "冬瓜", "姜", "陈皮", "消肿", "开胃"],
    "dry": ["润", "生津", "止渴", "止咳", "梨", "百合", "银耳", "莲藕", "蜂蜜", "滋阴", "养肺", "清燥"],
    "mild": [],
    "unknown": [],
}

# 菜品标签 → 天气适配
_DISH_WEATHER_TAGS: dict[str, list[str]] = {
    "cold": ["汤羹", "汤", "炖", "红烧", "煲", "热菜", "焖", "砂锅"],
    "snow": ["汤羹", "汤", "炖", "煲", "红烧", "焖"],
    "hot": ["凉菜", "凉拌", "清淡", "蒸", "减肥", "素菜", "素食", "爽口"],
    "rain": ["汤羹", "汤", "炖", "清淡", "蒸"],
    "dry": ["汤羹", "汤", "炖", "清淡", "蒸", "粥"],
    "mild": [],
    "unknown": [],
}

# 低钠约束下，整菜钠含量的参照线（mg/人/餐）。
# 《中国居民膳食指南》建议每日钠 < 2000mg，正餐大约占一半。
_SODIUM_PER_MEAL_TARGET_MG = 800.0


@dataclass(slots=True)
class HardConstraints:
    """家庭硬约束 —— 和前端 FamilyProfile 一一对应。"""

    people: int = 3
    cook_minutes: float = 45
    low_sodium: bool = False
    preferences: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()

    @classmethod
    def from_profile(cls, profile: Any) -> HardConstraints:
        """从任意「长得像家庭档案」的对象构造 —— 前端传什么都不会炸。"""
        if profile is None:
            return cls()
        return cls(
            people=max(int(getattr(profile, "people", 3) or 3), 1),
            cook_minutes=float(getattr(profile, "cook_minutes", 45) or 45),
            low_sodium=bool(getattr(profile, "low_sodium", False)),
            preferences=tuple(getattr(profile, "preferences", ()) or ()),
            avoid=tuple(getattr(profile, "avoid", ()) or ()),
        )


@dataclass(slots=True)
class ScoredItem:
    """打分结果。raw 是可直接交给 to_brief() 的库对象。"""

    raw: Any
    item_id: int
    name: str
    score: float
    reason: str
    factors: dict[str, float] = field(default_factory=dict)
    insight: FoodInsight | DishInsight | None = None
    # 命中了哪些因素，前端可以做成小标签展示
    highlights: list[str] = field(default_factory=list)
    # 不含「每日轮换」那一项的质量分 —— 池子的排序用它，
    # 这样天气/营养/偏好这些真信号不会被轮换因子污染。
    quality: float = 0.0
    # 档位：食材用应季程度，菜品恒为 0。档位是主序，轮换只在档位内部发生。
    band: float = 0.0


def _select_with_rotation(
    items: list[ScoredItem], *, limit: int, pool_size: int
) -> list[ScoredItem]:
    """档位为主序；档位内部「质量取前 N → 当日轮换排序」。

    这是「同地区同一天一样、跨天不一样」的落点：
      · 质量排序只用来**决定谁有资格进池子**（不含轮换因子，所以是稳定的）
      · 池子内按 `factors["daily"]` 排序 —— 它是 sha256(地区+日期+名字)，
        确定性，但随日期全变
    """
    if limit <= 0:
        return []

    ordered = sorted(items, key=lambda item: (-item.band, -item.quality, item.item_id))
    result: list[ScoredItem] = []
    index = 0
    while index < len(ordered) and len(result) < limit:
        band = ordered[index].band
        group: list[ScoredItem] = []
        while index < len(ordered) and ordered[index].band == band:
            group.append(ordered[index])
            index += 1

        pool = group[:pool_size]
        pool.sort(
            key=lambda item: (-item.factors.get("daily", 0.0), -item.quality, item.item_id)
        )
        for item in pool:
            if len(result) >= limit:
                break
            result.append(item)
    return result


def _select_by_relevance(
    items: list[ScoredItem], *, food_ids: list[int], limit: int
) -> list[ScoredItem]:
    """★ 查询式场景：按「用上了你几样食材」排序，**不做每日轮换**。

    为什么不能对「用我的食材能做什么」也用轮换：
        用户明确说「我有莲藕」，那他要的是能用莲藕的菜（莲藕排骨汤），
        而不是「今天轮到哪道菜」。轮换在这里会把最相关的菜挤出去 ——
        实测就是这样把「莲藕排骨汤」挤掉了。
    所以这里：命中食材数优先 → 质量 → id。结果是确定的，
    同一个人同样的食材，什么时候问都一样（这对「配菜」是优点，不是缺点）。
    """
    if limit <= 0:
        return []
    wanted = {int(i) for i in food_ids if i is not None}

    def overlap(item: ScoredItem) -> int:
        if not wanted or item.insight is None:
            return 0
        ids = set(getattr(item.insight, "ingredient_ids", None) or [])
        return len(ids & wanted)

    ordered = sorted(
        items, key=lambda item: (-overlap(item), -item.quality, item.item_id)
    )
    return ordered[:limit]


# =====================================================================
# 工具
# =====================================================================


def season_char_of(month: int) -> str:
    """月份 → 单字季节。和 seasonal_food.season 的口径一致。"""
    if 3 <= month <= 5:
        return "春"
    if 6 <= month <= 8:
        return "夏"
    if 9 <= month <= 11:
        return "秋"
    return "冬"


def daily_salt(*parts: Any) -> float:
    """确定性的 0~1 轮换因子。

    同样的入参永远得到同一个值 —— 这是「同地区同一天所有人看到一样」
    的实现基础，也是「每天不一样」的来源（日期是入参之一）。
    """
    key = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def _avoid_terms(avoid: tuple[str, ...]) -> list[str]:
    terms: list[str] = []
    for word in avoid:
        word = word.strip()
        if not word:
            continue
        terms.append(word)
        terms.extend(_DEFAULT_AVOID_SYNONYMS.get(word, []))
    return list(dict.fromkeys(terms))


def _haystack(*parts: Any) -> str:
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, (list, tuple, set)):
            chunks.extend(str(item) for item in part)
        elif part is not None:
            chunks.append(str(part))
    return " ".join(chunks)


def _hits_avoid(terms: list[str], *parts: Any) -> str | None:
    if not terms:
        return None
    haystack = _haystack(*parts)
    for term in terms:
        if term and term in haystack:
            return term
    return None


def _keyword_score(keywords: list[str], *parts: Any) -> float:
    """命中关键词的比例（0~1）。不做加权，命中越多越贴合天气。"""
    if not keywords:
        return 0.0
    haystack = _haystack(*parts)
    hits = sum(1 for word in keywords if word in haystack)
    # 命中 3 个就到 1.0 —— 再多没有额外信息量
    return min(hits / 3.0, 1.0)


def _log_norm(value: int, ceiling: int) -> float:
    if value <= 0 or ceiling <= 0:
        return 0.0
    return math.log1p(value) / math.log1p(ceiling)


def _preference_score(preferences: tuple[str, ...], *parts: Any) -> float:
    if not preferences:
        return 0.0
    haystack = _haystack(*parts)
    hits = sum(1 for word in preferences if word and word in haystack)
    return min(hits / max(len(preferences), 1), 1.0)


def _fmt(value: float | None, unit: str = "") -> str:
    if value is None:
        return "—"
    number = round(value)
    return f"{number}{unit}"


# =====================================================================
# 食材打分
# =====================================================================


def score_foods(
    session: Session,
    *,
    month: int,
    weather: WeatherContext,
    constraints: HardConstraints,
    region: str | None = None,
    date_key: str = "",
    pool_size: int = 80,
    limit: int = 3,
    health_goal: Any = None,
    exclude_ids: set[int] | None = None,
) -> list[ScoredItem]:
    """按综合打分挑出今天的推荐食材（按分数降序）。

    `health_goal`（食养诉求）会做两件事：
      1. **扩大召回**：光看当季食材的话，候选里可能压根没有「补气血」的食材，
         再好的排序也救不回来。所以把 effects_json 命中诉求关键词的食材
         也拉进池子（`foods_matching_effects`）。
      2. **把「对不对症」变成主序**：用户明说了「健身要补蛋白」的时候，
         鸡胸肉就该排在当季青菜前面。所以有诉求时 `band = 100 × 契合度`，
         没有诉求时才按时令档位排。
         （菜品那边反过来 —— 一顿饭的时令感更重要，诉求只在同档位内加权。
           两边的取舍不同，是有意的。）
    """
    season_name = f"{season_char_of(month)}季"

    seasonal = food_repository.list_seasonal(session, month=month, limit=pool_size)
    if seasonal:
        pool: list[tuple[Any, Any]] = [(food, season) for food, season in seasonal]
    else:
        rows, _ = food_repository.list_foods(session, offset=0, limit=pool_size)
        pool = [(food, None) for food in rows]

    # 有诉求时，把「对症」的食材也加进候选池
    goal_keywords = list(getattr(health_goal, "effect_keywords", None) or [])
    if goal_keywords:
        seen = {int(getattr(food, "id", 0)) for food, _ in pool}
        matched = foods_matching_effects(session, goal_keywords, limit=150)
        if matched:
            # 一次取全部核心食材再筛，比按 id 逐个查省事得多（590 条很小）
            rows, _ = food_repository.list_foods(session, offset=0, limit=1000)
            by_id = {int(getattr(food, "id", 0)): food for food in rows}
            for food_id in matched:
                if food_id not in seen and food_id in by_id:
                    pool.append((by_id[food_id], None))
                    seen.add(food_id)

    # ★ 「健身要补蛋白」这类诉求：光靠功效词捞不到人。
    #   effects_json 是中医功效（补气血/健脾…），全库只 1 条「补充蛋白质」——
    #   而鸡胸肉（24.6g/100g）、牛里脊（22.2g）这些**压根不带功效标签**。
    #   所以按营养值直接捞：蛋白质 >= 15g/100g 的核心食材全部进池子。
    #   不这么做的话，用户说「家里有健身的」，推出来是山药和石榴。
    if getattr(health_goal, "prefer_high_protein", False):
        seen = {int(getattr(food, "id", 0)) for food, _ in pool}
        rows, _ = food_repository.list_foods(session, offset=0, limit=1000)
        by_id = {int(getattr(food, "id", 0)): food for food in rows}
        candidates_ids = [fid for fid in by_id if fid not in seen]
        for food_id, insight in food_insights(session, candidates_ids).items():
            protein = insight.protein
            # ⚠️ 必须同时要求 is_protein_source（肉蛋/水产/豆）。
            #    只按蛋白质数值排的话，口蘑(38.7g)、羊肚菌 会冲进前三 ——
            #    那是**干货**的浓缩值，谁也不会一次吃 100g 干蘑菇。
            #    "高蛋白食材"在用户心里指的是肉蛋水产豆，不是干菌菇。
            if (
                protein is not None
                and protein >= 15
                and insight.is_protein_source
                and food_id in by_id
            ):
                pool.append((by_id[food_id], None))
                seen.add(food_id)

    if not pool:
        return []

    insights = food_insights(session, [int(getattr(food, "id", 0)) for food, _ in pool])
    avoid_terms = _avoid_terms(constraints.avoid)
    keywords = _WEATHER_KEYWORDS.get(weather.kind, [])
    max_usage = max(
        (insight.usage_count for insight in insights.values()), default=0
    )

    scored: list[ScoredItem] = []
    for food, season in pool:
        food_id = int(getattr(food, "id", 0))
        name = str(getattr(food, "name", ""))
        insight = insights.get(food_id)
        tags = list(getattr(food, "tags", None) or [])

        # ---- 硬约束：忌口直接出局 ----
        if _hits_avoid(
            avoid_terms,
            name,
            tags,
            getattr(insight, "description", None),
            getattr(insight, "tags", None),
        ):
            continue

        season_score = int(getattr(season, "season_score", 0) or 0)

        # ---- 天气适配 ----
        weather_fit = _keyword_score(
            keywords,
            name,
            tags,
            getattr(insight, "tags", None),
            getattr(insight, "tcm_suitable", None),
        )

        # ---- 营养均衡：蔬菜/水果加分；限钠时压低高钠食材 ----
        nutrition_fit = 0.0
        if insight is not None:
            if insight.is_vegetable or insight.category == "fruit":
                nutrition_fit += 0.6
            if insight.is_protein_source:
                nutrition_fit += 0.3
            sodium = insight.na_mg
            if constraints.low_sodium and sodium is not None:
                # 100g 里钠 <100mg 算优秀，>400mg 明显扣分
                if sodium < 100:
                    nutrition_fit += 0.4
                elif sodium > 400:
                    nutrition_fit -= 0.4
            if insight.dietary_fiber is not None and insight.dietary_fiber >= 2:
                nutrition_fit += 0.1
        nutrition_fit = max(0.0, min(nutrition_fit, 1.0))

        preference_fit = _preference_score(
            constraints.preferences, name, tags, getattr(insight, "tags", None)
        )
        popularity = _log_norm(
            insight.usage_count if insight else 0, max_usage
        )
        salt = daily_salt(region or "national", date_key, "food", name)

        # ---- 食养诉求契合度（用户明说的需求）----
        goal_fit_score = 0.0
        if goal_keywords:
            effect_tags = set(getattr(insight, "tags", None) or ())
            goal_fit_score = goal_fit(effect_tags, goal_keywords)

        # ★ 「健身要补蛋白」这类诉求本质是**营养**需求，不是中医功效需求。
        #   effects_json 里几乎没有营养学词（全库只有 1 条「补充蛋白质」），
        #   靠功效匹配的话，用户说「家里有健身的」推出来的还是山药和石榴。
        #   所以这类诉求改用「每 100g 蛋白质含量」来评：>=20g 算优秀。
        if getattr(health_goal, "prefer_high_protein", False) and insight is not None:
            protein = insight.protein
            if protein is not None:
                goal_fit_score = max(goal_fit_score, min(protein / 20.0, 1.0))
        if goal_keywords and goal_fit_score == 0.0:
            goal_fit_score = -0.5

        # 质量分不含轮换因子 —— 池子用它排序，保证「能进池子的都是好候选」
        quality = (
            W_WEATHER * weather_fit
            + W_NUTRITION * nutrition_fit
            + W_PREFERENCE * preference_fit
            + W_POPULARITY * popularity
            + W_GOAL * goal_fit_score
            + (W_IMAGE if has_image(name) else 0.0)
            # 「对症」的食材也得当季优先 —— 但只是加权，主序见下面的 band
            + W_SEASON * (season_score / 100.0)
        )
        score = quality + W_DAILY * salt

        highlights: list[str] = []
        if goal_fit_score > 0 and health_goal is not None:
            highlights.append(getattr(health_goal, "name", "对症"))
        if season_score >= 95:
            highlights.append(f"{month}月正当时")
        elif season_score >= 85:
            highlights.append(f"{season_name}时令")
        if weather_fit >= 0.34:
            highlights.append(weather.advice.split("，")[0])
        if constraints.low_sodium and insight and insight.na_level() == "低":
            highlights.append("低钠")
        if preference_fit > 0:
            highlights.append("合口味")
        if insight and insight.tags:
            highlights.append(insight.tags[0])

        scored.append(
            ScoredItem(
                raw=food,
                item_id=food_id,
                name=name,
                score=score,
                reason="",  # 先留空，下面按主序 + 分数统一生成
                factors={
                    "season": float(season_score),
                    "weather": weather_fit,
                    "nutrition": nutrition_fit,
                    "preference": preference_fit,
                    "popularity": popularity,
                    "daily": salt,
                    "goal": goal_fit_score,
                },
                insight=insight,
                highlights=highlights[:3],
                quality=quality,
                # ★ 排序主序：
                #   没有诉求 → 时令档位（95 分的莲藕永远压过 90 分的南瓜，
                #              但同为「当月时令」的几十个食材每天会换一批）
                #   有诉求   → 对症程度（用户明说了「补气血」，那就该以它为先）
                band=(
                    100.0 * goal_fit_score
                    if goal_keywords
                    else float(season_score)
                ),
            )
        )

    if exclude_ids:
        scored = [item for item in scored if item.item_id not in exclude_ids]

    for item in scored:
        item.reason = _food_reason(item, month=month, weather=weather)

    # ★ 有诉求时不要按「每日轮换」抽稀 —— 用户要的是「对症的那几样」，
    #   轮换会把最对症的挤出去，看起来就像没听懂。
    if goal_keywords:
        scored.sort(key=lambda item: (-item.band, -item.quality, item.item_id))
        return scored[:limit] if limit else scored
    picked = _select_with_rotation(
        scored, limit=limit, pool_size=ROTATE_POOL_FOOD
    )
    return picked if limit else scored


def _food_reason(item: ScoredItem, *, month: int, weather: WeatherContext) -> str:
    factors = item.factors
    parts: list[str] = []
    if factors["season"] >= 95:
        parts.append(f"{month} 月正当时")
    elif factors["season"] > 0:
        parts.append("应季食材")
    if factors["weather"] >= 0.34:
        parts.append(weather.advice)
    if item.insight is not None and item.insight.tags:
        parts.append(item.insight.tags[0])
    if factors["preference"] > 0:
        parts.append("合家里口味")
    if not parts:
        parts.append("当季常见，搭配不挑菜")
    return " · ".join(dict.fromkeys(parts))


# =====================================================================
# 菜品打分
# =====================================================================


def _dish_candidate_ids(
    session: Session,
    *,
    month: int,
    season_name: str,
    pool_size: int,
    goal_effect_keywords: list[str] | None = None,
) -> list[int]:
    """菜品候选池。

    优先级：
      1. 时令日历显式关联的菜（seasonal_dish_links，只有 101 条，最精准）
      2. 用了当月时令食材的菜（dish_ingredients × seasonal_food，覆盖广得多）
      3. 兜底：按时令标注取一批

    ★ 传了 goal_effect_keywords 时，会把「用了具备该功效的食材」的菜
      也并进候选池 —— 否则用户说「想吃点补气血的」，而候选池里全是
      当季时蔬、一道补气血的都没有，排序再准也白搭。
    """
    ids: list[int] = []
    seen: set[int] = set()

    def push(values) -> None:
        for value in values:
            value = int(value)
            if value not in seen:
                seen.add(value)
                ids.append(value)

    if goal_effect_keywords:
        goal_food_ids = foods_matching_effects(
            session, goal_effect_keywords, limit=60
        )
        if goal_food_ids:
            push(dishes_using_foods(session, goal_food_ids, limit=pool_size).keys())

    linked = seasonal_linked_dish_ids(session, season_char_of(month))
    push(sorted(linked))

    seasonal_foods = food_repository.list_seasonal(session, month=month, limit=60)
    seasonal_food_ids = [int(getattr(food, "id", 0)) for food, _ in seasonal_foods]
    if seasonal_food_ids:
        hits = dishes_using_foods(session, seasonal_food_ids, limit=pool_size)
        push(hits.keys())

    if len(ids) < 8:
        rows, _ = recipe_repository.list_recipes(
            session, season=season_name, limit=pool_size
        )
        push([int(getattr(r, "id", 0)) for r in rows])
        if len(ids) < 8:
            rows, _ = recipe_repository.list_recipes(session, limit=pool_size)
            push([int(getattr(r, "id", 0)) for r in rows])

    return ids[:pool_size]


def score_dishes(
    session: Session,
    *,
    month: int,
    weather: WeatherContext,
    constraints: HardConstraints,
    region: str | None = None,
    date_key: str = "",
    food_ids: list[int] | None = None,
    exclude_ids: set[int] | None = None,
    pool_size: int = 200,
    limit: int = 3,
    candidate_ids: list[int] | None = None,
    rejected_names: list[str] | None = None,
    health_goal: HealthGoal | None = None,
) -> list[ScoredItem]:
    """按综合打分挑菜。

    传 `food_ids` 时进入「配菜模式」：候选只从「能用这些食材做的菜」里选，
    这是 AI 助手那一栏「根据我选好的食材推荐」的实现基础。

    传 `rejected_names` 时，被硬约束挡掉的菜名会追加进去 ——
    调用方（AI 助手的 Critic 步骤）可以如实告诉用户「为什么没推这道」，
    而不必再跑一遍打分。
    """
    season_name = f"{season_char_of(month)}季"
    exclude_ids = exclude_ids or set()
    goal_keywords = effect_keywords_of(health_goal)

    if candidate_ids is not None:
        ids = [int(i) for i in candidate_ids if int(i) not in exclude_ids]
    elif food_ids:
        hits = dishes_using_foods(session, food_ids, limit=pool_size)
        ids = [i for i in hits if i not in exclude_ids]
    else:
        ids = [
            i
            for i in _dish_candidate_ids(
                session,
                month=month,
                season_name=season_name,
                pool_size=pool_size,
                goal_effect_keywords=goal_keywords,
            )
            if i not in exclude_ids
        ]

    if not ids:
        return []

    insights = dish_insights(session, ids, season=season_char_of(month))
    raw_by_id = {
        int(getattr(recipe, "id", 0)): recipe
        for recipe in recipe_repository.list_by_ids(session, ids)
    }

    # ---- 用户诉求（如「补气血」）----
    # 拿每道菜所有食材的功效标签，和诉求关键词对一遍。
    # 这一步是「答到点子上」的关键：没有它，模型只能拿时令/天气硬凑。
    effects_by_food: dict[int, set[str]] = {}
    if goal_keywords:
        all_food_ids = sorted(
            {
                food_id
                for insight in insights.values()
                for food_id in insight.ingredient_ids
            }
        )
        if all_food_ids:
            effects_by_food = {
                food_id: set(insight.tags)
                for food_id, insight in food_insights(session, all_food_ids).items()
            }

    avoid_terms = _avoid_terms(constraints.avoid)
    keywords = _DISH_WEATHER_TAGS.get(weather.kind, [])
    seasonal_food_ids = {
        int(getattr(food, "id", 0))
        for food, _ in food_repository.list_seasonal(session, month=month, limit=60)
    }

    scored: list[ScoredItem] = []
    for recipe_id in ids:
        raw = raw_by_id.get(recipe_id)
        if raw is None:
            continue
        insight = insights.get(recipe_id)
        name = str(getattr(raw, "name", "") or (insight.name if insight else ""))
        tags = list(getattr(raw, "tags", None) or (insight.tags if insight else []))

        # ---- 推荐准入：抓取来的页面标题不进推荐位（库里保留，列表/搜索照旧）----
        if not is_recommendable_dish_name(name):
            continue

        # ---- 硬约束 1：忌口 ----
        hit = _hits_avoid(
            avoid_terms, name, tags, getattr(insight, "main_ingredients", None)
        )
        if hit:
            if rejected_names is not None:
                rejected_names.append(f"{name}（含「{hit}」）")
            continue

        duration = int(getattr(raw, "duration_minutes", 0) or 0)
        duration_reliable = True
        overtime_penalty = 0.0
        if insight is not None:
            duration = insight.duration_minutes
            duration_reliable = insight.duration_source in {"table", "text"}
            # 让「展示用的对象」和「筛选用的值」保持一致 ——
            # 否则会出现卡片上写着 30 分钟、却被按 90 分钟筛掉的怪事。
            if (
                hasattr(raw, "duration_minutes")
                and getattr(raw, "duration_minutes", None) != duration
            ):
                raw.duration_minutes = duration
                if hasattr(raw, "duration_estimated"):
                    raw.duration_estimated = not duration_reliable

        # ---- 硬约束 2：今天的可用烹饪时间 ----
        #
        # ⚠️ 只在时长**有依据**时才硬筛。
        #    清洗库的 dishes 没有时长列：56% 的菜能从做法文本里抽出
        #    「小火炖 30 分钟」，剩下的只能估。拿一个估出来的数字去**否决**
        #    一道菜，等于用编的数据删候选 —— 那不算确定性约束，那叫瞎猜。
        #    所以：有依据 → 硬筛；没依据 → 降权（排后面，但不消失）。
        if duration > constraints.cook_minutes:
            if duration_reliable:
                if rejected_names is not None:
                    rejected_names.append(f"{name}（需 {duration} 分钟）")
                continue
            overtime_penalty = 0.4

        # ---- 时令契合度 ----
        season_fit = 0.0
        if insight is not None and insight.season_linked:
            season_fit += 0.5
        if insight is not None and seasonal_food_ids:
            overlap = len(set(insight.ingredient_ids) & seasonal_food_ids)
            season_fit += min(overlap / 2.0, 1.0) * 0.5
        season_fit = min(season_fit, 1.0)

        # ---- 天气适配 ----
        weather_fit = _keyword_score(keywords, tags, name)

        # ---- 营养 ----
        nutrition_fit = 0.0
        if insight is not None:
            if insight.dietary_fiber_g is not None and insight.dietary_fiber_g >= 3:
                nutrition_fit += 0.25
            if insight.protein_g is not None and insight.protein_g >= 15:
                nutrition_fit += 0.25
            per_serving_na = insight.na_per_serving()
            if per_serving_na is not None:
                if constraints.low_sodium:
                    if per_serving_na <= _SODIUM_PER_MEAL_TARGET_MG:
                        nutrition_fit += 0.5
                    elif per_serving_na > _SODIUM_PER_MEAL_TARGET_MG * 1.6:
                        nutrition_fit -= 0.5
                else:
                    nutrition_fit += 0.15
            # 营养数据可信度（清洗时的配料匹配比例）也计入 —— 数据可信才敢推荐
            if insight.matched_ratio is not None:
                nutrition_fit += 0.15 * min(max(insight.matched_ratio, 0.0), 1.0)
        nutrition_fit = max(0.0, min(nutrition_fit, 1.0))

        preference_fit = _preference_score(constraints.preferences, tags, name)

        # ---- 用户主动说出的食养诉求（「想吃点补气血的」）----
        goal_score = 0.0
        if goal_keywords and insight is not None:
            dish_effects: set[str] = set()
            for food_id in insight.ingredient_ids:
                dish_effects |= effects_by_food.get(food_id, set())
            goal_score = goal_fit(dish_effects, goal_keywords)

        # ---- 大众接受度：用配料数当「不是黑暗料理」的粗过滤 ----
        popularity = 0.5
        if insight is not None and insight.main_ingredients:
            count = len(insight.main_ingredients)
            popularity = 1.0 if 2 <= count <= 7 else 0.4
        # 营销式长标题已经在准入那一步剔除了，这里不再重复降权
        salt = daily_salt(region or "national", date_key, "dish", name)

        quality = (
            W_SEASON * season_fit
            + W_WEATHER * weather_fit
            + W_NUTRITION * nutrition_fit
            + W_PREFERENCE * preference_fit
            + W_POPULARITY * popularity
            + W_GOAL * goal_score
            # 有配图的优先（展示层偏好，权重很小，见 W_IMAGE 的说明）
            + (W_IMAGE if has_image(name) else 0.0)
            # 时长没依据、又明显超预算的：降权而不是删掉
            - overtime_penalty
        )
        score = quality + W_DAILY * salt

        highlights: list[str] = []
        if goal_score > 0 and health_goal is not None:
            highlights.append(health_goal.name)
        if season_fit >= 0.5:
            highlights.append("当季食材")
        if weather_fit >= 0.34:
            highlights.append(weather.advice.split("，")[0])
        if constraints.low_sodium and insight is not None:
            per_serving_na = insight.na_per_serving()
            if per_serving_na is not None and per_serving_na <= _SODIUM_PER_MEAL_TARGET_MG:
                highlights.append("低钠")
        if preference_fit > 0:
            highlights.append("合口味")
        if insight is not None and insight.tags:
            highlights.append(insight.tags[0])

        scored.append(
            ScoredItem(
                raw=raw,
                item_id=recipe_id,
                name=name,
                score=score,
                reason="",
                factors={
                    "season": season_fit,
                    "weather": weather_fit,
                    "nutrition": nutrition_fit,
                    "preference": preference_fit,
                    "popularity": popularity,
                    "daily": salt,
                    "goal": goal_score,
                },
                insight=insight,
                highlights=highlights[:3],
                quality=quality,
                # 菜品没有「应季程度」这种天然档位，所以全部同一个档位，
                # 轮换在「质量前 N 名」的池子里进行。
                band=0.0,
            )
        )

    for item in scored:
        item.reason = _dish_reason(
            item, weather=weather, constraints=constraints, health_goal=health_goal
        )

    # ★ 两种场景用两种选法：
    #   · 传了 food_ids（「用我的食材配菜 / 能做什么」）→ 相关性优先，不轮换
    #   · 没传（首页每日推荐）→ 档位 + 每日轮换
    if food_ids:
        return _select_by_relevance(scored, food_ids=food_ids, limit=limit)
    picked = _select_with_rotation(
        scored, limit=limit, pool_size=ROTATE_POOL_DISH
    )
    return picked if limit else scored


def _dish_reason(
    item: ScoredItem,
    *,
    weather: WeatherContext,
    constraints: HardConstraints,
    health_goal: HealthGoal | None = None,
) -> str:
    factors = item.factors
    parts: list[str] = []
    # ★ 用户说出的诉求排在最前面 —— 它比时令/天气更贴近「我为什么问」
    if health_goal is not None and factors.get("goal", 0) > 0:
        parts.append(f"含{health_goal.name}的食材")
    if factors["season"] >= 0.5:
        parts.append("用了当季食材")
    if factors["weather"] >= 0.34:
        parts.append(weather.advice)
    if constraints.low_sodium and factors["nutrition"] >= 0.5:
        parts.append("钠含量在控制范围内")
    if factors["preference"] > 0:
        parts.append("合家里口味")
    if item.insight is not None and item.insight.tags:
        parts.append(item.insight.tags[0])
    if not parts:
        parts.append("家常好做，食材不挑季节")
    return " · ".join(dict.fromkeys(parts))
