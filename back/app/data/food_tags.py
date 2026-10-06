"""食材标签推导 —— 保证每个食材**至少有一个**可展示的标签。

【要解决的问题】
清洗库里 `effects_json`（功效标签，如「润燥养胃」「增强人体免疫力」）只覆盖
**124 / 590（21%）** 个核心食材。剩下 79% 的食材在界面上就没有标签，
卡片下面空一块 —— 而 `reason` 列虽然 100% 有值，但内容全是
「核心原生食材」这种占位串，拿来做标签是骗人。

【为什么可以推导，而不是编】
这张表的营养列覆盖率很高（能量 79%、蛋白 79%、钠 75%、钙 77%、维C 43%），
已经是**按 100g 算好的权威数值**。所以标签不是「编」出来的，是从真实数值
判出来的：
    「富含维生素C」  ⇐ vitamin_c >= 30 mg/100g
    「低热量」       ⇔ energy_kcal <= 40 kcal/100g
    「蛋白质丰富」   ⇐ protein >= 12 g/100g
这些说法可核对、可解释，和「AI 生成一段养生文案」完全不是一回事。

【兜底链】
    1. effects_json（功效标签，质量最高，有就排最前）
    2. 营养特征（真实数值推导）
    3. subcategory / category（100% 有值，最弱但一定有）
这样 590 个食材**每一个都至少有一个标签**。

⚠️ 数值阈值参照《中国食物成分表》的常见分档（每 100g）：
    维生素C：>=30mg 算丰富（成人每日推荐量约 100mg）
    蛋白质：>=12g 算丰富（瘦肉/鱼/蛋/豆制品一档）
    钙：>=100mg 算丰富
    膳食纤维：>=2.5g 算丰富
    能量：<=40kcal 算低热量；脂肪 <=1g 算低脂肪；钠 <=100mg 算低钠
阈值集中在这里，觉得不合适直接改这一个文件。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

# (标签, 判定函数) —— 顺序即优先级：越靠前越"值得放在卡片上"
_NUTRITION_RULES: list[tuple[str, str, float]] = [
    # (标签, 列名, 阈值) —— 语义由 _cmp 决定
    ("蛋白质丰富", "protein", 12.0),      # >=
    ("富含维生素C", "vitamin_c", 30.0),    # >=
    ("含钙丰富", "ca", 100.0),            # >=
    ("膳食纤维丰富", "dietary_fiber", 2.5),  # >=
    ("富含钾", "k", 300.0),               # >=
    ("含铁丰富", "fe", 5.0),              # >=
    ("低脂肪", "fat", 1.0),               # <=
    ("低热量", "energy_kcal", 40.0),       # <=
    ("低钠", "na", 100.0),                # <=
]

# 哪些规则是「小于等于」判定
_LTE = {"fat", "energy_kcal", "na"}

# category（清洗库里是中文）→ 兜底标签
_CATEGORY_TAG = {
    "蔬菜": "蔬菜",
    "薯芋": "薯类",
    "菌菇": "菌菇",
    "菌菇藻类": "菌菇",
    "水果": "水果",
    "畜肉": "肉类",
    "禽肉": "肉类",
    "蛋类": "蛋类",
    "肉蛋": "肉蛋",
    "水产": "水产",
    "豆类": "豆制品",
    "豆制品": "豆制品",
    "谷物": "主食",
    "坚果": "坚果",
    "调味": "调味",
    "调味料": "调味",
}


# 这些词一出现，说明这条不是「功效词」而是句子 / 主治 / 说明。
#
# 【为什么要这么狠】
# effects_json 是从公开中医食材页面抓来的，混了大量句子碎片。实测原始数据：
#   花生 → ['对美容', '抗老化', '抗老化等都有助益', ...]   ← 后半句被截断成"标签"
#   蒜   → [..., '暖胃\\补肾', ...]                       ← 反斜杠转义残留
#   木耳 → [..., '小儿疳积', '治下痢']                    ← 混进了「主治」条目
#   鸡肉 → ['利于人体消化吸收', ...]                       ← 这是句子
# 这些贴到卡片上就是假信息。宁可少几个标签（不够会自动退回营养推导），
# 也不要放一个用户看了会误解的"功效"。
_SENTENCE_MARKERS = (
    "等", "都", "有助", "利于", "可以", "能够", "适宜", "适合", "用于",
    "的", "了", "、", "，", ",", "。", ".", "：", ":", "\\", "/", "|",
)
# 以这些字开头的基本是「主治/适用」而不是功效
_NON_EFFECT_PREFIXES = ("对", "治", "主", "有", "可", "能", "适", "用")

# 功效词的长度上限。实测「增强人体免疫力」（7 字）是有效标签，
# 「月经不调及健脾开胃调理」（12 字）是句子，所以卡在 8。
_EFFECT_MAX_LEN = 8


def _clean_effect(text: str) -> str | None:
    """把 effects_json 里的条目规范成「能当标签用」的短词。

    返回 None 表示这条不可用 —— 调用方会跳过它，
    全部被跳过时自然退回营养/分类推导（不会因此没标签）。
    """
    cleaned = text.strip().strip("。．.，,、；;：:！!？? 　")
    if not cleaned:
        return None
    # 「暖胃\补肾」这种带转义残留的：取第一段
    for separator in ("\\", "/", "|"):
        if separator in cleaned:
            cleaned = cleaned.split(separator)[0].strip()
    if not cleaned or len(cleaned) > _EFFECT_MAX_LEN:
        return None
    if any(marker in cleaned for marker in _SENTENCE_MARKERS):
        return None
    if cleaned.startswith(_NON_EFFECT_PREFIXES):
        return None
    return cleaned


def _dedupe_effects(effects: list[str]) -> list[str]:
    """去掉语义重复的条目。

    例如葱的原始标签是 ['健脾', '健脾宽中', '养生', '导滞'] ——
    「健脾」和「健脾宽中」说的是同一件事，占两个位置没意义。
    规则：如果 A 是 B 的子串，只保留先出现的那个（保持源数据顺序）。
    """
    kept: list[str] = []
    for item in effects:
        if any(item in existing or existing in item for existing in kept):
            continue
        kept.append(item)
    return kept


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            text_value = value.strip()
            return [text_value] if text_value and text_value != "[]" else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def derive_food_tags(row: Mapping[str, Any], *, limit: int = 4) -> list[str]:
    """从清洗库的一行里推导标签，保证非空。

    `row` 可以是 `ingredients` 表的行（清洗库），也可以是 `foods` 表的行（旧演示表）。
    列不存在时按「没有这项数据」处理，不会报错 —— 测试用的最小库就是这么用的。
    """
    tags: list[str] = []

    # ---- 1. 功效标签：有就用，质量最高 ----
    raw_effects = [
        cleaned
        for effect in _json_list(row.get("effects_json"))
        if (cleaned := _clean_effect(effect))
    ]
    for effect in _dedupe_effects(raw_effects):
        if effect not in tags:
            tags.append(effect)

    # ---- 2. 营养特征：从真实数值判 ----
    for label, column, threshold in _NUTRITION_RULES:
        if len(tags) >= limit:
            break
        value = _number(row.get(column))
        if value is None:
            continue
        hit = value <= threshold if column in _LTE else value >= threshold
        if hit and label not in tags:
            tags.append(label)

    if tags:
        return tags[:limit]

    # ---- 3. 兜底：分类。100% 有值，保证「每个食材至少一个标签」----
    subcategory = str(row.get("subcategory") or "").strip()
    # 「叶菜」「根茎」「菌菇」「瓜果」「杂粮」这类两字以上的子类直接可用；
    # 「猪」「鸡」「虾」这种单字做标签读着别扭，退回分类
    if len(subcategory) >= 2:
        return [subcategory]

    category = str(row.get("category") or "").strip()
    return [_CATEGORY_TAG.get(category, category or "食材")]
