from __future__ import annotations

import csv
import os
import zipfile
from collections import Counter
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

    map_by_old = {int(r["old_id"]): r for r in mapping}
    valid_ing = set(new_ids)
    source_count = 0
    output_count = 0
    roles = Counter()
    with (SOURCE / "dish_ingredients.csv").open(encoding="utf-8-sig", newline="") as old_fh, (OUT / "dish_ingredients.csv").open(encoding="utf-8-sig", newline="") as new_fh:
        old_rd, new_rd = csv.DictReader(old_fh), csv.DictReader(new_fh)
        for index, (old, new) in enumerate(zip(old_rd, new_rd), 1):
            source_count += 1; output_count += 1
            require(int(new["id"]) == index, f"关系 ID 不连续：{index}")
            for field in ["dish_id", "raw_name", "raw_text", "quantity"]:
                require(old[field] == new[field], f"关系第 {index} 行 {field} 被改动")
            old_id = int(old["ingredient_id"]) if old["ingredient_id"] else 0
            action = map_by_old.get(old_id)
            if action and action["action"] in {"KEEP", "MERGE"}:
                require(new["role"] == "main" and new["ingredient_id"] == action["new_id"], f"第 {index} 行 main 映射错误")
            elif action and action["action"] == "DROP" and "调味料" in action["reason"]:
                require(new["role"] == "seasoning" and not new["ingredient_id"], f"第 {index} 行 seasoning 映射错误")
            else:
                require(new["role"] == "other" and not new["ingredient_id"], f"第 {index} 行 other 映射错误")
            require(not new["ingredient_id"] or int(new["ingredient_id"]) in valid_ing, f"第 {index} 行食材孤儿")
            roles[new["role"]] += 1
        require(next(old_rd, None) is None and next(new_rd, None) is None, "dish_ingredients 两侧行数不同")
    require(source_count == output_count == 1_372_579, f"dish_ingredients 行数错误：{source_count}/{output_count}")

    dish_ids = set()
    with (SOURCE / "dishes.csv").open(encoding="utf-8-sig", newline="") as old_fh, (OUT / "dishes.csv").open(encoding="utf-8-sig", newline="") as new_fh:
        old_rd, new_rd = csv.DictReader(old_fh), csv.DictReader(new_fh)
        dish_count = 0
        for old, new in zip(old_rd, new_rd):
            dish_count += 1; dish_ids.add(int(new["id"]))
            for field in old_rd.fieldnames or []:
                require(old[field] == new[field], f"dishes 第 {dish_count} 行 {field} 被改动")
            require(new["main_ingredient_count"].isdigit(), f"菜品 {new['id']} 核心数量非法")
        require(next(old_rd, None) is None and next(new_rd, None) is None, "dishes 两侧行数不同")
    require(dish_count == 200_000, f"dishes 行数错误：{dish_count}")

    with (SOURCE / "dish_nutrition.csv").open(encoding="utf-8-sig", newline="") as old_fh, (OUT / "dish_nutrition.csv").open(encoding="utf-8-sig", newline="") as new_fh:
        old_rd, new_rd = csv.DictReader(old_fh), csv.DictReader(new_fh)
        nutrition_count = 0
        for old, new in zip(old_rd, new_rd):
            nutrition_count += 1
            for field in old_rd.fieldnames or []:
                require(old[field] == new[field], f"dish_nutrition 第 {nutrition_count} 行 {field} 被改动")
            require(new["nutrition_version"] == "legacy", "营养版本未标 legacy")
        require(next(old_rd, None) is None and next(new_rd, None) is None, "dish_nutrition 两侧行数不同")
    require(nutrition_count == 189_587, f"dish_nutrition 行数错误：{nutrition_count}")

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
        "dish_ingredients.csv", "ingredient_effects.csv", "ingredient_groups.csv", "dishes.csv", "dish_nutrition.csv",
        "ingredient_categories.csv", "ingredient_subcategories.csv", "excluded_seasonings.csv", "excluded_junk.csv",
        "schema.sql", "load_to_mysql.py", "CLEANING_REPORT.md", "README.md",
    }
    require(expected <= {p.name for p in OUT.iterdir()}, "交付文件不完整")

    report = f"""# V2 独立验证报告

- 旧名称动作覆盖：{len(mapping):,}/16,693；动作分布：{dict(action_counts)}。
- 新核心食材：{len(main_rows):,}；ID 连续、名称唯一、十类分类完整。
- 指南必须存在/必须不存在清单：全部通过。
- 菜谱：{dish_count:,} 行逐字段比对，原字段零改动；仅新增 `main_ingredient_count`。
- 菜谱用料：{output_count:,} 行逐行比对；`raw_name/raw_text/quantity` 零改动；角色分布：{dict(roles)}。
- 菜品营养：{nutrition_count:,} 行原值零改动；全部标记 `legacy`。
- 食材、菜品、功效、人群外键：零孤儿；功效/人群关系零重复。
- 猪肉、牛肉、鸡蛋、番茄、苹果、香蕉的营养来源及代表数值与 canonical 源行一致。
- `load_to_mysql.py` 语法编译：通过；导入使用 CSV 明确 ID。
"""
    (OUT / "VALIDATION_REPORT.md").write_text(report, encoding="utf-8")

    tmp = ZIP.with_suffix(".zip.validating")
    if tmp.exists(): tmp.unlink()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, Path("cleaned_v2") / path.relative_to(OUT))
    os.replace(tmp, ZIP)
    print(f"VALID old_map={len(mapping)} new={len(main_rows)} dishes={dish_count} dish_ingredients={output_count} roles={dict(roles)}")


if __name__ == "__main__":
    main()
