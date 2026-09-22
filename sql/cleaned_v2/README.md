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
- `ingredient_hierarchy.csv` 保存通用食材与具体部位/品种关系。
- `dish_ingredient_search.csv` 已展开父级搜索，例如鸡肉可查到鸡腿、鸡胸肉和鸡翅菜谱。
- `seasonal_calendar.csv` 保存季节、月份、二十四节气和传统节日。
- `seasonal_food.csv` 将时令名称连接到核心/完整食材目录，或保留为节令菜名关键词。
- `seasonal_dish_links.csv` 保存节令菜名关键词与精选菜谱的标题关系。
- `seasonal_knowledge.csv` 保存具体食物知识和汇总知识，并连接日历与时令食物。
- 导入前先执行 `schema.sql`，再配置环境变量运行 `load_to_mysql.py`。
