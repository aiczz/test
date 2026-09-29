from __future__ import annotations

import csv
import json
import os
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from clean_v2 import (
    DISH_TARGET_COUNT, clean_dish_display_name, dish_filter_reason, extract_unsuitable_groups,
    normalized_dish_title,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "菜谱数据库_交付_20260918 (1)"
SEASONAL_SOURCE = ROOT / "seasonal_source"
OUT = ROOT / "cleaned_v2"
ZIP = ROOT / "cleaned_v2.zip"

REQUIRED_PRESENT = "葱 姜 蒜 洋葱 番茄 圣女果 黄瓜 胡萝卜 菠菜 白菜 西兰花 土豆 南瓜 苹果 香蕉 草莓 葡萄 橙子 猪肉 牛肉 羊肉 排骨 牛腩 鸡肉 鸡胸肉 鸡腿 鸡翅 鸡蛋 鸭蛋 草鱼 鲈鱼 虾 扇贝 香菇 金针菇 木耳".split()
REQUIRED_ABSENT = "盐 白糖 生抽 老抽 蚝油 料酒 番茄酱 沙拉酱 火腿 火腿肠 培根 香肠 午餐肉 肉松 面包 吐司 饼干 蛋糕 巧克力 照片 塑料袋 保温杯 一个洋葱 几个土豆 香蕉一根 半根胡萝卜 刷表面蛋液".split()


def rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def require(ok: bool, message: str):
    if not ok:
        raise AssertionError(message)


def main():
    main_rows = rows(OUT / "main_ingredient.csv")
    mapping = rows(OUT / "ingredient_id_map.csv")
    require(len(mapping) == 16693, f"映射行数错误：{len(mapping)}")
    require([int(r["old_id"]) for r in mapping] == list(range(1, 16694)), "old_id 不连续")
    require(set(r["action"] for r in mapping) <= {"KEEP", "MERGE", "DROP", "SPLIT", "REVIEW"}, "出现非法 action")
    action_counts = Counter(r["action"] for r in mapping)

    new_ids = [int(r["id"]) for r in main_rows]
    names = [r["name"] for r in main_rows]
    by_name = {r["name"]: int(r["id"]) for r in main_rows}
    category_by_id = {int(r["id"]): r["category_major"] for r in main_rows}
    valid_ing = set(new_ids)
    require(new_ids == list(range(1, len(main_rows) + 1)), "新食材 ID 不连续")
    require(len(names) == len(set(names)) and all(names), "新食材名重复或为空")
    require(not [n for n in REQUIRED_PRESENT if n not in names], "必须存在清单未通过")
    require(not [n for n in REQUIRED_ABSENT if n in names], "必须不存在清单未通过")
    require(set(r["category_major"] for r in main_rows) == {"蔬菜", "水果", "畜肉", "禽肉", "蛋类", "水产", "菌菇藻类", "薯芋", "豆类", "谷物/坚果"}, "类别集合错误")
    require(all(r["is_core_raw"] == "1" for r in main_rows), "主表存在非核心行")

    source_main = rows(SOURCE / "main_ingredient.csv")
    source_by_name = {r["name"]: r for r in source_main}
    out_by_name = {r["name"]: r for r in main_rows}
    for name in ["猪肉", "牛肉", "鸡蛋", "番茄", "苹果", "香蕉"]:
        require(out_by_name[name]["nutrition_source_name"] == source_by_name[name]["nutrition_source_name"], f"{name} 营养来源变化")
        for field in ["能量kcal", "蛋白质g", "脂肪g", "碳水化合物g"]:
            require(out_by_name[name][field] == source_by_name[name][field], f"{name} {field} 变化")

    # 菜谱保留/删除必须完整分区，ID 保持原值。
    dish_ids: set[int] = set()
    dish_main_count: dict[int, int] = {}
    dish_search_count: dict[int, int] = {}
    dish_names: dict[int, str] = {}
    with (OUT / "dishes.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            dish_id = int(row["id"])
            require(dish_id not in dish_ids, f"菜谱 ID 重复：{dish_id}")
            dish_ids.add(dish_id)
            dish_names[dish_id] = row["dish_name"]
            dish_main_count[dish_id] = int(row["main_ingredient_count"])
            dish_search_count[dish_id] = int(row["search_ingredient_count"])
            require(dish_main_count[dish_id] > 0, f"保留菜谱没有基础食材：{dish_id}")
            require(dish_search_count[dish_id] >= dish_main_count[dish_id], f"搜索食材数小于直接食材数：{dish_id}")

    name_map = rows(OUT / "dish_name_map.csv")
    require(len(name_map) == len(dish_ids), "菜名审计映射未完整覆盖保留菜谱")
    require({int(r["id"]) for r in name_map} == dish_ids, "菜名审计映射 ID 不一致")
    for row in name_map:
        expected_name, expected_rules = clean_dish_display_name(row["original_name"])
        require(row["cleaned_name"] == expected_name, f"菜名清洗结果不可复现：{row['id']}")
        require(row["rules"] == expected_rules, f"菜名清洗规则不可复现：{row['id']}")
        require(dish_names[int(row["id"])] == row["cleaned_name"], f"菜名未同步到 dishes：{row['id']}")
        require(bool(row["cleaned_name"].strip()), f"菜名清洗为空：{row['id']}")
    name_examples = {
        "西红柿肥牛汤（2人食快手菜）": "西红柿肥牛汤",
        "超美味的西红柿蛋汤": "西红柿蛋汤",
        "水煮海螺（附海螺的挑选方法）": "水煮海螺",
        "下饭菜-豆角肉丁": "豆角肉丁",
        "【杭椒牛肉】快手下饭菜": "杭椒牛肉",
    }
    mapped_examples = {r["original_name"]: r["cleaned_name"] for r in name_map}
    require(all(mapped_examples.get(k) == v for k, v in name_examples.items()), "代表菜名清洗回归失败")

    dropped_rows = rows(OUT / "dropped_dishes.csv")
    dropped_ids = {int(r["id"]) for r in dropped_rows}
    drop_type_counts = Counter(r["drop_type"] for r in dropped_rows)
    require(
        all(r["drop_type"] and r["reason"] and r["evidence"] for r in dropped_rows),
        "菜谱删除审计字段不完整",
    )
    require(
        set(drop_type_counts) <= {
            "no_core_ingredient", "unhealthy_high_signal",
            "unhealthy_sugary_beverage", "unhealthy_nutrition_density",
            "low_use_foreign", "low_priority_catalog_trim",
        },
        "出现未知菜谱删除类型",
    )
    source_dish_ids = {int(r["id"]) for r in rows(SOURCE / "dishes.csv")}
    require(not dish_ids & dropped_ids, "保留与删除菜谱重叠")
    require(dish_ids | dropped_ids == source_dish_ids, "菜谱保留/删除没有完整覆盖源表")
    require(len(dish_ids) == DISH_TARGET_COUNT, f"精选菜谱数量错误：{len(dish_ids)}")

    # 菜谱用料只允许引用保留菜谱；食材外键必须有效。
    catalog = rows(OUT / "ingredient_catalog.csv")
    catalog_ids = {int(r["id"]) for r in catalog}
    require(catalog_ids == set(range(1, len(catalog) + 1)), "完整食材目录 ID 不连续")
    require(len({r["name"] for r in catalog}) == len(catalog), "完整食材目录名称重复")
    require(all(not r["core_ingredient_id"] or int(r["core_ingredient_id"]) in valid_ing for r in catalog), "完整食材目录核心映射孤儿")
    di_count = 0
    roles = Counter()
    direct_dishes: set[int] = set()
    unresolved_shrimp = 0
    with (OUT / "dish_ingredients.csv").open(encoding="utf-8-sig", newline="") as handle:
        for expected_id, row in enumerate(csv.DictReader(handle), 1):
            di_count += 1
            require(int(row["id"]) == expected_id, f"菜谱用料 ID 不连续：{expected_id}")
            dish_id = int(row["dish_id"])
            require(dish_id in dish_ids, f"菜谱用料引用不存在菜谱：{dish_id}")
            require(dish_id not in dropped_ids, f"被删菜谱仍有用料：{dish_id}")
            if row["ingredient_id"]:
                require(int(row["ingredient_id"]) in valid_ing, f"菜谱用料食材孤儿：{row['ingredient_id']}")
            require(row["catalog_ingredient_id"], f"菜谱用料缺少完整目录关系：{expected_id}")
            require(int(row["catalog_ingredient_id"]) in catalog_ids, f"菜谱用料目录孤儿：{row['catalog_ingredient_id']}")
            if row["role"] == "main":
                direct_dishes.add(dish_id)
                require(row["ingredient_id"], f"main 用料缺少核心食材：{expected_id}")
            if row["raw_name"].strip() == "虾" and not row["ingredient_id"]:
                unresolved_shrimp += 1
            roles[row["role"]] += 1
    require(roles.keys() <= {"main", "seasoning", "processed", "composite", "other_food", "generic", "non_food"}, "出现非法用料角色")
    require(direct_dishes == dish_ids, "存在没有直接核心食材关系的保留菜谱")
    require(unresolved_shrimp == 0, f"仍有“虾”未映射：{unresolved_shrimp}")

    aliases = rows(OUT / "ingredient_catalog_aliases.csv")
    require(all(int(r["catalog_ingredient_id"]) in catalog_ids for r in aliases), "完整食材别名有孤儿")
    require(len({(r["alias_name"], r["catalog_ingredient_id"]) for r in aliases}) == len(aliases), "完整食材别名重复")
    components = rows(OUT / "dish_ingredient_components.csv")
    require(all(int(r["dish_ingredient_id"]) <= di_count and int(r["component_ingredient_id"]) in valid_ing for r in components), "复合用料组成关系有孤儿")
    require(len({(r["dish_ingredient_id"], r["component_ingredient_id"]) for r in components}) == len(components), "复合用料组成关系重复")

    # 季节数据必须与三张来源表逐行闭合，并连接到有效日历、食材目录或菜谱。
    source_calendar = rows(SEASONAL_SOURCE / "seasonal_calendar.csv")
    source_seasonal_food = rows(SEASONAL_SOURCE / "seasonal_food.csv")
    source_knowledge = rows(SEASONAL_SOURCE / "seasonal_knowledge.csv")
    calendar = rows(OUT / "seasonal_calendar.csv")
    seasonal_food = rows(OUT / "seasonal_food.csv")
    seasonal_knowledge = rows(OUT / "seasonal_knowledge.csv")
    seasonal_dish_links = rows(OUT / "seasonal_dish_links.csv")
    calendar_ids = {r["id"] for r in calendar}
    seasonal_food_ids = {r["id"] for r in seasonal_food}
    require(len(calendar) == len(source_calendar) == 52 and len(calendar_ids) == len(calendar), "季节日历数量或主键错误")
    require({r["level"] for r in calendar} == {"季节", "月份", "节气", "节日"}, "季节日历层级不完整")
    require({r["season"] for r in calendar} == {"春", "夏", "秋", "冬"}, "季节值不完整")
    require(len(seasonal_food) == len(source_seasonal_food) == 544, "时令食物数量错误")
    require(len(seasonal_food_ids) == len(seasonal_food), "时令食物主键重复")
    require(len({(r["calendar_id"], r["category"], r["name"]) for r in seasonal_food}) == len(seasonal_food), "时令食物业务键重复")
    require(all(r["calendar_id"] in calendar_ids for r in seasonal_food), "时令食物日历孤儿")
    require(all(r["entity_type"] in {"ingredient", "dish_keyword"} for r in seasonal_food), "时令实体类型非法")
    require(all(r["match_status"] in {"core_exact", "catalog_exact", "catalog_alias", "seasonal_catalog", "dish_title_keyword", "unmatched_dish_keyword"} for r in seasonal_food), "时令匹配状态非法")
    require(all(r["catalog_ingredient_id"] and int(r["catalog_ingredient_id"]) in catalog_ids for r in seasonal_food if r["entity_type"] == "ingredient"), "时令食材目录映射不完整")
    require(all(not r["catalog_ingredient_id"] for r in seasonal_food if r["entity_type"] == "dish_keyword"), "菜品关键词错误映射为食材")
    require(all(not r["core_ingredient_id"] or int(r["core_ingredient_id"]) in valid_ing for r in seasonal_food), "时令核心食材孤儿")
    require(len(seasonal_knowledge) == len(source_knowledge) == 636, "季节知识数量错误")
    require(len({r["id"] for r in seasonal_knowledge}) == len(seasonal_knowledge), "季节知识主键重复")
    require(all(r["calendar_id"] in calendar_ids for r in seasonal_knowledge), "季节知识日历孤儿")
    require(all(not r["seasonal_food_id"] or r["seasonal_food_id"] in seasonal_food_ids for r in seasonal_knowledge), "季节知识食物孤儿")
    require(sum(bool(r["seasonal_food_id"]) for r in seasonal_knowledge) == len(seasonal_food), "具体时令知识未一一覆盖时令食物")
    require(len({(r["seasonal_food_id"], r["dish_id"]) for r in seasonal_dish_links}) == len(seasonal_dish_links), "时令菜谱关系重复")
    require(all(r["seasonal_food_id"] in seasonal_food_ids and int(r["dish_id"]) in dish_ids for r in seasonal_dish_links), "时令菜谱关系孤儿")
    food_by_id = {r["id"]: r for r in seasonal_food}
    require(all(food_by_id[r["seasonal_food_id"]]["entity_type"] == "dish_keyword" for r in seasonal_dish_links), "时令菜谱关系连接了非菜品关键词")
    require(all(food_by_id[r["seasonal_food_id"]]["name"] in dish_names[int(r["dish_id"])] for r in seasonal_dish_links), "时令菜谱标题关系不可复核")
    seasonal_match_counts = Counter(r["match_status"] for r in seasonal_food)

    # 层级关系：外键有效、无自环、无环路。
    hierarchy = rows(OUT / "ingredient_hierarchy.csv")
    hierarchy_pairs = {(int(r["parent_ingredient_id"]), int(r["child_ingredient_id"])) for r in hierarchy}
    require(len(hierarchy_pairs) == len(hierarchy), "食材层级重复")
    children: dict[int, set[int]] = defaultdict(set)
    for parent_id, child_id in hierarchy_pairs:
        require(parent_id in valid_ing and child_id in valid_ing, "食材层级有孤儿")
        require(parent_id != child_id, "食材层级有自环")
        require(category_by_id[parent_id] == category_by_id[child_id], "食材层级父子分类不一致")
        children[parent_id].add(child_id)

    def reaches(start: int, target: int) -> bool:
        seen: set[int] = set()
        stack = list(children.get(start, set()))
        while stack:
            value = stack.pop()
            if value == target:
                return True
            if value not in seen:
                seen.add(value)
                stack.extend(children.get(value, set()))
        return False

    require(not any(reaches(child, parent) for parent, child in hierarchy_pairs), "食材层级存在环路")

    # 展开搜索表必须唯一、无孤儿，并和 dishes 的统计字段一致。
    search_seen: set[tuple[int, int]] = set()
    search_counts = Counter()
    direct_search_counts: dict[int, set[int]] = defaultdict(set)
    chicken_dishes: set[int] = set()
    child_dishes: set[int] = set()
    chicken_id = by_name["鸡肉"]
    chicken_children = {by_name[n] for n in ["鸡腿", "鸡胸肉", "鸡翅"]}
    with (OUT / "dish_ingredient_search.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            dish_id = int(row["dish_id"])
            ingredient_id = int(row["ingredient_id"])
            source_id = int(row["source_ingredient_id"])
            key = (dish_id, ingredient_id)
            require(key not in search_seen, f"搜索关系重复：{key}")
            search_seen.add(key)
            require(dish_id in dish_ids and dish_id not in dropped_ids, "搜索关系菜谱孤儿")
            require(ingredient_id in valid_ing and source_id in valid_ing, "搜索关系食材孤儿")
            require(row["match_type"] in {"direct", "split", "ancestor"}, "搜索匹配类型非法")
            search_counts[dish_id] += 1
            if row["match_type"] in {"direct", "split"}:
                direct_search_counts[dish_id].add(ingredient_id)
                if ingredient_id in chicken_children:
                    child_dishes.add(dish_id)
            if ingredient_id == chicken_id:
                chicken_dishes.add(dish_id)

    require(set(search_counts) == dish_ids, "存在没有搜索关系的保留菜谱")
    require(all(search_counts[d] == dish_search_count[d] for d in dish_ids), "search_ingredient_count 不一致")
    require(all(len(direct_search_counts[d]) == dish_main_count[d] for d in dish_ids), "main_ingredient_count 不一致")
    require(child_dishes and child_dishes <= chicken_dishes, "鸡肉未完整展开鸡腿/鸡胸肉/鸡翅菜谱")
    covered_direct_ingredients = set().union(*direct_search_counts.values())
    require(len(covered_direct_ingredients) >= 578, f"核心食材菜谱覆盖下降：{len(covered_direct_ingredients)}")

    # 其余所有关联表同步过滤且外键完整。
    tag_ids = {int(r["id"]) for r in rows(OUT / "tags.csv")}
    tag_names = {int(r["id"]): r["name"] for r in rows(OUT / "tags.csv")}
    dish_tags = rows(OUT / "dish_tags.csv")
    require(all(int(r["dish_id"]) in dish_ids and int(r["tag_id"]) in tag_ids for r in dish_tags), "菜谱标签有孤儿")
    nutrition = rows(OUT / "dish_nutrition.csv")
    require(all(int(r["dish_id"]) in dish_ids and r["nutrition_version"] in {"legacy", "missing"} for r in nutrition), "菜谱营养有孤儿或版本错误")
    require({int(r["dish_id"]) for r in nutrition} == dish_ids, "菜谱营养未完整覆盖保留菜谱")
    nutrition_versions = Counter(r["nutrition_version"] for r in nutrition)

    tags_by_dish: dict[int, set[str]] = defaultdict(set)
    for row in dish_tags:
        tags_by_dish[int(row["dish_id"])].add(tag_names[int(row["tag_id"])])
    nutrition_by_dish = {int(r["dish_id"]): r for r in nutrition}
    residual_quality_drops = [
        dish_id
        for dish_id, dish_name in dish_names.items()
        if dish_filter_reason(
            dish_name,
            tags_by_dish.get(dish_id, set()),
            nutrition_by_dish.get(dish_id),
        )
    ]
    require(not residual_quality_drops, f"保留菜谱仍命中删减规则：{residual_quality_drops[:10]}")

    representative_staples = ["番茄炒蛋", "红烧肉", "宫保鸡丁", "鱼香肉丝", "麻婆豆腐"]
    staple_counts = {
        staple: sum(staple in name for name in dish_names.values())
        for staple in representative_staples
    }
    require(all(staple_counts.values()), f"代表性家常中餐被删空：{staple_counts}")
    normalized_title_counts = Counter(normalized_dish_title(name) for name in dish_names.values())

    effect_ids = {int(r["id"]) for r in rows(OUT / "tcm_effects.csv")}
    target_group_rows = rows(OUT / "target_groups.csv")
    group_ids = {int(r["id"]) for r in target_group_rows}
    group_names = {int(r["id"]): r["name"] for r in target_group_rows}
    effects = rows(OUT / "ingredient_effects.csv")
    groups = rows(OUT / "ingredient_groups.csv")
    require(all(int(r["ingredient_id"]) in valid_ing and int(r["effect_id"]) in effect_ids for r in effects), "功效关系有孤儿")
    require(all(int(r["ingredient_id"]) in valid_ing and int(r["group_id"]) in group_ids for r in groups), "人群关系有孤儿")
    require(len({(r["ingredient_id"], r["effect_id"]) for r in effects}) == len(effects), "功效关系重复")
    require(len({(r["ingredient_id"], r["group_id"], r["is_suitable"]) for r in groups}) == len(groups), "人群关系重复")
    require(all(r["is_suitable"] in {"0", "1"} and r["evidence_source"] and r["evidence_text"] for r in groups), "人群关系缺少方向或证据")
    suitable_group_count = sum(r["is_suitable"] == "1" for r in groups)
    unsuitable_group_count = sum(r["is_suitable"] == "0" for r in groups)
    require(suitable_group_count > 0 and unsuitable_group_count > 0, "人群关系缺少正向或负向数据")
    positive_group_pairs = {(r["ingredient_id"], r["group_id"]) for r in groups if r["is_suitable"] == "1"}
    negative_group_pairs = {(r["ingredient_id"], r["group_id"]) for r in groups if r["is_suitable"] == "0"}
    require(not positive_group_pairs & negative_group_pairs, "同一食材和人群同时存在正负关系")
    extraction_audit = rows(OUT / "ingredient_group_extraction_audit.csv")
    require(len(extraction_audit) == sum(bool(r["tcm_not_user"].strip()) for r in main_rows), "禁忌解析审计未覆盖全部非空原文")
    for row in extraction_audit:
        extracted_names = [name for name, _ in extract_unsuitable_groups(row["tcm_not_user"])]
        require(json.loads(row["extracted_groups_json"]) == list(dict.fromkeys(extracted_names)), f"禁忌解析不可复现：{row['ingredient_id']}")
    negative_pairs = {(int(r["ingredient_id"]), group_names[int(r["group_id"])]) for r in groups if r["is_suitable"] == "0"}
    require((by_name["鸡蛋"], "高血压患者") in negative_pairs, "鸡蛋高血压禁忌未结构化")
    require((by_name["薄荷"], "孕妇") in negative_pairs, "薄荷孕妇禁忌未结构化")
    require((by_name["西瓜"], "糖尿病患者") in negative_pairs, "西瓜糖尿病禁忌未结构化")

    # MySQL 运行结构只保留 6 张表，所有合并 JSON 和外键均可解析、可闭合。
    runtime_ingredients = rows(OUT / "db_ingredients.csv")
    runtime_dishes = rows(OUT / "db_dishes.csv")
    runtime_di = rows(OUT / "db_dish_ingredients.csv")
    runtime_calendar = rows(OUT / "db_seasonal_calendar.csv")
    runtime_food = rows(OUT / "db_seasonal_food.csv")
    require(len(runtime_ingredients) == len(catalog), "运行食材表数量错误")
    require(len(runtime_dishes) == len(dish_ids), "运行菜谱表数量错误")
    require(len(runtime_di) == di_count, "运行菜谱用料表数量错误")
    require(len(runtime_calendar) == len(calendar), "运行季节日历表数量错误")
    require(len(runtime_food) == len(seasonal_food), "运行时令食物表数量错误")
    runtime_ingredient_ids = {int(r["id"]) for r in runtime_ingredients}
    require(runtime_ingredient_ids == catalog_ids, "运行食材表 ID 与完整目录不一致")
    require(all(int(r["dish_id"]) in dish_ids and int(r["ingredient_id"]) in runtime_ingredient_ids for r in runtime_di), "运行菜谱用料存在孤儿")
    require(all(not r["core_ingredient_id"] or int(r["core_ingredient_id"]) in valid_ing for r in runtime_di), "运行菜谱用料核心食材孤儿")
    require(all(r["calendar_id"] in calendar_ids for r in runtime_food), "运行时令食物日历孤儿")
    require(all(not r["ingredient_id"] or int(r["ingredient_id"]) in runtime_ingredient_ids for r in runtime_food), "运行时令食物食材孤儿")
    json_columns = [
        (runtime_ingredients, ["effects_json", "suitable_groups_json", "unsuitable_groups_json", "aliases_json", "parent_core_ids_json", "child_core_ids_json"]),
        (runtime_dishes, ["tags_json", "search_ingredient_ids_json"]),
        (runtime_di, ["component_core_ids_json"]),
        (runtime_calendar, ["knowledge_json"]),
        (runtime_food, ["knowledge_json"]),
    ]
    for table_rows, fields in json_columns:
        for row in table_rows:
            for field in fields:
                require(isinstance(json.loads(row[field]), list), f"运行 JSON 列非法：{field}")
    runtime_ingredient_by_name = {r["name"]: r for r in runtime_ingredients}
    require("高血压患者" in json.loads(runtime_ingredient_by_name["鸡蛋"]["unsuitable_groups_json"]), "运行表未合并鸡蛋禁忌人群")
    require("孕妇" in json.loads(runtime_ingredient_by_name["薄荷"]["unsuitable_groups_json"]), "运行表未合并薄荷禁忌人群")
    require("糖尿病患者" in json.loads(runtime_ingredient_by_name["西瓜"]["unsuitable_groups_json"]), "运行表未合并西瓜禁忌人群")
    schema = (OUT / "schema.sql").read_text(encoding="utf-8")
    schema_tables = re.findall(r"CREATE TABLE\s+([a-z_]+)\s*\(", schema, flags=re.I)
    runtime_tables = ["ingredients", "dishes", "dish_ingredients", "seasonal_calendar", "seasonal_food", "seasonal_dish_links"]
    require(schema_tables == runtime_tables, f"运行表结构不是预期 6 表：{schema_tables}")

    compile((OUT / "load_to_mysql.py").read_text(encoding="utf-8"), "load_to_mysql.py", "exec")
    expected = {
        "main_ingredient.csv", "ingredient_id_map.csv", "dropped_ingredients.csv", "review_ingredients.csv",
        "ingredient_catalog.csv", "ingredient_catalog_aliases.csv", "dish_ingredient_components.csv",
        "dish_ingredients.csv", "dish_ingredient_search.csv", "ingredient_hierarchy.csv", "dropped_dishes.csv",
        "ingredient_effects.csv", "ingredient_groups.csv", "ingredient_group_extraction_audit.csv", "dishes.csv", "dish_nutrition.csv", "dish_tags.csv",
        "ingredient_categories.csv", "ingredient_subcategories.csv", "excluded_seasonings.csv", "excluded_junk.csv",
        "seasonal_calendar.csv", "seasonal_food.csv", "seasonal_knowledge.csv", "seasonal_dish_links.csv",
        "dish_name_map.csv", "db_ingredients.csv", "db_dishes.csv", "db_dish_ingredients.csv",
        "db_seasonal_calendar.csv", "db_seasonal_food.csv",
        "schema.sql", "load_to_mysql.py", "CLEANING_REPORT.md", "README.md",
    }
    require(expected <= {p.name for p in OUT.iterdir()}, "交付文件不完整")

    report = f"""# V2 独立验证报告

- 旧名称动作覆盖：{len(mapping):,}/16,693；动作分布：{dict(action_counts)}。
- 新核心食材：{len(main_rows):,}；ID 连续、名称唯一、十类分类完整。
- 菜谱：源表 {len(source_dish_ids):,}，保留 {len(dish_ids):,}，删除 {len(dropped_ids):,}；删除类型分布：{dict(drop_type_counts)}。
- 菜名规范：修改 {sum(r['changed'] == '1' for r in name_map):,}/{len(name_map):,}，原名、结果和规则可逐行复核。
- 菜谱删减规则回归：保留集零残留命中；代表家常菜保留数量：{staple_counts}。
- 精选库：目标 {DISH_TARGET_COUNT:,} 道，直接/拆分食材覆盖 {len(covered_direct_ingredients):,}/590；规范同名标题最大保留 {max(normalized_title_counts.values()):,} 道。
- 菜谱用料：{di_count:,}；角色分布：{dict(roles)}；每条均有非空完整目录 ID，目录外键零孤儿。
- 完整食材目录：{len(catalog):,}；别名 {len(aliases):,}；复合用料组成关系 {len(components):,}；每道保留菜谱至少一个直接核心食材。
- 菜谱搜索关系：{len(search_seen):,}；唯一且零孤儿；每道保留菜谱至少一个确定基础食材。
- 食材层级：{len(hierarchy_pairs):,}；无重复、无自环、无环路。
- 鸡肉搜索展开：鸡腿/鸡胸肉/鸡翅菜谱 {len(child_dishes):,} 道，全部可由“鸡肉”检索。
- 季节数据：日历 {len(calendar):,}、时令食物 {len(seasonal_food):,}、知识 {len(seasonal_knowledge):,}、菜谱标题关系 {len(seasonal_dish_links):,}；匹配状态 {dict(seasonal_match_counts)}。
- 季节关联：日历、完整食材目录、核心食材、知识和精选菜谱外键均零孤儿；具体食物知识 {sum(bool(r['seasonal_food_id']) for r in seasonal_knowledge):,}/{len(seasonal_food):,} 一一覆盖。
- 菜谱标签：{len(dish_tags):,}；菜谱营养：{len(nutrition):,}，版本分布 {dict(nutrition_versions)}；被删菜谱零残留。
- 食材、功效、人群关系零孤儿且零重复；代表营养字段未被错误继承。
- 人群关系：适宜 {suitable_group_count:,} 条，不适宜 {unsuitable_group_count:,} 条；方向存放在食材×人群关系并保留证据原句。
- MySQL 运行结构：23 张明细表合并为 6 张业务表；运行数据数量分别为 {len(runtime_ingredients):,}/{len(runtime_dishes):,}/{len(runtime_di):,}/{len(runtime_calendar):,}/{len(runtime_food):,}/{len(seasonal_dish_links):,}。
- `load_to_mysql.py` 语法编译通过，6 张运行表的合并字段、JSON 与外键全部校验通过。
"""
    (OUT / "VALIDATION_REPORT.md").write_text(report, encoding="utf-8")

    tmp = ZIP.with_suffix(".zip.validating")
    if tmp.exists():
        tmp.unlink()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, Path("cleaned_v2") / path.relative_to(OUT))
    os.replace(tmp, ZIP)
    print(
        f"VALID ingredients={len(main_rows)} dishes={len(dish_ids)} dropped={len(dropped_ids)} "
        f"dish_ingredients={di_count} search={len(search_seen)} hierarchy={len(hierarchy_pairs)} "
        f"seasonal_food={len(seasonal_food)} seasonal_links={len(seasonal_dish_links)}"
    )


if __name__ == "__main__":
    main()
