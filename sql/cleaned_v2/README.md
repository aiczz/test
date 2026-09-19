# cleaned_v2 交付说明

本目录由 `../scripts/clean_v2.py` 从原始交付目录确定性生成。

- 先阅读 `CLEANING_REPORT.md`。
- `main_ingredient.csv` 使用明确、连续的新 ID。
- `ingredient_id_map.csv` 是所有旧 ID 的审计映射。
- `review_ingredients.csv` 必须人工复核后才能扩大主表。
- 导入前先执行 `schema.sql`，再配置环境变量运行 `load_to_mysql.py`。
