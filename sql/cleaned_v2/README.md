# cleaned_v2 交付说明

本目录由 `../scripts/clean_v2.py` 从原始交付目录和 `../seasonal_source` 确定性生成。

- 先阅读 `CLEANING_REPORT.md`。
- `main_ingredient.csv` 保留590条核心原生食材，用于推荐、营养和层级搜索。
- `ingredient_catalog.csv` 覆盖全部菜谱用料和季节数据补充食材；每条 `dish_ingredients` 都有非空 `catalog_ingredient_id`。
- `ingredient_catalog_aliases.csv` 保存菜谱原名称到规范目录名称的映射。
- `dish_ingredient_components.csv` 保存“葱姜蒜、青红椒”等复合用料的确定组成。
- `ingredient_id_map.csv` 是所有旧 ID 的审计映射。
- `review_ingredients.csv` 保留仍需人工确认的旧名称。
- `dropped_dishes.csv` 是菜谱删除审计清单，含类型、原因和命中证据。
- `dish_name_map.csv` 保存每道保留菜谱的原名、规范名及命中规则。
- `ingredient_hierarchy.csv` 保存通用食材与具体部位/品种关系。
- `target_groups.csv` 只保存人群字典；`ingredient_groups.csv.is_suitable` 保存每种食材对该人群是否适宜，并附证据来源和原句。
- `ingredient_group_extraction_audit.csv` 保存 `tcm_not_user` 的结构化结果以及仍需人工复核的文本。
- `dish_ingredient_search.csv` 已展开父级搜索，例如鸡肉可查到鸡腿、鸡胸肉和鸡翅菜谱。
- `seasonal_calendar.csv` 保存季节、月份、二十四节气和传统节日。
- `seasonal_food.csv` 将时令名称连接到核心/完整食材目录，或保留为节令菜名关键词。
- `seasonal_dish_links.csv` 保存节令菜名关键词与精选菜谱的标题关系。
- `seasonal_knowledge.csv` 保存具体食物知识和汇总知识，并连接日历与时令食物。
- MySQL 运行结构已由 23 张表合并为 6 张表；`db_*.csv` 是实际导入文件，其余 CSV 是可追溯的审计底稿。
- 导入前先备份旧库，再执行 `schema.sql`：它会删除旧 23 表并重建 6 张精简表；随后配置环境变量运行 `load_to_mysql.py`。
- `load_to_mysql.py` 只导入 6 张业务表；可用 `--verify` 检查表数量和孤儿关系。
