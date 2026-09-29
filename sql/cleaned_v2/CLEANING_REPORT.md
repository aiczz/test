# 菜谱数据库 V2 清洗报告

## 1. 处理范围与原则

- 数据源：`菜谱数据库_交付_20260918 (1)`，只读取、不修改。
- 规范依据：`菜谱数据库_V2_数据清洗与关联重构指南_Codex.md`。
- 目标：把食材主表收敛为基础原生食材；调味料、加工食品、成品、工具、操作语句和无法确认的碎片不进入主表。
- 映射策略：只使用明确别名、明确数量/形态剥离；不使用模糊包含匹配，不对 REVIEW 强行归并。
- 菜谱删减：删除高信号甜点/零食/油炸快餐、含糖饮品和相对低频异国菜；健康/低脂等明确标识优先保护。
- 营养阈值：仅在匹配率≥50%、重量置信度≥60%、总重量≥100g 时使用；能量≥400kcal/100g 且脂肪≥20g/100g 才作为补充删除证据。
- 精选规则：通过上述规则后，按家常/中式/清淡标签、步骤与用料完整度、营养完整度及同名频次排序；规范同名通常最多保留 2 版，并优先覆盖所有仍有候选菜谱的核心食材。
- 菜品营养：完整保留旧值并标记 `nutrition_version=legacy`；没有用不完整核心食材重新估算。
- 菜名规范：删除括号补充、营销/场景定语、分类前缀和宣传后句；原名与命中规则保存在 `dish_name_map.csv`。
- 运行库瘦身：原 23 张导入表合并为 6 张业务表；明细 CSV 仅作审计底稿，不参与 MySQL 导入。

## 2. 总量

| 指标 | 数量 |
|---|---:|
| 旧食材总数 | 16,693 |
| 新基础食材总数 | 590 |
| KEEP | 588 |
| MERGE | 383 |
| DROP | 9,346 |
| SPLIT | 33 |
| REVIEW | 6,343 |
| 删除调味料 | 399 |
| 删除加工食品 | 4,008 |
| 删除非食材/碎片 | 4,939 |
| 旧 ID 成功映射到新 ID | 971 |
| 完整食材目录 | 8,087 |
| 食材目录别名 | 8,809 |
| 复合用料组成关系 | 976 |
| 季节日历节点 | 52 |
| 时令食物记录 | 544 |
| 季节知识记录 | 636 |
| 时令菜品标题关系 | 101 |

## 3. 规则修复

| 修复类型 | 数量 |
|---|---:|
| 数量/单位残留归并 | 98 |
| 切片/块/丁/丝/末形态归并 | 38 |
| 明确别名归并 | 61 |
| 高频 KEEP/MERGE 审计条目（usage_count≥20） | 349 |
| 3~19 次确定性抽样条目 | 63 |

高频结果在 `high_frequency_audit.csv`；中频抽样在 `mid_frequency_sample_audit.csv`。REVIEW/SPLIT 连同原文样本和菜品 ID 见 `review_ingredients.csv`。

## 4. 菜谱关联

| 指标 | 数量 |
|---|---:|
| 原菜谱总数 | 200,000 |
| 保留菜谱 | 10,000 |
| 菜名实际规范化 | 2,738 |
| 删除菜谱合计 | 190,000 |
| 删除零有效食材菜谱 | 34,750 |
| 删除高糖/高脂/油炸高信号菜谱 | 16,189 |
| 删除含糖或高能量饮品 | 326 |
| 删除可靠营养高能量高脂菜谱 | 135 |
| 删除国内相对低频异国/西式菜谱 | 2,876 |
| 健康/地域规则通过后的候选菜谱 | 145,724 |
| 精选库优先级删减 | 135,724 |
| 原 dish_ingredients | 1,372,579 |
| 新 dish_ingredients | 77,886 |
| main | 30,550 |
| seasoning | 32,179 |
| processed | 5,323 |
| composite | 986 |
| other_food | 8,278 |
| generic | 531 |
| non_food | 39 |
| 菜谱核心关联覆盖率（main/保留用料） | 39.22% |
| 菜谱搜索关联 | 33,303 |
| 食材父子关系 | 58 |
| 原 dish_tags / 新 dish_tags | 215,795 / 30,864 |

保留菜谱的 `raw_name`、`raw_text`、`quantity` 均保留；SPLIT 因无法可靠分摊克数，`grams` 置空并标记 `split_unknown`。原 `ingredient_count` 不变，新增 `main_ingredient_count` 与 `search_ingredient_count`。删除类型、原因和证据见 `dropped_dishes.csv`。

每条 `dish_ingredients` 均有非空 `catalog_ingredient_id`。目录类型分布：{'core_raw': 590, 'other_food': 4341, 'processed': 902, 'seasoning': 1696, 'composite': 431, 'non_food': 29, 'generic': 73, 'seasonal_food': 25}。`ingredient_id` 继续指向590条核心原生食材，保持现有推荐与搜索兼容；调味料、加工食材、复合名称和待复核项通过完整目录闭环。

反向菜谱关联回归：番茄=649, 鸡蛋=1,390, 猪肉=634, 土豆=759, 苹果=17。

“鸡肉”搜索展开回归：鸡腿/鸡胸肉/鸡翅菜谱共 553 道，全部可由鸡肉检索到。

菜名示例：`超美味的西红柿蛋汤 → 西红柿蛋汤`、`下饭菜-豆角肉丁 → 豆角肉丁`。所有修改均可在 `dish_name_map.csv` 按菜谱 ID 复核。

## 5. 季节数据整合

- `seasonal_calendar.csv` 统一承载 4 季、12 月、24 节气和 12 个传统节日，共 52 个节点。
- `seasonal_food.csv` 共 544 条，匹配状态：{'seasonal_catalog': 50, 'core_exact': 422, 'catalog_exact': 52, 'unmatched_dish_keyword': 11, 'dish_title_keyword': 9}。
- 水果/蔬菜/普通食材如果不在原完整目录中，以 `seasonal_food` 类型补入完整目录，不进入590条核心营养食材表，也不伪造营养值。
- 来源中“菜品”优先匹配已有食材；无法作为食材的名称按菜名关键词关联，共形成 101 条精选菜谱关系。
- `seasonal_knowledge.csv` 共 636 条，其中 544 条连接具体时令食物，其余为汇总知识。

## 6. 其他关联与覆盖率

| 指标 | 原数量 | 新数量 |
|---|---:|---:|
| ingredient_effects | 891 | 566 |
| ingredient_groups | 5,001 | 2,086 |

- 营养数据覆盖率：482/590 = 81.69%
- 功效数据覆盖率：124/590 = 21.02%
- 人群关系：适宜 1,807 条，不适宜 279 条；禁忌原文解析状态 {'structured': 86, 'no_restriction_statement': 31}。
- 六个代表营养映射：猪肉=通过, 牛肉=通过, 鸡蛋=通过, 番茄=通过, 苹果=通过, 香蕉=通过

## 7. 完整性与回归测试

- 新食材 ID 连续：通过（1..590）。
- 食材名称唯一：通过。
- dish_ingredients 食材外键孤儿：0。
- dish_ingredients 菜品外键孤儿：0。
- dish_ingredients 完整目录空值/孤儿：0/0。
- 完整目录别名孤儿：0；复合用料组成关系孤儿：0。
- ingredient_effects 外键孤儿：0。
- ingredient_groups 外键孤儿：0；`is_suitable` 与证据字段错误：0。
- ingredient_hierarchy 外键/自环错误：0。
- dish_ingredient_search 外键孤儿：0，重复键：0。
- 季节日历、时令食物、季节知识和菜谱关系：数量与源表一致，外键零孤儿，重复键为0。
- 删除菜谱在 dish_ingredients、dish_tags、dish_nutrition、dish_ingredient_search 中残留：0。
- 指南“必须存在”清单：全部通过。
- 指南“必须不存在”清单：全部通过。
- 全部 16,693 个旧名称均分配 KEEP/MERGE/DROP/SPLIT/REVIEW 动作。

## 8. 审计边界

- `REVIEW` 不进入主表，等待人工确认；不能确定的 `SPLIT` 只保留菜谱原文，不伪造克数。
- MERGE 不合并或平均营养值；canonical 行只使用自身权威营养来源。新增“鸡腿、虾”规范名不继承模糊物种营养。
- `dish_nutrition` 是历史估算，只能按 legacy 使用；未来如需 V2 营养，应基于完整原料体系另行重算。
- MySQL 只导入 `ingredients`、`dishes`、`dish_ingredients`、`seasonal_calendar`、`seasonal_food`、`seasonal_dish_links` 6 张表；运行 CSV 数量为 {'ingredients': 8087, 'dishes': 10000, 'dish_ingredients': 77886, 'seasonal_calendar': 52, 'seasonal_food': 544, 'seasonal_dish_links': 101}。
