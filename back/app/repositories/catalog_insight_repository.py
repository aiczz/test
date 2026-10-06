"""内容库的「深层字段」只读访问 —— 综合打分算法与 AI 知识库的取数口。

【为什么不直接改 compact_catalog_repository】
那边是既有功能的取数口，字段是照着旧响应契约挑的（比如 `_recipe` 只取
菜名/描述/标签，**不取营养**）。这次要的是营养、中医属性、适合人群、
时令知识原文这些「描述性的深层字段」，硬塞进旧接口会改动已有响应。

所以这里单开一层：只读、只在首页打分和 AI 知识库里用，
**不碰任何既有响应**。

【为什么所有查询都要先探列】
`tests/test_compact_catalog.py` 用的是一套「最小六表」——只有部分列。
线上那套是完整的。同一份代码要同时活在这两种库上，所以这里统一：
先 `inspect` 出真实列，再按存在的列拼 SELECT。
这样既不会在最小库上炸，也能在字段扩充/裁剪时不至于整体报错。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy import inspect, text
from sqlmodel import Session

from app.core.database import uses_compact_catalog
from app.data.dish_tags import canonical_dish_tags
from app.data.food_tags import derive_food_tags

# =====================================================================
# 归一化后的洞察对象 —— 不管底层是清洗库还是旧演示表，上层只看这两个
# =====================================================================


@dataclass(slots=True)
class FoodInsight:
    """一个食材的「除名字以外」的全部可用信息。"""

    food_id: int
    name: str
    category: str = "other"
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    # 中医/营养视角的宜忌，直接来自清洗库，用来做硬约束与解释
    tcm_suitable: str | None = None
    tcm_avoid: str | None = None
    suitable_groups: list[str] = field(default_factory=list)
    unsuitable_groups: list[str] = field(default_factory=list)
    # 每 100g 营养
    energy_kcal: float | None = None
    protein: float | None = None
    fat: float | None = None
    cho: float | None = None
    dietary_fiber: float | None = None
    na_mg: float | None = None
    ca_mg: float | None = None
    vitamin_c: float | None = None
    # 被多少道菜用到 —— 当作「大众接受度」的代理指标
    usage_count: int = 0

    @property
    def is_vegetable(self) -> bool:
        return self.category == "vegetable"

    @property
    def is_protein_source(self) -> bool:
        return self.category in {"meat_egg", "aquatic", "soy"}

    def na_level(self) -> str:
        if self.na_mg is None:
            return "未知"
        if self.na_mg < 100:
            return "低"
        if self.na_mg < 400:
            return "中"
        return "高"


@dataclass(slots=True)
class DishInsight:
    """一道菜的深层信息。"""

    recipe_id: int
    name: str
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    duration_minutes: int = 30
    # 时长是怎么来的：
    #   table     —— 库里有时长列（旧演示表 recipes.duration_minutes），可信
    #   text      —— 从做法文本里抽出来的（「小火炖 30 分钟」），有依据
    #   estimated —— 既没列也抽不到，按标签数估的，**只是个数**
    duration_source: str = "estimated"
    servings: int = 3
    difficulty: str = "简单"
    # 整道菜的合计营养（清洗库已按配料克重算好）
    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    cho_g: float | None = None
    dietary_fiber_g: float | None = None
    na_mg: float | None = None
    total_weight_g: float | None = None
    # 营养可置信度（清洗时算出的配料匹配比例）
    matched_ratio: float | None = None
    # 主料（菜名里出现的、决定这道菜是什么的食材）
    main_ingredients: list[str] = field(default_factory=list)
    ingredient_ids: list[int] = field(default_factory=list)
    # 是否被时令日历直接关联（101 条 seasonal_dish_links）
    season_linked: bool = False

    def na_per_serving(self) -> float | None:
        if self.na_mg is None:
            return None
        return self.na_mg / max(self.servings, 1)

    def energy_per_serving(self) -> float | None:
        if self.energy_kcal is None:
            return None
        return self.energy_kcal / max(self.servings, 1)


# =====================================================================
# 列探测（带引擎级缓存）
# =====================================================================

# ⚠️ 必须用 WeakKeyDictionary 而不是 {id(bind): ...}：
#    Engine 被回收后 id 会被复用，新引擎可能命中上一个引擎的列缓存，
#    表现为「测试之间结果互相污染」这种极难查的 bug。
_column_cache: "WeakKeyDictionary[Any, dict[str, set[str]]]" = WeakKeyDictionary()


def _columns(session: Session, table: str) -> set[str]:
    bind = session.get_bind()
    try:
        per_engine = _column_cache.setdefault(bind, {})
    except TypeError:
        # bind 不支持弱引用（极少见），那就退回不缓存，只损失一点性能
        per_engine = {}
    cached = per_engine.get(table)
    if cached is not None:
        return cached

    inspector = inspect(bind)
    names = set(inspector.get_table_names())
    if table not in names:
        per_engine[table] = set()
        return set()
    cols = {column["name"] for column in inspector.get_columns(table)}
    per_engine[table] = cols
    return cols


def _pick(available: set[str], wanted: Iterable[str]) -> list[str]:
    """按 wanted 的顺序，挑出真实存在的列。"""
    return [name for name in wanted if name in available]


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            text_value = value.strip()
            return [text_value] if text_value else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "")]


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _i(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _placeholders(prefix: str, values: list[Any]) -> tuple[str, dict[str, Any]]:
    names: list[str] = []
    params: dict[str, Any] = {}
    for index, value in enumerate(values):
        key = f"{prefix}{index}"
        names.append(f":{key}")
        params[key] = value
    return ", ".join(names), params


# =====================================================================
# 食材洞察
# =====================================================================

_FOOD_COLUMNS = [
    "id",
    "name",
    "category",
    # subcategory 用于标签推导的最后兜底（100% 有值：叶菜/根茎/菌菇…）
    "subcategory",
    "reason",
    "effects_json",
    "tcm_user",
    "tcm_not_user",
    "suitable_groups_json",
    "unsuitable_groups_json",
    "usage_count",
    "energy_kcal",
    "protein",
    "fat",
    "cho",
    "dietary_fiber",
    "na",
    "ca",
    "vitamin_c",
    # k / fe 也参与标签推导（富含钾 / 含铁丰富）
    "k",
    "fe",
]

# 清洗库里 category 是中文；旧演示表里已经是英文枚举
_CATEGORY_MAP = {
    "蔬菜": "vegetable",
    "薯芋": "vegetable",
    "菌菇": "vegetable",
    "菌菇藻类": "vegetable",
    "水果": "fruit",
    "畜肉": "meat_egg",
    "禽肉": "meat_egg",
    "蛋类": "meat_egg",
    "肉蛋": "meat_egg",
    "水产": "aquatic",
    "豆类": "soy",
    "豆制品": "soy",
    "谷物": "grain",
    "坚果": "grain",
    "调味": "seasoning",
    "调味料": "seasoning",
}


def _norm_category(value: Any) -> str:
    raw = str(value or "")
    return _CATEGORY_MAP.get(raw, raw or "other")


def _food_from_row(row: Mapping[str, Any]) -> FoodInsight:
    return FoodInsight(
        food_id=_i(row.get("id")),
        name=str(row.get("name") or ""),
        category=_norm_category(row.get("category")),
        description=row.get("reason") or row.get("description"),
        # 与 compact_catalog_repository 共用同一套推导 —— 保证
        # 「首页/AI 看到的标签」和「食材列表看到的标签」永远一致，
        # 而且每个食材都至少有一个（功效 → 营养 → 分类）。
        tags=derive_food_tags(row),
        tcm_suitable=row.get("tcm_user"),
        tcm_avoid=row.get("tcm_not_user"),
        suitable_groups=_json_list(row.get("suitable_groups_json")),
        unsuitable_groups=_json_list(row.get("unsuitable_groups_json")),
        energy_kcal=_f(row.get("energy_kcal")),
        protein=_f(row.get("protein")),
        fat=_f(row.get("fat")),
        cho=_f(row.get("cho")),
        dietary_fiber=_f(row.get("dietary_fiber")),
        na_mg=_f(row.get("na")),
        ca_mg=_f(row.get("ca")),
        vitamin_c=_f(row.get("vitamin_c")),
        usage_count=_i(row.get("usage_count")),
    )


def food_insights(session: Session, food_ids: list[int]) -> dict[int, FoodInsight]:
    """批量取食材洞察。查不到就少几个 key，不报错。"""
    ids = [int(i) for i in food_ids if i is not None]
    if not ids:
        return {}

    if uses_compact_catalog(session.get_bind()):
        table, extra = "ingredients", {}
    else:
        # 旧演示表没有营养/中医列，_pick 会自动跳过 —— 上层按 None 处理
        table, extra = "foods", {"is_active": 1}

    available = _columns(session, table)
    if not available:
        return {}

    selected = _pick(available, _FOOD_COLUMNS)
    if "id" not in selected:
        return {}

    marks, params = _placeholders("fid", ids)
    where = f"id IN ({marks})"
    if "is_active" in available and extra:
        where += " AND is_active = 1"

    rows = session.execute(
        text(f"SELECT {', '.join(selected)} FROM {table} WHERE {where}"), params
    ).mappings()
    result: dict[int, FoodInsight] = {}
    for row in rows:
        insight = _food_from_row(row)
        result[insight.food_id] = insight
    return result


# =====================================================================
# 菜品洞察
# =====================================================================

_DISH_COLUMNS = [
    "id",
    "dish_name",
    "name",
    "description",
    "cuisine",
    "category",
    "tags_json",
    "duration_minutes",
    "servings",
    "difficulty",
    "total_weight_g",
    "energy_kcal",
    "protein_g",
    "fat_g",
    "cho_g",
    "dietary_fiber_g",
    "na_mg",
    "matched_ratio",
    # 做法文本：清洗库没有时长列，只能从这里抽「小火炖 30 分钟」→ 30
    "instruction_text",
]

# 「30分钟」「30 分钟」「炖 1.5 小时」「20-30分钟」都要能抽到
_DURATION_PATTERNS = (
    re.compile(r"(\d+)\s*[-~至到]\s*(\d+)\s*分钟"),
    re.compile(r"(\d+)\s*分钟"),
    re.compile(r"(\d+(?:\.\d+)?)\s*个?\s*小时"),
)


def _duration_from_text(text: str | None) -> int | None:
    """从做法文本里抽烹饪时长（分钟）。

    取**所有提到的时间里的最大值** —— 做法里「腌制 10 分钟…小火炖 30 分钟」
    总共要 40 分钟，取最大那个更接近「这道菜要占你多久」。
    抽不到返回 None（调用方退回估算，并标注为估算）。
    """
    if not text:
        return None
    values: list[float] = []
    for pattern in _DURATION_PATTERNS:
        for match in pattern.finditer(text):
            groups = [g for g in match.groups() if g]
            try:
                numbers = [float(g) for g in groups]
            except ValueError:
                continue
            if not numbers:
                continue
            value = max(numbers)
            # 小时 → 分钟
            if "小时" in match.group(0):
                value *= 60
            values.append(value)
    if not values:
        return None
    # 上限 180 分钟：数据里偶尔有「腌制 12 小时」，那不是烹饪时长
    return int(min(max(values), 180))


def _dish_from_row(row: Mapping[str, Any]) -> DishInsight:
    row_duration = _i(row.get("duration_minutes"), 0)
    if row_duration > 0:
        # 旧演示表（recipes）真的有时长列 —— 最可信
        duration, source = row_duration, "table"
    else:
        extracted = _duration_from_text(row.get("instruction_text"))
        if extracted:
            duration, source = extracted, "text"
        else:
            duration, source = 30, "estimated"

    name = str(row.get("dish_name") or row.get("name") or "")
    return DishInsight(
        recipe_id=_i(row.get("id")),
        name=name,
        description=row.get("description"),
        # 和菜谱接口用同一套归一化，AI 提示词里看到的也是「汤羹」而不是「汤」，
        # 否则模型复述标签时会跟界面上显示的对不上。
        tags=canonical_dish_tags(_json_list(row.get("tags_json")), name),
        duration_minutes=duration,
        duration_source=source,
        servings=max(_i(row.get("servings"), 3), 1),
        difficulty=str(row.get("difficulty") or "简单"),
        energy_kcal=_f(row.get("energy_kcal")),
        protein_g=_f(row.get("protein_g")),
        fat_g=_f(row.get("fat_g")),
        cho_g=_f(row.get("cho_g")),
        dietary_fiber_g=_f(row.get("dietary_fiber_g")),
        na_mg=_f(row.get("na_mg")),
        total_weight_g=_f(row.get("total_weight_g")),
        matched_ratio=_f(row.get("matched_ratio")),
    )


def _main_ingredients_compact(
    session: Session, dish_ids: list[int]
) -> dict[int, tuple[list[str], list[int]]]:
    available = _columns(session, "dish_ingredients")
    if not available or "dish_id" not in available:
        return {}

    wanted = ["dish_id", "raw_name", "role", "ingredient_id", "core_ingredient_id"]
    selected = _pick(available, wanted)
    marks, params = _placeholders("did", dish_ids)
    rows = session.execute(
        text(
            f"SELECT {', '.join(selected)} FROM dish_ingredients "
            f"WHERE dish_id IN ({marks}) ORDER BY dish_id"
        ),
        params,
    ).mappings()

    names: dict[int, list[str]] = {}
    ids: dict[int, list[int]] = {}
    for row in rows:
        dish_id = _i(row.get("dish_id"))
        name = str(row.get("raw_name") or "").strip()
        # 只把「主料」喂给打分和 AI —— 盐、油、葱姜蒜这些辅料会淹没信号
        role = str(row.get("role") or "")
        if name and (role in {"main", "core", ""} or role is None):
            names.setdefault(dish_id, []).append(name)
        for key in ("ingredient_id", "core_ingredient_id"):
            value = row.get(key)
            if value is not None:
                ids.setdefault(dish_id, []).append(_i(value))

    return {
        dish_id: (names.get(dish_id, []), sorted(set(ids.get(dish_id, []))))
        for dish_id in dish_ids
    }


def _main_ingredients_legacy(
    session: Session, dish_ids: list[int]
) -> dict[int, tuple[list[str], list[int]]]:
    available = _columns(session, "recipe_ingredients")
    if not available or "recipe_id" not in available:
        return {}
    selected = _pick(available, ["recipe_id", "ingredient_name", "food_id"])
    marks, params = _placeholders("did", dish_ids)
    rows = session.execute(
        text(
            f"SELECT {', '.join(selected)} FROM recipe_ingredients "
            f"WHERE recipe_id IN ({marks}) ORDER BY recipe_id"
        ),
        params,
    ).mappings()
    names: dict[int, list[str]] = {}
    ids: dict[int, list[int]] = {}
    for row in rows:
        rid = _i(row.get("recipe_id"))
        name = str(row.get("ingredient_name") or "").strip()
        if name:
            names.setdefault(rid, []).append(name)
        if row.get("food_id") is not None:
            ids.setdefault(rid, []).append(_i(row.get("food_id")))
    return {
        rid: (names.get(rid, []), sorted(set(ids.get(rid, [])))) for rid in dish_ids
    }


def dish_insights(
    session: Session, recipe_ids: list[int], *, season: str | None = None
) -> dict[int, DishInsight]:
    """批量取菜品洞察（含主料与时令关联）。"""
    ids = [int(i) for i in recipe_ids if i is not None]
    if not ids:
        return {}

    compact = uses_compact_catalog(session.get_bind())
    table = "dishes" if compact else "recipes"
    available = _columns(session, table)
    if not available or "id" not in available:
        return {}

    selected = _pick(available, _DISH_COLUMNS)
    marks, params = _placeholders("rid", ids)
    rows = session.execute(
        text(f"SELECT {', '.join(selected)} FROM {table} WHERE id IN ({marks})"),
        params,
    ).mappings()

    result: dict[int, DishInsight] = {}
    for row in rows:
        insight = _dish_from_row(row)
        # 清洗库的 dishes 没有时长列时，_dish_from_row 已经从做法文本里抽过了；
        # 这里不再覆盖，保证「抽到的真实时长」不会被估的盖掉。
        result[insight.recipe_id] = insight

    pairs = (
        _main_ingredients_compact(session, list(result))
        if compact
        else _main_ingredients_legacy(session, list(result))
    )
    for recipe_id, (names, ingredient_ids) in pairs.items():
        if recipe_id in result:
            result[recipe_id].main_ingredients = names
            result[recipe_id].ingredient_ids = ingredient_ids

    # 时令关联：清洗库只有 101 条显式链接，信号很稀，所以只当作加分项
    linked = seasonal_linked_dish_ids(session, season) if season else set()
    for recipe_id, insight in result.items():
        insight.season_linked = recipe_id in linked

    return result


# =====================================================================
# 时令
# =====================================================================


def list_core_food_names(session: Session) -> list[tuple[int, str]]:
    """全部面向用户的核心食材 (id, 名称)。

    用途：从用户的话里认出他提到的食材（「莲藕怎么做」「我不吃香菜」）。
    只有 590 行，一次查完在内存里做子串匹配，比按名字逐个 LIKE 便宜得多。
    """
    if not uses_compact_catalog(session.get_bind()):
        return []
    available = _columns(session, "ingredients")
    if not {"id", "name"} <= available:
        return []
    rows = session.execute(
        text(
            "SELECT id, name FROM ingredients "
            "WHERE is_core_raw = 1 AND is_edible = 1"
        )
    ).all()
    return [(_i(row[0]), str(row[1])) for row in rows if row[1]]


# 别名里混着大量**配料量词短语**（「一小撮葱花」「几片姜」「一整根大葱」），
# 它们来自菜谱配料文本，不是真的别名。拿它们去匹配用户的话会误命中，
# 所以只保留「看起来像食材名」的别名。
_ALIAS_NOISE_CHARS = "一二三四五六七八九十两几些许少量克片块末丝丁碎颗粒根把勺碗半多整个颗"
_ALIAS_MIN_LEN = 2
_ALIAS_MAX_LEN = 6


def _alias_terms(aliases: list[str]) -> list[str]:
    terms: list[str] = []
    for alias in aliases:
        cleaned = alias.strip().lstrip("/.-－").strip()
        if not (_ALIAS_MIN_LEN <= len(cleaned) <= _ALIAS_MAX_LEN):
            continue
        if any(char in cleaned for char in _ALIAS_NOISE_CHARS):
            continue
        if cleaned not in terms:
            terms.append(cleaned)
    return terms


def list_core_food_terms(session: Session) -> list[tuple[int, str, list[str]]]:
    """核心食材 (id, 名称, 可用于匹配的别名)。

    为什么需要别名：用户说「西红柿炒蛋怎么做」，而库里的核心名是「番茄」——
    只按名字匹配就认不出来，会退化成「按时令随便推」，也就是答非所问。
    实测 590 个核心食材里 **580 个（98%）带别名**，西红柿正是番茄的别名之一。
    """
    bind = session.get_bind()
    if not uses_compact_catalog(bind):
        # 旧演示表（foods）没有别名列 —— 只按名字匹配，功能退化但不报错。
        # 这条路径现在只用于本地演示和测试；线上跑的是清洗库（compact）。
        table = "foods"
        available = _columns(session, table)
        if not {"id", "name"} <= available:
            return []
        where = "WHERE is_active = 1" if "is_active" in available else ""
        rows = session.execute(
            text(f"SELECT id, name FROM {table} {where}")
        ).all()
        return [(_i(row[0]), str(row[1]), []) for row in rows if row[1]]

    available = _columns(session, "ingredients")
    if not {"id", "name"} <= available:
        return []
    selected = _pick(available, ["id", "name", "aliases_json"])
    rows = session.execute(
        text(
            f"SELECT {', '.join(selected)} FROM ingredients "
            "WHERE is_core_raw = 1 AND is_edible = 1"
        )
    ).mappings()
    result: list[tuple[int, str, list[str]]] = []
    for row in rows:
        name = str(row.get("name") or "")
        if not name:
            continue
        result.append(
            (_i(row.get("id")), name, _alias_terms(_json_list(row.get("aliases_json"))))
        )
    return result


def foods_matching_effects(
    session: Session, keywords: list[str], *, limit: int = 120
) -> list[int]:
    """哪些食材带这些功效（按 effects_json 匹配）。

    用途：用户说「想吃点补气血的」时，用它**扩大召回** ——
    只按当季食材召回的话，候选里可能压根没有补气血的菜，
    再好的排序也救不回来。
    """
    if not keywords or not uses_compact_catalog(session.get_bind()):
        return []
    available = _columns(session, "ingredients")
    if not {"id", "effects_json"} <= available:
        return []

    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    for index, keyword in enumerate(keywords):
        key = f"effect_{index}"
        clauses.append(f"effects_json LIKE :{key}")
        params[key] = f"%{keyword}%"
    if not clauses:
        return []

    rows = session.execute(
        text(
            "SELECT id FROM ingredients "
            f"WHERE ({' OR '.join(clauses)}) "
            "AND is_edible = 1 AND is_core_raw = 1 LIMIT :limit"
        ),
        params,
    ).scalars()
    return [_i(value) for value in rows]


def seasonal_linked_dish_ids(session: Session, season: str | None) -> set[int]:
    """被时令日历显式关联的菜品 id。"""
    if not season or not uses_compact_catalog(session.get_bind()):
        return set()

    link_cols = _columns(session, "seasonal_dish_links")
    food_cols = _columns(session, "seasonal_food")
    if not {"dish_id", "seasonal_food_id"} <= link_cols:
        return set()
    if "season" not in food_cols:
        return set()

    rows = session.execute(
        text(
            "SELECT DISTINCT sdl.dish_id FROM seasonal_dish_links sdl "
            "JOIN seasonal_food sf ON sf.id = sdl.seasonal_food_id "
            "WHERE sf.season = :season"
        ),
        {"season": season},
    ).scalars()
    return {_i(value) for value in rows}


def seasonal_knowledge(
    session: Session, *, month: int, season: str, limit: int = 6
) -> list[str]:
    """时令知识原文 —— 直接来自清洗库的 `knowledge_json`。

    这些句子是全项目最「可引用」的原创素材，例如：
        「秋季（9月-11月，农历七〜九月）的应季蔬菜共 24 种：白萝卜、大白菜、山药、莲藕…」
        「秋季润肺，这样吃抗病魔！」
    AI 的解释必须建立在这些句子上，而不是自己编。
    """
    if not uses_compact_catalog(session.get_bind()):
        return []

    available = _columns(session, "seasonal_calendar")
    if not {"name", "knowledge_json"} <= available:
        return []

    selected = _pick(available, ["name", "level", "season", "description", "knowledge_json"])
    month_name = f"{month}月"
    rows = session.execute(
        text(
            f"SELECT {', '.join(selected)} FROM seasonal_calendar "
            "WHERE name = :month_name OR (level = '季节' AND season = :season) "
            "ORDER BY CASE WHEN name = :month_name THEN 0 ELSE 1 END"
        ),
        {"month_name": month_name, "season": season},
    ).mappings()

    facts: list[str] = []
    for row in rows:
        for sentence in _json_list(row.get("knowledge_json")):
            if sentence not in facts:
                facts.append(sentence)
        description = row.get("description")
        if description and description not in facts:
            facts.append(str(description))
        if len(facts) >= limit:
            break
    return facts[:limit]


def seasonal_food_reasons(
    session: Session, *, month: int, season: str, limit: int = 12
) -> list[str]:
    """当月时令食材的推荐理由（可能为空，不勉强）。"""
    if not uses_compact_catalog(session.get_bind()):
        return []
    available = _columns(session, "seasonal_food")
    if "recommendation_reason" not in available:
        return []

    selected = _pick(
        available, ["name", "category", "time_name", "season", "note", "recommendation_reason"]
    )
    rows = session.execute(
        text(
            f"SELECT {', '.join(selected)} FROM seasonal_food "
            "WHERE recommendation_reason IS NOT NULL AND recommendation_reason != '' "
            "AND (season = :season OR time_name = :month_name) LIMIT :limit"
        ),
        {"season": season, "month_name": f"{month}月", "limit": limit},
    ).mappings()

    result: list[str] = []
    for row in rows:
        name = row.get("name")
        reason = row.get("recommendation_reason")
        if name and reason:
            result.append(f"{name}：{reason}")
    return result


# =====================================================================
# 按食材找菜（AI 配菜模块的候选召回）
# =====================================================================


def dishes_using_foods(
    session: Session, food_ids: list[int], *, limit: int = 200
) -> dict[int, list[int]]:
    """哪些菜用到了这些食材。

    返回 {dish_id: [命中的 food_id, ...]}，按命中数降序截断。
    清洗库里同时匹配「食材本身」和它的「核心食材」—— 点了「鸡肉」,
    也要能召回用「鸡胸肉」的菜（沿用 list_recipes_by_food 的口径）。
    """
    ids = [int(i) for i in food_ids if i is not None]
    if not ids:
        return {}

    if uses_compact_catalog(session.get_bind()):
        table = "dish_ingredients"
        id_col, dish_col = "ingredient_id", "dish_id"
        extra_cols = ["core_ingredient_id"]
    else:
        table = "recipe_ingredients"
        id_col, dish_col = "food_id", "recipe_id"
        extra_cols = []

    available = _columns(session, table)
    if not {dish_col, id_col} <= available:
        return {}

    selected = _pick(available, [dish_col, id_col, *extra_cols])
    marks, params = _placeholders("fid", ids)
    params["limit"] = limit

    clauses = [f"{id_col} IN ({marks})"]
    for column in extra_cols:
        clauses.append(f"{column} IN ({marks})")

    rows = session.execute(
        text(
            f"SELECT {', '.join(selected)} FROM {table} "
            f"WHERE {' OR '.join(clauses)}"
        ),
        params,
    ).mappings()

    hits: dict[int, set[int]] = {}
    for row in rows:
        dish_id = _i(row.get(dish_col))
        by_id = {_i(row.get(id_col))}
        for column in extra_cols:
            if row.get(column) is not None:
                by_id.add(_i(row.get(column)))
        matched = by_id & set(ids)
        if dish_id and matched:
            hits.setdefault(dish_id, set()).update(matched)

    ordered = sorted(hits.items(), key=lambda item: (-len(item[1]), item[0]))
    return {dish_id: sorted(matched) for dish_id, matched in ordered[:limit]}
