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
 ("ingredients","db_ingredients.csv",["id","name","ingredient_type","core_ingredient_id","category","subcategory","is_core_raw","is_edible","review_status","usage_count","reason","edible","water","energy_kcal","energy_kj","protein","fat","cho","dietary_fiber","cholesterol","ash","vitamin_a","carotene","retinol","thiamin","riboflavin","niacin","vitamin_c","vitamin_e","ca","p","k","na","mg","fe","zn","se","cu","mn","nutrition_source","nutrition_match","quality","category_source","tcm_user","tcm_not_user","effects_json","suitable_groups_json","unsuitable_groups_json","aliases_json","parent_core_ids_json","child_core_ids_json"]),
 ("dishes","db_dishes.csv",["id","dish_name","dish_name_original","description","cuisine","ingredient_text","instruction_text","ingredient_count","main_ingredient_count","search_ingredient_count","total_weight_g","energy_kcal","protein_g","fat_g","cho_g","dietary_fiber_g","ca_mg","fe_mg","na_mg","matched_ratio","weight_confidence","explicit_count","estimated_count","vague_count","suspect","nutrition_version","tags_json","search_ingredient_ids_json"]),
 ("dish_ingredients","db_dish_ingredients.csv",["id","dish_id","ingredient_id","core_ingredient_id","raw_name","raw_text","quantity","role","grams","grams_source","component_core_ids_json"]),
 ("seasonal_calendar","db_seasonal_calendar.csv",["id","level","name","gregorian_time","lunar_time","season","sort_order","description","knowledge_json"]),
 ("seasonal_food","db_seasonal_food.csv",["id","calendar_id","level","time_name","season","category","name","note","recommendation_reason","source","entity_type","ingredient_id","core_ingredient_id","match_status","knowledge_json"]),
 ("seasonal_dish_links","seasonal_dish_links.csv",["seasonal_food_id","dish_id","match_type"]),
]
DB_COL = {}
ORDER_DELETE = [x[0] for x in reversed(TABLES)]

NULL_LIKE_VALUES = {"", "—", "-", "NULL", "null", "Tr", "tr", "TR", "un", "UN"}

def value(v):
    if v is None:
        return None
    v = v.strip()
    return None if v in NULL_LIKE_VALUES else v
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
                cur.execute("SELECT COUNT(*) FROM dish_ingredients d LEFT JOIN ingredients i ON i.id=d.ingredient_id WHERE i.id IS NULL"); print("orphan_ingredient",cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM dish_ingredients d LEFT JOIN ingredients i ON i.id=d.core_ingredient_id WHERE d.core_ingredient_id IS NOT NULL AND i.id IS NULL"); print("orphan_core",cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM seasonal_food f LEFT JOIN seasonal_calendar c ON c.id=f.calendar_id WHERE c.id IS NULL"); print("orphan_seasonal_calendar",cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM seasonal_dish_links l LEFT JOIN seasonal_food f ON f.id=l.seasonal_food_id LEFT JOIN dishes d ON d.id=l.dish_id WHERE f.id IS NULL OR d.id IS NULL"); print("orphan_seasonal_dish",cur.fetchone()[0])
                return
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
