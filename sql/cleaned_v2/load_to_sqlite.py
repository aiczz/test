"""把 cleaned_v2 的 6 张 CSV 导入 SQLite。

为什么不用 load_to_mysql.py：自托管那台是 2 核 2G 的轻量服务器，跑 MySQL 太重，
后端本来就是 SQLite（shishi.db）。这里照搬它的表/列定义，只把方言换成 SQLite。

列类型是特意写清楚的 —— SQLite 靠"类型亲和性"决定怎么存，写 INTEGER/REAL 才能让
"1274" 变成数字 1274，否则 ORDER BY usage_count 会按字符串排序（"9" > "10"）。
所有约束（NOT NULL / UNIQUE / 外键）都去掉了：为 NULL 的单元格本来就会被写成
None，留着约束只会让导入半路失败。

用法（在 /opt/test/sql/cleaned_v2 目录下）：
    python3 load_to_sqlite.py --db /opt/test/back/shishi.db
    python3 load_to_sqlite.py --db /opt/test/back/shishi.db --verify

导入只动这 6 张内容表，不碰 users / my_foods 等业务表。
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (表名, CSV 文件名, 列顺序) —— 与 load_to_mysql.py 保持一致，列名即 CSV 表头。
TABLES = [
    ("ingredients", "db_ingredients.csv", [
        "id", "name", "ingredient_type", "core_ingredient_id", "category", "subcategory",
        "is_core_raw", "is_edible", "review_status", "usage_count", "reason",
        "edible", "water", "energy_kcal", "energy_kj", "protein", "fat", "cho",
        "dietary_fiber", "cholesterol", "ash", "vitamin_a", "carotene", "retinol",
        "thiamin", "riboflavin", "niacin", "vitamin_c", "vitamin_e", "ca", "p", "k",
        "na", "mg", "fe", "zn", "se", "cu", "mn", "nutrition_source", "nutrition_match",
        "quality", "category_source", "tcm_user", "tcm_not_user",
        "effects_json", "suitable_groups_json", "unsuitable_groups_json", "aliases_json",
        "parent_core_ids_json", "child_core_ids_json"]),
    ("dishes", "db_dishes.csv", [
        "id", "dish_name", "dish_name_original", "description", "cuisine",
        "ingredient_text", "instruction_text", "ingredient_count",
        "main_ingredient_count", "search_ingredient_count", "total_weight_g",
        "energy_kcal", "protein_g", "fat_g", "cho_g", "dietary_fiber_g",
        "ca_mg", "fe_mg", "na_mg", "matched_ratio", "weight_confidence",
        "explicit_count", "estimated_count", "vague_count", "suspect",
        "nutrition_version", "tags_json", "search_ingredient_ids_json"]),
    ("dish_ingredients", "db_dish_ingredients.csv", [
        "id", "dish_id", "ingredient_id", "core_ingredient_id", "raw_name", "raw_text",
        "quantity", "role", "grams", "grams_source", "component_core_ids_json"]),
    ("seasonal_calendar", "db_seasonal_calendar.csv", [
        "id", "level", "name", "gregorian_time", "lunar_time", "season", "sort_order",
        "description", "knowledge_json"]),
    ("seasonal_food", "db_seasonal_food.csv", [
        "id", "calendar_id", "level", "time_name", "season", "category", "name", "note",
        "recommendation_reason", "source", "entity_type", "ingredient_id",
        "core_ingredient_id", "match_status", "knowledge_json"]),
    ("seasonal_dish_links", "seasonal_dish_links.csv", [
        "seasonal_food_id", "dish_id", "match_type"]),
]

# 每张表的列类型：SQLite 据此决定亲和性。
INT_COLS = {
    "id", "core_ingredient_id", "is_core_raw", "is_edible", "usage_count",
    "ingredient_id", "dish_id", "ingredient_count", "main_ingredient_count",
    "search_ingredient_count", "explicit_count", "estimated_count", "vague_count",
    "suspect", "sort_order",
}
REAL_COLS = {
    "edible", "water", "energy_kcal", "energy_kj", "protein", "fat", "cho",
    "dietary_fiber", "cholesterol", "ash", "vitamin_a", "carotene", "retinol",
    "thiamin", "riboflavin", "niacin", "vitamin_c", "vitamin_e", "ca", "p", "k",
    "na", "mg", "fe", "zn", "se", "cu", "mn",
    "total_weight_g", "protein_g", "fat_g", "cho_g", "dietary_fiber_g",
    "ca_mg", "fe_mg", "na_mg", "matched_ratio", "weight_confidence", "grams",
}

# 与 MySQL 版一致的"看起来像空值"清单
NULL_LIKE_VALUES = {"", "—", "-", "NULL", "null", "Tr", "tr", "TR", "un", "UN"}


def normalise(v):
    if v is None:
        return None
    v = v.strip()
    return None if v in NULL_LIKE_VALUES else v


def col_type(col: str) -> str:
    if col in INT_COLS:
        return "INTEGER"
    if col in REAL_COLS:
        return "REAL"
    return "TEXT"


def build_ddl(table: str, cols: list[str]) -> str:
    body = ", ".join(f'"{c}" {col_type(c)}' for c in cols)
    return f'CREATE TABLE "{table}" ({body})'


def batches(reader, size=2000):
    batch = []
    for row in reader:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.getenv("SHISHI_DB", ""),
                    help="目标 SQLite 文件，例如 /opt/test/back/shishi.db")
    ap.add_argument("--verify", action="store_true",
                    help="只统计各表行数，不导入")
    args = ap.parse_args()

    if not args.db:
        print("必须用 --db 指定 sqlite 文件", file=sys.stderr)
        return 2
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"找不到 {db_path}", file=sys.stderr)
        return 2

    con = sqlite3.connect(str(db_path))
    try:
        if args.verify:
            for table, _, _ in TABLES:
                try:
                    n = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                    print(f"{table:24} {n}")
                except sqlite3.OperationalError:
                    print(f"{table:24} <表不存在>")
            return 0

        for table, filename, cols in TABLES:
            path = HERE / filename
            if not path.exists():
                print(f"缺文件 {path}", file=sys.stderr)
                return 2

            con.execute(f'DROP TABLE IF EXISTS "{table}"')
            con.execute(build_ddl(table, cols))

            collist = ",".join(f'"{c}"' for c in cols)
            marks = ",".join(["?"] * len(cols))
            sql = f'INSERT INTO "{table}" ({collist}) VALUES ({marks})'

            total = 0
            with path.open(encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                for batch in batches(reader):
                    con.executemany(
                        sql, [[normalise(r.get(c, "")) for c in cols] for r in batch]
                    )
                    total += len(batch)
            con.commit()
            print(f"loaded {table:24} {total} 行")

        con.execute("ANALYZE")
        con.commit()
        print("done")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
