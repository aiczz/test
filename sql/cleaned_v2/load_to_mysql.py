"""把 cleaned_v2 CSV 安全导入 MySQL；所有主键均使用 CSV 的明确 ID。"""
from __future__ import annotations
import argparse, csv, os
from pathlib import Path
import pymysql

HERE = Path(__file__).resolve().parent
DB = dict(host=os.getenv("MYSQL_HOST", "localhost"), port=int(os.getenv("MYSQL_PORT", "3306")),
          user=os.getenv("MYSQL_USER", "root"), password=os.getenv("MYSQL_PASSWORD", ""),
          database=os.getenv("MYSQL_DB", "recipe_db"), charset="utf8mb4", autocommit=False)

TABLES = [
 ("ingredient_categories","ingredient_categories.csv",["id","name","sort_order"]),
 ("ingredient_subcategories","ingredient_subcategories.csv",["id","category_id","name","sort_order"]),
 ("ingredients","main_ingredient.csv",["id","name","category_id","subcategory_id","usage_count","is_core_raw","可食部%","水分g","能量kcal","能量kJ","蛋白质g","脂肪g","碳水化合物g","膳食纤维g","胆固醇mg","灰分g","维生素A(ugRE)","胡萝卜素(ug)","视黄醇(ug)","硫胺素mg","核黄素mg","烟酸mg","维生素Cmg","维生素E总mg","钙mg","磷mg","钾mg","钠mg","镁mg","铁mg","锌mg","硒(ug)","铜mg","锰mg","nutrition_source_name","nutrition_match","quality","category_source","tcm_user","tcm_not_user"]),
 ("tcm_effects","tcm_effects.csv",["id","name"]),
 ("target_groups","target_groups.csv",["id","name","is_suitable"]),
 ("ingredient_effects","ingredient_effects.csv",["ingredient_id","effect_id"]),
 ("ingredient_groups","ingredient_groups.csv",["ingredient_id","group_id"]),
 ("dishes","dishes.csv",["id","dish_name","description","cuisine","ingredient_text","instruction_text","ingredient_count","main_ingredient_count","total_weight_g"]),
 ("dish_ingredients","dish_ingredients.csv",["id","dish_id","ingredient_id","raw_name","raw_text","quantity","role","grams","grams_source"]),
 ("tags","tags.csv",["id","name","kind"]), ("dish_tags","dish_tags.csv",["dish_id","tag_id"]),
 ("dish_nutrition","dish_nutrition.csv",["dish_id","total_weight_g","energy_kcal","protein_g","fat_g","cho_g","dietary_fiber_g","ca_mg","fe_mg","na_mg","matched_ratio","weight_confidence","explicit_count","estimated_count","vague_count","suspect","nutrition_version"]),
 ("seasonings","excluded_seasonings.csv",["id","name","usage_count","reason"]),
 ("excluded_names","excluded_junk.csv",["id","name","usage_count","reason"]),
]
DB_COL = {"ingredients": ["id","name","category_id","subcategory_id","usage_count","is_core_raw","edible","water","energy_kcal","energy_kj","protein","fat","cho","dietary_fiber","cholesterol","ash","vitamin_a","carotene","retinol","thiamin","riboflavin","niacin","vitamin_c","vitamin_e","ca","p","k","na","mg","fe","zn","se","cu","mn","nutrition_source","nutrition_match","quality","category_source","tcm_user","tcm_not_user"]}
ORDER_DELETE = [x[0] for x in reversed(TABLES)]

def value(v): return None if v is None or v.strip() in {"", "—", "-", "NULL", "null"} else v
def batches(reader, size=2000):
    batch=[]
    for row in reader:
        batch.append(row)
        if len(batch)>=size: yield batch; batch=[]
    if batch: yield batch

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--verify",action="store_true"); args=ap.parse_args()
    con=pymysql.connect(**DB)
    try:
        with con.cursor() as cur:
            if args.verify:
                for table,_,_ in TABLES: cur.execute(f"SELECT COUNT(*) FROM `{table}`"); print(table,cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM dish_ingredients d LEFT JOIN dishes x ON x.id=d.dish_id WHERE x.id IS NULL"); print("orphan_dish",cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM dish_ingredients d LEFT JOIN ingredients i ON i.id=d.ingredient_id WHERE d.ingredient_id IS NOT NULL AND i.id IS NULL"); print("orphan_ingredient",cur.fetchone()[0]); return
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for table in ORDER_DELETE: cur.execute(f"DELETE FROM `{table}`")
            for table,filename,csv_cols in TABLES:
                db_cols=DB_COL.get(table,csv_cols); marks=",".join(["%s"]*len(db_cols)); cols=",".join(f"`{c}`" for c in db_cols)
                sql=f"INSERT INTO `{table}` ({cols}) VALUES ({marks})"
                with (HERE/filename).open(encoding="utf-8-sig",newline="") as fh:
                    rd=csv.DictReader(fh)
                    for batch in batches(rd): cur.executemany(sql,[[value(r.get(c,"")) for c in csv_cols] for r in batch])
                print(f"loaded {table}")
            cur.execute("SET FOREIGN_KEY_CHECKS=1"); con.commit()
    except Exception: con.rollback(); raise
    finally: con.close()
if __name__=="__main__": main()
