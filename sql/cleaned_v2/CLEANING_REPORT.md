# 菜谱数据库 V2 清洗报告

## 1. 处理范围与原则

- 数据源：`菜谱数据库_交付_20260918 (1)`，只读取、不修改。
- 规范依据：`菜谱数据库_V2_数据清洗与关联重构指南_Codex.md`。
- 目标：把食材主表收敛为基础原生食材；调味料、加工食品、成品、工具、操作语句和无法确认的碎片不进入主表。
- 映射策略：只使用明确别名、明确数量/形态剥离；不使用模糊包含匹配，不对 REVIEW 强行归并。
- 菜品营养：完整保留旧值并标记 `nutrition_version=legacy`；没有用不完整核心食材重新估算。

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
| 保留菜谱 | 164,490 |
| 删除零有效食材菜谱 | 35,510 |
| 原 dish_ingredients | 1,372,579 |
| 新 dish_ingredients | 1,214,633 |
| main | 401,032 |
| seasoning | 13,157 |
| other | 800,444 |
| 菜谱核心关联覆盖率（main/保留用料） | 33.02% |
| 菜谱搜索关联 | 434,486 |
| 食材父子关系 | 58 |
| 原 dish_tags / 新 dish_tags | 215,795 / 179,500 |

保留菜谱的 `raw_name`、`raw_text`、`quantity` 均保留；SPLIT 因无法可靠分摊克数，`grams` 置空并标记 `split_unknown`。原 `ingredient_count` 不变，新增 `main_ingredient_count` 与 `search_ingredient_count`。删除清单见 `dropped_dishes.csv`。

反向菜谱关联回归：番茄=8,219, 鸡蛋=41,710, 猪肉=6,500, 土豆=9,589, 苹果=1,573。

“鸡肉”搜索展开回归：鸡腿/鸡胸肉/鸡翅菜谱共 7,597 道，全部可由鸡肉检索到。

## 5. 其他关联与覆盖率

| 指标 | 原数量 | 新数量 |
|---|---:|---:|
| ingredient_effects | 891 | 566 |
| ingredient_groups | 5,001 | 1,813 |

- 营养数据覆盖率：482/590 = 81.69%
- 功效数据覆盖率：124/590 = 21.02%
- 六个代表营养映射：猪肉=通过, 牛肉=通过, 鸡蛋=通过, 番茄=通过, 苹果=通过, 香蕉=通过

## 6. 完整性与回归测试

- 新食材 ID 连续：通过（1..590）。
- 食材名称唯一：通过。
- dish_ingredients 食材外键孤儿：0。
- dish_ingredients 菜品外键孤儿：0。
- ingredient_effects 外键孤儿：0。
- ingredient_groups 外键孤儿：0。
- ingredient_hierarchy 外键/自环错误：0。
- dish_ingredient_search 外键孤儿：0，重复键：0。
- 删除菜谱在 dish_ingredients、dish_tags、dish_nutrition、dish_ingredient_search 中残留：0。
- 指南“必须存在”清单：全部通过。
- 指南“必须不存在”清单：全部通过。
- 全部 16,693 个旧名称均分配 KEEP/MERGE/DROP/SPLIT/REVIEW 动作。

## 7. 审计边界

- `REVIEW` 不进入主表，等待人工确认；不能确定的 `SPLIT` 只保留菜谱原文，不伪造克数。
- MERGE 不合并或平均营养值；canonical 行只使用自身权威营养来源。新增“鸡腿、虾”规范名不继承模糊物种营养。
- `dish_nutrition` 是历史估算，只能按 legacy 使用；未来如需 V2 营养，应基于完整原料体系另行重算。
