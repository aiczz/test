"""把 build/*.csv 导入 MySQL。

为什么要这个脚本
----------------
CSV 的列名和表字段名**不是一一对应**的：

  * main_ingredient.csv 的营养素列是中文（能量kcal / 蛋白质g …），
    表字段是英文（energy_kcal / protein …）；
  * main_ingredient.csv 只有「大类名/子类名」，表里要的是 category_id / subcategory_id；
  * dishes.csv 多一个 cuisine 字段、ingredient_text 里有换行。

手写 INSERT 很容易对错列、也容易被换行坑。
这个脚本用「先全字段进临时表，再用 INSERT…SELECT 映射」的方式导入，
既快（LOAD DATA）又不会错位。

用法
----
    # 用环境变量传连接信息（推荐，不要把密码写进代码）
    set MYSQL_HOST=localhost
    set MYSQL_USER=root
    set MYSQL_PASSWORD=你的密码
    set MYSQL_DB=recipe_db

    python load_to_mysql.py                 # 建库建表 + 全量导入
    python load_to_mysql.py --tables ingredients,dishes
    python load_to_mysql.py --verify        # 只跑校验查询

注意
----
需要一个 `--local-infile=1` 的 MySQL 服务端（脚本会尝试自动打开）。
如果打不开，会退化为逐行 executemany（慢，但结果一样）。
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time

import pymysql

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 连接信息
# ---------------------------------------------------------------------------
DB = {
    "host": os.environ.get("MYSQL_HOST", "localhost"),
    "port": int(os.environ.get("MYSQL_PORT", "3306")),
    "user": os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DB", "recipe_db"),
    "charset": "utf8mb4",
    "local_infile": True,
}


def connect(with_db: bool = True):
    cfg = dict(DB)
    if not with_db:
        cfg.pop("database")
    return pymysql.connect(**cfg)


# ---------------------------------------------------------------------------
# 表清单：表名 -> (CSV 文件, [(表字段, CSV 列名 | None)])
# CSV 列名为 None 表示该字段不由这个 CSV 提供（留默认值）
# 字段顺序即 INSERT 顺序。
# ---------------------------------------------------------------------------

NUTRI_MAP = [
    ("edible", "可食部%"),
    ("water", "水分g"),
    ("energy_kcal", "能量kcal"),
    ("energy_kj", "能量kJ"),
    ("protein", "蛋白质g"),
    ("fat", "脂肪g"),
    ("cho", "碳水化合物g"),
    ("dietary_fiber", "膳食纤维g"),
    ("cholesterol", "胆固醇mg"),
    ("ash", "灰分g"),
    ("vitamin_a", "维生素A(ugRE)"),
    ("carotene", "胡萝卜素(ug)"),
    ("retinol", "视黄醇(ug)"),
    ("thiamin", "硫胺素mg"),
    ("riboflavin", "核黄素mg"),
    ("niacin", "烟酸mg"),
    ("vitamin_c", "维生素Cmg"),
    ("vitamin_e", "维生素E总mg"),
    ("ca", "钙mg"),
    ("p", "磷mg"),
    ("k", "钾mg"),
    ("na", "钠mg"),
    ("mg", "镁mg"),
    ("fe", "铁mg"),
    ("zn", "锌mg"),
    ("se", "硒(ug)"),
    ("cu", "铜mg"),
    ("mn", "锰mg"),
]

TABLES: dict[str, dict] = {
    "ingredient_categories": {
        "csv": "ingredient_categories.csv",
        "cols": [("id", "id"), ("name", "name"), ("sort_order", "sort_order")],
        "explicit_id": True,
    },
    "ingredient_subcategories": {
        "csv": "ingredient_subcategories.csv",
        "cols": [("id", "id"), ("category_id", "category_id"),
                 ("name", "name"), ("sort_order", "sort_order")],
        "explicit_id": True,
    },
    "ingredients": {
        "csv": "main_ingredient.csv",
        "cols": ([("name", "name"), ("usage_count", "usage_count"),
                  ("quality", "quality"), ("category_source", "category_source")]
                 + NUTRI_MAP
                 + [("nutrition_source", "nutrition_source_name"),
                    ("tcm_user", "tcm_user"), ("tcm_not_user", "tcm_not_user")]),
        # 宁可直接报错：ingredients.name 是 UNIQUE，
        # 如果出现"归一化后同名"的行，必须让人看见，不能静默少数据
        "ignore": False,
        # 营养素列里"没测"写作 '—'，必须当 NULL
        "numeric": [cn for _, cn in NUTRI_MAP] + ["usage_count"],
        # category_id / subcategory_id 由导入后两条 UPDATE 补
        "post_sql": [
            "UPDATE ingredients i "
            "  JOIN _stage_ingredients s ON s.name = i.name "
            "  JOIN ingredient_categories c "
            "    ON c.name = NULLIF(s.category_major, '') "
            "SET i.category_id = c.id",
            "UPDATE ingredients i "
            "  JOIN _stage_ingredients s ON s.name = i.name "
            "  JOIN ingredient_subcategories sc "
            "    ON sc.name = NULLIF(s.category_sub, '') "
            "   AND sc.category_id = i.category_id "
            "SET i.subcategory_id = sc.id",
        ],
    },
    "tcm_effects": {
        "csv": "tcm_effects.csv",
        "cols": [("id", "id"), ("name", "name")],
        "explicit_id": True,
    },
    "ingredient_effects": {
        "csv": "ingredient_effects.csv",
        "cols": [("ingredient_id", "ingredient_id"),
                 ("effect_id", "effect_id")],
    },
    "target_groups": {
        "csv": "target_groups.csv",
        "cols": [("id", "id"), ("name", "name"),
                 ("is_suitable", "is_suitable")],
        "explicit_id": True,
    },
    "ingredient_groups": {
        "csv": "ingredient_groups.csv",
        "cols": [("ingredient_id", "ingredient_id"),
                 ("group_id", "group_id")],
    },
    "dishes": {
        "csv": "dishes.csv",
        "cols": [("id", "id"), ("dish_name", "dish_name"),
                 ("description", "description"), ("cuisine", "cuisine"),
                 ("ingredient_text", "ingredient_text"),
                 ("instruction_text", "instruction_text"),
                 ("ingredient_count", "ingredient_count"),
                 ("total_weight_g", "total_weight_g")],
        "explicit_id": True,
        "numeric": ["id", "ingredient_count", "total_weight_g"],
        "notnull": {"dish_name": ""},
    },
    "dish_ingredients": {
        "csv": "dish_ingredients.csv",
        "cols": [("dish_id", "dish_id"), ("ingredient_id", "ingredient_id"),
                 ("raw_name", "raw_name"), ("raw_text", "raw_text"),
                 ("quantity", "quantity"), ("role", "role"),
                 ("grams", "grams"), ("grams_source", "grams_source")],
        # 没有自然主键，但外键必须成立 —— 用普通 INSERT，脏外键会直接报错
        "ignore": False,
        "numeric": ["dish_id", "ingredient_id", "grams"],
        "notnull": {"raw_name": "", "raw_text": ""},
    },
    "tags": {
        "csv": "tags.csv",
        "cols": [("id", "id"), ("name", "name"), ("kind", "kind")],
        "explicit_id": True,
    },
    "dish_tags": {
        "csv": "dish_tags.csv",
        "cols": [("dish_id", "dish_id"), ("tag_id", "tag_id")],
    },
    "dish_nutrition": {
        "csv": "dish_nutrition.csv",
        "cols": [("dish_id", "dish_id"), ("total_weight_g", "total_weight_g"),
                 ("energy_kcal", "energy_kcal"), ("protein_g", "protein_g"),
                 ("fat_g", "fat_g"), ("cho_g", "cho_g"),
                 ("dietary_fiber_g", "dietary_fiber_g"),
                 ("ca_mg", "ca_mg"), ("fe_mg", "fe_mg"), ("na_mg", "na_mg"),
                 ("matched_ratio", "matched_ratio"),
                 ("weight_confidence", "weight_confidence"),
                 ("explicit_count", "explicit_count"),
                 ("estimated_count", "estimated_count"),
                 ("vague_count", "vague_count"), ("suspect", "suspect")],
        "numeric": ["dish_id", "total_weight_g", "energy_kcal", "protein_g",
                    "fat_g", "cho_g", "dietary_fiber_g", "ca_mg", "fe_mg",
                    "na_mg", "matched_ratio", "weight_confidence",
                    "explicit_count", "estimated_count", "vague_count",
                    "suspect"],
    },
    "seasonings": {
        "csv": "excluded_seasonings.csv",
        "cols": [("name", "name"), ("usage_count", "usage_count"),
                 ("reason", "reason")],
        "numeric": ["usage_count"],
    },
    "excluded_names": {
        "csv": "excluded_junk.csv",
        "cols": [("name", "name"), ("reason", "reason")],
    },
}

# 建表顺序（外键依赖）
ORDER = [
    "ingredient_categories", "ingredient_subcategories", "ingredients",
    "tcm_effects", "ingredient_effects",
    "target_groups", "ingredient_groups",
    "dishes", "dish_ingredients", "tags", "dish_tags", "dish_nutrition",
    "seasonings", "excluded_names",
]


# ---------------------------------------------------------------------------
# CSV -> 临时 TSV（把换行/制表符转义，让 LOAD DATA 安全）
# ---------------------------------------------------------------------------
def csv_to_tsv(csv_path: str, tsv_path: str) -> int:
    n = 0
    with open(csv_path, encoding="utf-8-sig", newline="") as src, \
            open(tsv_path, "w", encoding="utf-8", newline="") as dst:
        rd = csv.reader(src)
        header = next(rd)
        for row in rd:
            out = []
            for v in row:
                if v is None or v == "":
                    out.append("\\N")
                    continue
                v = (v.replace("\\", "\\\\")
                      .replace("\t", "\\t")
                      .replace("\n", "\\n")
                      .replace("\r", "\\r"))
                out.append(v)
            dst.write("\t".join(out))
            dst.write("\n")
            n += 1
    return n


def _num_expr(source: str, numeric: bool, default=None) -> str:
    """把 CSV 列转成可安全写入 DECIMAL/INT 的表达式。

    《中国食物成分表》里"没测"是用 '—' 表示的，不是空。
    直接塞进 DECIMAL 会报 1366 Incorrect decimal value。
    所以只放行真正的数字，其余一律当 NULL。

    default 不为 None 时，最后再套一层 IFNULL：
    用于 NOT NULL 的字符串列（语料里有 emoji-only 的名字，
    MySQL 转换后可能落成 NULL，会报 1048）。
    """
    v = f"NULLIF(`{source}`, '')"
    if numeric:
        # 只用 [.] 不用 \\. ，避免 Python -> SQL 的反斜杠转义问题
        v = (f"CASE WHEN {v} REGEXP '^-?[0-9]+([.][0-9]+)?$' "
             f"THEN {v} ELSE NULL END")
    if default is not None:
        lit = "'" + str(default).replace("'", "''") + "'"
        v = f"IFNULL({v}, {lit})"
    return v


def load_table(conn, table: str, spec: dict, force_slow: bool = False) -> int:
    csv_path = os.path.join(HERE, spec["csv"])
    if not os.path.exists(csv_path):
        print(f"  [跳过] 没有 {spec['csv']}")
        return 0

    cols = [c for c, _ in spec["cols"]]
    numeric = set(spec.get("numeric", ()))
    notnull = spec.get("notnull", {})
    stage = f"_stage_{table}"
    cur = conn.cursor()

    # 临时表：把 CSV 的**原始列名**原样建出来，方便 INSERT…SELECT 引用
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        csv_header = next(csv.reader(f))
    cur.execute(f"DROP TEMPORARY TABLE IF EXISTS `{stage}`")
    defs = ",\n  ".join(f"`{h}` TEXT" for h in csv_header)
    cur.execute(f"CREATE TEMPORARY TABLE `{stage}` (\n  {defs}\n) "
                f"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")

    t0 = time.time()
    if force_slow:
        n = _load_slow(cur, stage, csv_path, csv_header)
    else:
        n = _load_fast(conn, cur, stage, csv_path)

    # 映射列
    select = []
    for target, source in spec["cols"]:
        if source is None:
            select.append("NULL")
        else:
            select.append(_num_expr(source, source in numeric,
                                    notnull.get(target)))
    # ignore=False 的表不用 IGNORE：宁可直接报错，也不要静默少数据。
    # （默认：有显式主键的表不用 IGNORE，其余用 IGNORE 跳过重复行）
    ignore = spec.get("ignore", not spec.get("explicit_id"))
    skip = "IGNORE" if ignore else ""
    sql = (f"INSERT {skip} INTO `{table}` ({', '.join('`' + c + '`' for c in cols)}) "
           f"SELECT {', '.join(select)} FROM `{stage}`")
    cur.execute(sql)
    conn.commit()

    for extra in spec.get("post_sql", []):
        cur.execute(extra)
    conn.commit()
    print(f"  {table:24s} {n:>9,} 行  ({time.time() - t0:.1f}s)")
    return n


def _load_fast(conn, cur, stage: str, csv_path: str) -> int:
    """LOAD DATA LOCAL INFILE：快，但要服务端允许。"""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False)
    tmp.close()
    n = csv_to_tsv(csv_path, tmp.name)
    p = tmp.name.replace("\\", "\\\\")
    cur.execute(
        f"LOAD DATA LOCAL INFILE '{p}' INTO TABLE `{stage}` "
        f"CHARACTER SET utf8mb4 "
        f"FIELDS TERMINATED BY '\\t' ESCAPED BY '\\\\' "
        f"LINES TERMINATED BY '\\n'")
    os.unlink(tmp.name)
    return n


def _load_slow(cur, stage: str, csv_path: str, header: list) -> int:
    """executemany 兜底：慢，但一定能跑。"""
    ph = ", ".join(["%s"] * len(header))
    sql = (f"INSERT INTO `{stage}` "
           f"({', '.join('`' + h + '`' for h in header)}) VALUES ({ph})")
    n, batch = 0, []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        for r in rd:
            batch.append([r.get(h) or None for h in header])
            if len(batch) >= 5000:
                cur.executemany(sql, batch)
                n += len(batch)
                batch = []
        if batch:
            cur.executemany(sql, batch)
            n += len(batch)
    return n


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
VERIFY = [
    ("食材总数", "SELECT COUNT(*) FROM ingredients"),
    ("  有分类", "SELECT COUNT(*) FROM ingredients WHERE category_id IS NOT NULL"),
    ("  core+common", "SELECT COUNT(*) FROM ingredients WHERE quality IN ('core','common')"),
    ("菜品总数", "SELECT COUNT(*) FROM dishes"),
    ("菜-食材行数", "SELECT COUNT(*) FROM dish_ingredients"),
    ("  挂上食材的行", "SELECT COUNT(*) FROM dish_ingredients WHERE ingredient_id IS NOT NULL"),
    ("菜-标签行数", "SELECT COUNT(*) FROM dish_tags"),
    ("菜品营养行数", "SELECT COUNT(*) FROM dish_nutrition"),
    ("调味料字典", "SELECT COUNT(*) FROM seasonings"),
    ("剔除名单", "SELECT COUNT(*) FROM excluded_names"),
    ("外键脏数据: 菜-食材->食材",
     "SELECT COUNT(*) FROM dish_ingredients di LEFT JOIN ingredients i "
     "ON i.id = di.ingredient_id WHERE di.ingredient_id IS NOT NULL AND i.id IS NULL"),
    ("外键脏数据: 菜-食材->菜品",
     "SELECT COUNT(*) FROM dish_ingredients di LEFT JOIN dishes d "
     "ON d.id = di.dish_id WHERE d.id IS NULL"),
    ("外键脏数据: 菜-标签->标签",
     "SELECT COUNT(*) FROM dish_tags dt LEFT JOIN tags t "
     "ON t.id = dt.tag_id WHERE t.id IS NULL"),
    ("番茄能做的菜",
     "SELECT COUNT(DISTINCT di.dish_id) FROM dish_ingredients di "
     "JOIN ingredients i ON i.id = di.ingredient_id WHERE i.name = '番茄'"),
    ("西红柿炒鸡蛋(样例)",
     "SELECT id, dish_name, ingredient_count, total_weight_g FROM dishes "
     "WHERE dish_name LIKE '%西红柿炒鸡蛋%' LIMIT 3"),
]


def verify(conn):
    cur = conn.cursor()
    print("\n" + "=" * 66)
    print("导入结果校验")
    print("=" * 66)
    for label, sql in VERIFY:
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            if len(rows) == 1 and len(rows[0]) == 1:
                print(f"  {label:26s} {rows[0][0]}")
            else:
                for r in rows:
                    print(f"  {label:26s} {r}")
        except Exception as e:
            print(f"  {label:26s} 查询失败: {e}")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", default="",
                    help="只导入这些表，逗号分隔；默认全部")
    ap.add_argument("--verify", action="store_true", help="只跑校验")
    ap.add_argument("--slow", action="store_true",
                    help="不用 LOAD DATA，走 executemany（慢但兼容）")
    ap.add_argument("--no-schema", action="store_true", help="不建表")
    ap.add_argument("--truncate", action="store_true",
                    help="导入前清空目标表（重复导入同一张表时用）")
    args = ap.parse_args()

    conn = connect(with_db=args.verify or args.no_schema or bool(args.tables))
    cur = conn.cursor()
    if not args.verify and not args.no_schema:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB['database']}` "
                    f"DEFAULT CHARSET=utf8mb4")
        cur.execute(f"USE `{DB['database']}`")
        schema = os.path.join(HERE, "schema.sql")
        if os.path.exists(schema) and not args.tables:
            print(f"执行 {os.path.basename(schema)} …")
            with open(schema, encoding="utf-8") as f:
                for stmt in _split_sql(f.read()):
                    cur.execute(stmt)
            conn.commit()

    if args.verify:
        verify(conn)
        return

    # local_infile 是**连接时**读取的服务端变量，所以要先改 GLOBAL 再重连
    if not args.slow:
        try:
            cur.execute("SET GLOBAL local_infile = 1")
            conn.commit()
            conn.close()
            conn = connect()
            cur = conn.cursor()
            print("local_infile 已开启（LOAD DATA 快速导入）")
        except Exception as e:
            print(f"（无法开启 local_infile: {e}；改用慢速导入）")
            args.slow = True

    want = [t.strip() for t in args.tables.split(",") if t.strip()] or ORDER
    print(f"\n导入 {len(want)} 张表 -> {DB['database']}")
    total = 0
    for t in want:
        if t not in TABLES:
            print(f"  [跳过] 未知表 {t}")
            continue
        if args.truncate:
            cur.execute(f"DELETE FROM `{t}`")
            conn.commit()
        total += load_table(conn, t, TABLES[t], force_slow=args.slow)
    print(f"\n合计 {total:,} 行")
    verify(conn)
    conn.close()


def _split_sql(text: str):
    """按分号切 SQL（schema.sql 没有存储过程/触发器，够用）。"""
    buf = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        buf.append(line)
        if s.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                yield stmt
            buf = []
    if buf:
        yield "\n".join(buf).strip()


if __name__ == "__main__":
    sys.exit(main())
