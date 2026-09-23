from __future__ import annotations

import csv
import hashlib
import os
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "cleaned_v2"
OUTPUT = ROOT / "knowledge_base"
RECIPE_TXT = OUTPUT / "recipe_knowledge.txt"
INGREDIENT_TXT = OUTPUT / "ingredient_knowledge.txt"
DOC_START = "<<<DOCUMENT START>>>"
DOC_END = "<<<DOCUMENT END>>>"


def rows(name: str) -> list[dict[str, str]]:
    with (SOURCE / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def compact(value: str | None) -> str:
    value = (value or "").replace("\x00", " ")
    return re.sub(r"\s+", " ", value).strip()


def value_or_missing(value: str | None) -> str:
    return compact(value) or "暂无"


def unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def normalize_alias(value: str) -> str:
    trim_chars = "/\\／|,，;；:：()（）[]【】－—-"
    name = compact(value).strip(trim_chars)
    name = re.sub(
        r"^(?:适量|少量|少许|一点点|一点|若干|几根|一根|两根|三根|"
        r"几颗|一颗|两颗|半根|半颗|数根|撮|新鲜)",
        "",
        name,
    )
    return name.strip(trim_chars)


def join_or_missing(values, separator: str = "、") -> str:
    result = unique(compact(value) for value in values)
    return separator.join(result) if result else "暂无"


def write_documents(path: Path, documents: list[str]) -> str:
    payload = "\n\n".join(documents) + "\n"
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(temp, path)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def document(lines: list[str]) -> str:
    return "\n".join([DOC_START, *lines, DOC_END])


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    dishes = rows("dishes.csv")
    dish_ingredients = rows("dish_ingredients.csv")
    dish_tags = rows("dish_tags.csv")
    tags = {int(row["id"]): row["name"] for row in rows("tags.csv")}
    dish_nutrition = {int(row["dish_id"]): row for row in rows("dish_nutrition.csv")}

    ingredients = rows("main_ingredient.csv")
    catalog = rows("ingredient_catalog.csv")
    aliases = rows("ingredient_catalog_aliases.csv")
    effects = {int(row["id"]): row["name"] for row in rows("tcm_effects.csv")}
    groups = {int(row["id"]): row["name"] for row in rows("target_groups.csv")}

    seasonal_calendar = {row["id"]: row for row in rows("seasonal_calendar.csv")}
    seasonal_food = rows("seasonal_food.csv")
    seasonal_knowledge = rows("seasonal_knowledge.csv")
    seasonal_dish_links = rows("seasonal_dish_links.csv")

    ingredients_by_dish: dict[int, list[dict[str, str]]] = defaultdict(list)
    core_ids_by_dish: dict[int, set[int]] = defaultdict(set)
    catalog_ids_by_dish: dict[int, set[int]] = defaultdict(set)
    for row in dish_ingredients:
        dish_id = int(row["dish_id"])
        ingredients_by_dish[dish_id].append(row)
        if row["ingredient_id"]:
            core_ids_by_dish[dish_id].add(int(row["ingredient_id"]))
        catalog_ids_by_dish[dish_id].add(int(row["catalog_ingredient_id"]))

    tags_by_dish: dict[int, list[str]] = defaultdict(list)
    for row in dish_tags:
        tags_by_dish[int(row["dish_id"])].append(tags[int(row["tag_id"])])

    effects_by_ingredient: dict[int, list[str]] = defaultdict(list)
    for row in rows("ingredient_effects.csv"):
        effects_by_ingredient[int(row["ingredient_id"])].append(
            effects[int(row["effect_id"])]
        )

    suitable_by_ingredient: dict[int, list[str]] = defaultdict(list)
    unsuitable_by_ingredient: dict[int, list[str]] = defaultdict(list)
    for row in rows("ingredient_groups.csv"):
        group_name = groups[int(row["group_id"])]
        is_suitable = row["is_suitable"] == "1"
        target = suitable_by_ingredient if is_suitable else unsuitable_by_ingredient
        target[int(row["ingredient_id"])].append(group_name)

    alias_by_catalog: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for row in aliases:
        alias_by_catalog[int(row["catalog_ingredient_id"])].append(
            (int(row["usage_count"] or 0), row["alias_name"])
        )

    seasonal_by_catalog: dict[int, list[dict[str, str]]] = defaultdict(list)
    seasonal_by_core: dict[int, list[dict[str, str]]] = defaultdict(list)
    seasonal_food_by_id = {row["id"]: row for row in seasonal_food}
    for row in seasonal_food:
        if row["catalog_ingredient_id"]:
            seasonal_by_catalog[int(row["catalog_ingredient_id"])].append(row)
        if row["core_ingredient_id"]:
            seasonal_by_core[int(row["core_ingredient_id"])].append(row)

    knowledge_by_food: dict[str, list[str]] = defaultdict(list)
    for row in seasonal_knowledge:
        if row["seasonal_food_id"]:
            knowledge_by_food[row["seasonal_food_id"]].append(row["content"])

    direct_seasonal_by_dish: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in seasonal_dish_links:
        direct_seasonal_by_dish[int(row["dish_id"])].append(
            seasonal_food_by_id[row["seasonal_food_id"]]
        )

    recipe_documents: list[str] = []
    missing_ingredients = 0
    missing_instruction = 0
    missing_nutrition = 0
    for dish in sorted(dishes, key=lambda row: int(row["id"])):
        dish_id = int(dish["id"])
        rels = ingredients_by_dish[dish_id]
        ingredient_lines = unique(
            compact(row["raw_text"]) or compact(row["raw_name"])
            for row in rels
        )
        if not ingredient_lines:
            missing_ingredients += 1
        tag_names = sorted(set(tags_by_dish[dish_id]))

        dish_effects = sorted({
            effect
            for ingredient_id in core_ids_by_dish[dish_id]
            for effect in effects_by_ingredient.get(ingredient_id, [])
        })

        seasonal_entries: list[dict[str, str]] = []
        for catalog_id in catalog_ids_by_dish[dish_id]:
            seasonal_entries.extend(seasonal_by_catalog.get(catalog_id, []))
        seasons = sorted({row["season"] for row in seasonal_entries}, key="春夏秋冬".index)
        seasonal_names = sorted({row["name"] for row in seasonal_entries})
        direct_seasonal = direct_seasonal_by_dish.get(dish_id, [])
        festival_labels = unique(
            f"{row['time_name']}推荐{row['name']}" for row in direct_seasonal
        )

        nutrition = dish_nutrition[dish_id]
        if nutrition["nutrition_version"] == "missing":
            nutrition_text = "暂无可靠营养估算"
            missing_nutrition += 1
        else:
            nutrition_text = (
                f"总重量{value_or_missing(nutrition['total_weight_g'])}g，"
                f"能量{value_or_missing(nutrition['energy_kcal'])}kcal，"
                f"蛋白质{value_or_missing(nutrition['protein_g'])}g，"
                f"脂肪{value_or_missing(nutrition['fat_g'])}g，"
                f"碳水化合物{value_or_missing(nutrition['cho_g'])}g，"
                f"膳食纤维{value_or_missing(nutrition['dietary_fiber_g'])}g，"
                f"钠{value_or_missing(nutrition['na_mg'])}mg；版本{nutrition['nutrition_version']}"
            )

        instruction = compact(dish["instruction_text"])
        if not instruction:
            missing_instruction += 1
        keyword_values = [dish["dish_name"], *tag_names]
        keyword_values.extend(row["raw_name"] for row in rels)
        recipe_documents.append(document([
            "文档类型：菜谱",
            f"文档ID：recipe:{dish_id}",
            f"菜名：{dish['dish_name']}",
            f"菜系：{value_or_missing(dish['cuisine'])}",
            f"描述：{value_or_missing(dish['description'])}",
            f"标签：{join_or_missing(tag_names)}",
            f"食材配方：{'；'.join(ingredient_lines) if ingredient_lines else '暂无'}",
            f"做法：{instruction or '暂无'}",
            f"营养概览：{nutrition_text}",
            f"相关食材功效：{join_or_missing(dish_effects[:30])}",
            f"适宜季节：{join_or_missing(seasons)}",
            f"时令食材：{join_or_missing(seasonal_names[:30])}",
            f"节气节日推荐：{join_or_missing(festival_labels)}",
            f"检索关键词：{join_or_missing(keyword_values)}",
            "数据来源：cleaned_v2 精选菜谱及其关联表",
        ]))

    catalog_by_id = {int(row["id"]): row for row in catalog}
    ingredient_documents: list[str] = []
    nutrition_fields = [
        ("可食部%", "可食部", "%"), ("水分g", "水分", "g/100g"),
        ("能量kcal", "能量", "kcal/100g"), ("蛋白质g", "蛋白质", "g/100g"),
        ("脂肪g", "脂肪", "g/100g"), ("碳水化合物g", "碳水化合物", "g/100g"),
        ("膳食纤维g", "膳食纤维", "g/100g"), ("胆固醇mg", "胆固醇", "mg/100g"),
        ("维生素A(ugRE)", "维生素A", "μgRE/100g"), ("维生素Cmg", "维生素C", "mg/100g"),
        ("维生素E总mg", "维生素E", "mg/100g"), ("钙mg", "钙", "mg/100g"),
        ("磷mg", "磷", "mg/100g"), ("钾mg", "钾", "mg/100g"),
        ("钠mg", "钠", "mg/100g"), ("镁mg", "镁", "mg/100g"),
        ("铁mg", "铁", "mg/100g"), ("锌mg", "锌", "mg/100g"),
        ("硒(ug)", "硒", "μg/100g"),
    ]

    def seasonal_lines_for(entries: list[dict[str, str]]) -> tuple[str, str, str]:
        seasons = sorted({row["season"] for row in entries}, key="春夏秋冬".index)
        times = sorted({row["time_name"] for row in entries})
        knowledge = unique(
            compact(content)
            for row in entries
            for content in knowledge_by_food.get(row["id"], [])
        )
        return join_or_missing(seasons), join_or_missing(times), " ".join(knowledge[:12]) or "暂无"

    for row in sorted(ingredients, key=lambda value: int(value["id"])):
        ingredient_id = int(row["id"])
        catalog_row = catalog_by_id[ingredient_id]
        aliases_sorted = unique(
            normalize_alias(name)
            for _, name in sorted(alias_by_catalog.get(ingredient_id, []), reverse=True)
            if normalize_alias(name) and normalize_alias(name) != row["name"]
        )
        nutrient_values = [
            f"{label}{compact(row[field])}{unit}"
            for field, label, unit in nutrition_fields
            if compact(row.get(field)) not in {"", "—", "-"}
        ]
        seasonal_entries = seasonal_by_core.get(ingredient_id, [])
        season_text, time_text, season_knowledge = seasonal_lines_for(seasonal_entries)
        ingredient_documents.append(document([
            "文档类型：食材",
            f"文档ID：ingredient:{ingredient_id}",
            f"食材名称：{row['name']}",
            f"分类：{row['category_major']} / {row['category_sub']}",
            f"常见别名：{join_or_missing(aliases_sorted[:20])}",
            f"营养成分：{'；'.join(nutrient_values) if nutrient_values else '暂无可靠数据'}",
            f"营养来源：{value_or_missing(row['nutrition_source_name'])}",
            f"功效：{join_or_missing(sorted(set(effects_by_ingredient.get(ingredient_id, []))))}",
            f"中医食性：{join_or_missing([row.get('tcm_taste', ''), row.get('tcm_toxicity', '')])}",
            f"适宜人群：{join_or_missing(suitable_by_ingredient.get(ingredient_id, []))}",
            f"不适宜人群：{join_or_missing(unsuitable_by_ingredient.get(ingredient_id, []))}",
            f"食用提示：{join_or_missing([row.get('tcm_user', ''), row.get('tcm_not_user', ''), row.get('tcm_side_effects', '')], '；')}",
            f"产地信息：{value_or_missing(row.get('tcm_production_place'))}",
            f"适宜季节：{season_text}",
            f"适宜月份/节气/节日：{time_text}",
            f"时令知识：{season_knowledge}",
            f"检索关键词：{join_or_missing([row['name'], *aliases_sorted[:20], row['category_major'], row['category_sub']])}",
            f"目录状态：{catalog_row['review_status']}；核心原生食材",
            "数据来源：cleaned_v2 核心食材、营养、功效、人群与季节关联表",
        ]))

    seasonal_catalog_rows = [
        row for row in catalog if row["ingredient_type"] == "seasonal_food"
    ]
    for row in sorted(seasonal_catalog_rows, key=lambda value: int(value["id"])):
        catalog_id = int(row["id"])
        aliases_sorted = unique(
            normalize_alias(name)
            for _, name in sorted(alias_by_catalog.get(catalog_id, []), reverse=True)
            if normalize_alias(name) and normalize_alias(name) != row["name"]
        )
        entries = seasonal_by_catalog.get(catalog_id, [])
        season_text, time_text, season_knowledge = seasonal_lines_for(entries)
        recommendation = join_or_missing(
            [entry["recommendation_reason"] for entry in entries], "；"
        )
        ingredient_documents.append(document([
            "文档类型：食材",
            f"文档ID：catalog:{catalog_id}",
            f"食材名称：{row['name']}",
            f"分类：{row['category']} / {row['subcategory']}",
            f"常见别名：{join_or_missing(aliases_sorted[:20])}",
            "营养成分：暂无可靠数据",
            "营养来源：暂无",
            "功效：暂无可靠数据",
            "适宜人群：暂无",
            "不适宜人群：暂无",
            f"适宜季节：{season_text}",
            f"适宜月份/节气/节日：{time_text}",
            f"推荐理由：{recommendation}",
            f"时令知识：{season_knowledge}",
            f"检索关键词：{join_or_missing([row['name'], *aliases_sorted[:20], row['category']])}",
            f"目录状态：{row['review_status']}；季节数据补充食材",
            "数据来源：cleaned_v2 时令食物、知识与完整食材目录",
        ]))

    expected_ingredient_documents = len(ingredients) + len(seasonal_catalog_rows)
    if len(recipe_documents) != len(dishes):
        raise RuntimeError("菜谱知识库文档数量与菜谱表不一致")
    if missing_ingredients:
        raise RuntimeError(f"存在没有食材配方的菜谱文档：{missing_ingredients}")
    if len(ingredient_documents) != expected_ingredient_documents:
        raise RuntimeError("食材知识库文档数量错误")
    if any(text.count(DOC_START) != 1 or text.count(DOC_END) != 1 for text in recipe_documents + ingredient_documents):
        raise RuntimeError("文档分隔标记错误")
    if any("\x00" in text for text in recipe_documents + ingredient_documents):
        raise RuntimeError("知识库包含 NUL 字符")

    recipe_hash = write_documents(RECIPE_TXT, recipe_documents)
    ingredient_hash = write_documents(INGREDIENT_TXT, ingredient_documents)

    print(
        f"KNOWLEDGE_OK recipes={len(recipe_documents)} ingredients={len(ingredient_documents)} "
        f"core={len(ingredients)} seasonal_extra={len(seasonal_catalog_rows)} "
        f"missing_ingredients={missing_ingredients} missing_instruction={missing_instruction} "
        f"missing_nutrition={missing_nutrition}"
    )
    print(f"RECIPE_SHA256={recipe_hash}")
    print(f"INGREDIENT_SHA256={ingredient_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
