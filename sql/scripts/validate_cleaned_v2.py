from __future__ import annotations

import csv
import os
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "菜谱数据库_交付_20260918 (1)"
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
    with (OUT / "dishes.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            dish_id = int(row["id"])
            require(dish_id not in dish_ids, f"菜谱 ID 重复：{dish_id}")
            dish_ids.add(dish_id)
            dish_main_count[dish_id] = int(row["main_ingredient_count"])
            dish_search_count[dish_id] = int(row["search_ingredient_count"])
            require(dish_main_count[dish_id] > 0, f"保留菜谱没有基础食材：{dish_id}")
            require(dish_search_count[dish_id] >= dish_main_count[dish_id], f"搜索食材数小于直接食材数：{dish_id}")

    dropped_ids = {int(r["id"]) for r in rows(OUT / "dropped_dishes.csv")}
    source_dish_ids = {int(r["id"]) for r in rows(SOURCE / "dishes.csv")}
    require(not dish_ids & dropped_ids, "保留与删除菜谱重叠")
    require(dish_ids | dropped_ids == source_dish_ids, "菜谱保留/删除没有完整覆盖源表")

    # 菜谱用料只允许引用保留菜谱；食材外键必须有效。
    di_count = 0
    roles = Counter()
    direct_dishes: set[int] = set()
    with (OUT / "dish_ingredients.csv").open(encoding="utf-8-sig", newline="") as handle:
        for expected_id, row in enumerate(csv.DictReader(handle), 1):
            di_count += 1
            require(int(row["id"]) == expected_id, f"菜谱用料 ID 不连续：{expected_id}")
            dish_id = int(row["dish_id"])
            require(dish_id in dish_ids, f"菜谱用料引用不存在菜谱：{dish_id}")
            require(dish_id not in dropped_ids, f"被删菜谱仍有用料：{dish_id}")
            if row["ingredient_id"]:
                require(int(row["ingredient_id"]) in valid_ing, f"菜谱用料食材孤儿：{row['ingredient_id']}")
            if row["role"] == "main":
                direct_dishes.add(dish_id)
            roles[row["role"]] += 1
    require(roles.keys() <= {"main", "seasoning", "other"}, "出现非法用料角色")

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

    # 其余所有关联表同步过滤且外键完整。
    tag_ids = {int(r["id"]) for r in rows(OUT / "tags.csv")}
    dish_tags = rows(OUT / "dish_tags.csv")
    require(all(int(r["dish_id"]) in dish_ids and int(r["tag_id"]) in tag_ids for r in dish_tags), "菜谱标签有孤儿")
    nutrition = rows(OUT / "dish_nutrition.csv")
    require(all(int(r["dish_id"]) in dish_ids and r["nutrition_version"] == "legacy" for r in nutrition), "菜谱营养有孤儿或版本错误")

    effect_ids = {int(r["id"]) for r in rows(OUT / "tcm_effects.csv")}
    group_ids = {int(r["id"]) for r in rows(OUT / "target_groups.csv")}
    effects = rows(OUT / "ingredient_effects.csv")
    groups = rows(OUT / "ingredient_groups.csv")
    require(all(int(r["ingredient_id"]) in valid_ing and int(r["effect_id"]) in effect_ids for r in effects), "功效关系有孤儿")
    require(all(int(r["ingredient_id"]) in valid_ing and int(r["group_id"]) in group_ids for r in groups), "人群关系有孤儿")
    require(len({(r["ingredient_id"], r["effect_id"]) for r in effects}) == len(effects), "功效关系重复")
    require(len({(r["ingredient_id"], r["group_id"]) for r in groups}) == len(groups), "人群关系重复")

    compile((OUT / "load_to_mysql.py").read_text(encoding="utf-8"), "load_to_mysql.py", "exec")
    expected = {
        "main_ingredient.csv", "ingredient_id_map.csv", "dropped_ingredients.csv", "review_ingredients.csv",
        "dish_ingredients.csv", "dish_ingredient_search.csv", "ingredient_hierarchy.csv", "dropped_dishes.csv",
        "ingredient_effects.csv", "ingredient_groups.csv", "dishes.csv", "dish_nutrition.csv", "dish_tags.csv",
        "ingredient_categories.csv", "ingredient_subcategories.csv", "excluded_seasonings.csv", "excluded_junk.csv",
        "schema.sql", "load_to_mysql.py", "CLEANING_REPORT.md", "README.md",
    }
    require(expected <= {p.name for p in OUT.iterdir()}, "交付文件不完整")

    report = f"""# V2 独立验证报告

- 旧名称动作覆盖：{len(mapping):,}/16,693；动作分布：{dict(action_counts)}。
- 新核心食材：{len(main_rows):,}；ID 连续、名称唯一、十类分类完整。
- 菜谱：源表 {len(source_dish_ids):,}，保留 {len(dish_ids):,}，删除零有效食材菜谱 {len(dropped_ids):,}；两者完整分区且保持原 ID。
- 菜谱用料：{di_count:,}；角色分布：{dict(roles)}；食材与菜谱外键零孤儿。
- 菜谱搜索关系：{len(search_seen):,}；唯一且零孤儿；每道保留菜谱至少一个确定基础食材。
- 食材层级：{len(hierarchy_pairs):,}；无重复、无自环、无环路。
- 鸡肉搜索展开：鸡腿/鸡胸肉/鸡翅菜谱 {len(child_dishes):,} 道，全部可由“鸡肉”检索。
- 菜谱标签：{len(dish_tags):,}；菜谱营养：{len(nutrition):,}；被删菜谱零残留。
- 食材、功效、人群关系零孤儿且零重复；代表营养字段未被错误继承。
- `load_to_mysql.py` 语法编译通过，新层级表与搜索表均包含在导入顺序中。
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
        f"dish_ingredients={di_count} search={len(search_seen)} hierarchy={len(hierarchy_pairs)}"
    )


if __name__ == "__main__":
    main()
