# 菜谱数据库 V2 数据清洗与关联重构指南（给 Codex）

## 1. 本次任务目标

当前数据库需要进行一次“以基础原始食材为核心”的重新清洗。

本轮不要追求食材数量多，而要追求：

> 食材名称规范、粒度统一、真正适合作为用户选择和推荐的基础食材，并保证营养、功效、人群、菜谱等所有关联同步正确。

`main_ingredient.csv` 当前有 16,693 条，本轮不要求保留这个规模。

应用主要面向“今天适合吃什么、这个季节适合什么食材、某种基础食材能做什么菜”等功能，因此核心食材应该主要是：

| 类型 | 例子 | 处理 |
|---|---|---|
| 新鲜蔬菜 | 番茄、黄瓜、菠菜、胡萝卜、西兰花、洋葱 | 保留 |
| 新鲜水果 | 苹果、香蕉、草莓、橙子、葡萄、芒果 | 保留 |
| 原始畜肉 | 猪肉、牛肉、羊肉、猪里脊、排骨、牛腩 | 保留 |
| 原始禽肉 | 鸡肉、鸡腿、鸡翅、鸭肉 | 保留 |
| 蛋类 | 鸡蛋、鸭蛋、鹅蛋、鹌鹑蛋 | 保留 |
| 水产 | 鲈鱼、草鱼、金枪鱼、虾、扇贝、螃蟹 | 保留 |
| 菌菇 | 香菇、金针菇、平菇、木耳、银耳 | 保留 |
| 薯芋 | 土豆、红薯、山药、芋头 | 保留 |
| 新鲜豆类 | 毛豆、豌豆、四季豆等 | 可保留 |
| 天然谷物/豆类/坚果 | 大米、玉米、黄豆、绿豆、花生、核桃 | 可作为扩展基础食材保留 |

本轮的核心原则是：

**用户在首页看到的是“食物本身”，而不是菜谱作者写下来的各种用料描述。**

---

## 2. 当前数据中已经确认的问题

不要相信现有文档中“main_ingredient 的名字已经全部清洗干净”的结论，需要重新以 CSV 实际内容为准。

目前已经实际发现以下问题。

| 当前名称 | 问题 | 应如何处理 |
|---|---|---|
| `克肉` | 数量单位残留 | 删除，不能猜是哪种肉 |
| `克花生` | 数量残留 | 合并到 `花生` |
| `一个洋葱` | 数量残留 | 合并到 `洋葱` |
| `几个土豆` | 数量描述 | 合并到 `土豆` |
| `香蕉一根` | 数量描述 | 合并到 `香蕉` |
| `半根胡萝卜` | 数量描述 | 合并到 `胡萝卜` |
| `豆腐一块` | 数量描述 + 加工食材 | 本轮核心食材删除 |
| `猪肉薄片` | 形态描述 | 合并到 `猪肉` |
| `胡萝卜切丁` | 加工形态 | 合并到 `胡萝卜` |
| `全蛋液` | 加工状态 | 不作为核心食材 |
| `刷表面蛋液` | 操作说明 | 删除核心关联 |
| `葱花香菜` | 两种食材混在一起 | 不允许作为一个食材 |
| `蛋液和芝麻` | 多食材组合 | 不允许作为一个食材 |
| `照片` | 非食材 | 删除 |
| `塑料袋` | 工具 | 删除 |
| `保温杯` | 工具 | 删除 |
| `火腿` | 加工肉制品 | 本轮核心食材删除 |
| `培根` | 加工肉制品 | 删除 |
| `香肠` | 加工肉制品 | 删除 |
| `面包` | 加工成品 | 删除 |
| `蛋糕` | 成品 | 删除 |
| `巧克力` | 加工配料 | 删除 |
| `芝士` | 加工乳制品 | 默认删除 |
| `番茄酱` | 调味/加工品 | 删除 |
| `生抽/老抽/蚝油` | 调味料 | 删除 |
| `盐/糖/油` | 调味料 | 删除 |

当前分类本身也不能直接作为最终判断条件。

例如：

- `火腿`、`培根`、`香肠` 都可能被正确分类到“畜肉类”，但它们不是本项目想保留的基础原始食材。
- `泡菜`、`酸菜` 可能被分类到蔬菜，但属于加工食品。
- “蔬菜类及其制品”中的“制品”本轮应该大量排除。

因此：

> 禁止使用 `category_major` 一列直接决定 KEEP/DROP。

---

## 3. 绝对不能直接修改原始文件

原始压缩包必须保持不动。

新建：

```text
cleaned_v2/
```

所有结果输出到这里。

至少生成：

```text
cleaned_v2/
├── main_ingredient.csv
├── ingredient_id_map.csv
├── dropped_ingredients.csv
├── review_ingredients.csv
├── dish_ingredients.csv
├── ingredient_effects.csv
├── ingredient_groups.csv
├── dishes.csv
├── dish_nutrition.csv
├── ingredient_categories.csv
├── ingredient_subcategories.csv
├── excluded_seasonings.csv
├── excluded_junk.csv
├── schema.sql
├── load_to_mysql.py
└── CLEANING_REPORT.md
```

---

## 4. 最关键的原则：先建立 OLD ID → NEW ID 映射

当前 `main_ingredient.csv` 自身没有显式 `id`。

现有数据库实际上采用：

```text
CSV 第 1 行 -> ingredient_id = 1
CSV 第 2 行 -> ingredient_id = 2
CSV 第 3 行 -> ingredient_id = 3
...
```

而：

```text
dish_ingredients.ingredient_id
ingredient_effects.ingredient_id
ingredient_groups.ingredient_id
```

全部引用这些 ID。

因此：

> 绝对禁止直接从 main_ingredient.csv 删除若干行后继续使用旧关联文件。

否则删除一条以后，后面所有 ID 都会错位。

必须首先生成：

```csv
old_id,old_name,action,new_id,new_name,reason
```

例如：

```csv
3002,一个洋葱,MERGE,6,洋葱,数量描述残留
3550,几个土豆,MERGE,16,土豆,数量描述残留
4260,香蕉一根,MERGE,108,香蕉,单位残留
1958,克肉,DROP,,,食材种类无法确定
19,火腿,DROP,,,加工肉制品
30,培根,DROP,,,加工肉制品
```

注意：

`new_id` 最后应该基于清洗后的表重新连续编号。

建议同时修改 `main_ingredient.csv`：

增加明确的：

```text
id
```

字段。

以后不要再依赖 CSV 行号产生食材 ID。

同时修改 `load_to_mysql.py`，让 ingredients 和其他字典表一样显式导入 ID。

---

## 5. 每一个旧食材必须属于 5 种动作之一

本轮建立：

```text
KEEP
MERGE
DROP
SPLIT
REVIEW
```

### KEEP

名称本身已经是符合要求的基础食材。

例如：

```text
番茄
黄瓜
胡萝卜
菠菜
洋葱
苹果
香蕉
猪肉
牛肉
鸡肉
排骨
鸡腿
鸡蛋
草鱼
虾
香菇
金针菇
土豆
山药
```

### MERGE

本质上是同一种基础食材，只是带有：

数量、形态、切法、大小、说明、方言别名等。

例如：

```text
一个洋葱 -> 洋葱
洋葱一个 -> 洋葱
香蕉一根 -> 香蕉
半根胡萝卜 -> 胡萝卜
胡萝卜半个 -> 胡萝卜
胡萝卜切丁 -> 胡萝卜
猪肉薄片 -> 猪肉
```

MERGE 的前提必须是：

> 能 100% 判断属于哪一个食材。

不能猜。

### DROP

以下内容不能进入核心食材表：

```text
调味料
加工食品
成品菜
半成品
烘焙配料
饮料酒水
厨房工具
包装用品
操作说明
单位残留
无法确定含义的碎片
```

### SPLIT

例如：

```text
葱花香菜
胡萝卜土豆
青椒胡萝卜
蛋液和芝麻
```

这种情况不允许把整串作为一个 ingredient。

但 SPLIT 只能在确定确实包含多个独立食材时使用。

不要在 `main_ingredient` 中留下：

```text
胡萝卜土豆
葱花香菜
```

这种“两个食材合成一个食材”的记录。

### REVIEW

任何无法确定的情况不得自动猜。

例如：

```text
克肉
肉片
肉馅
鲜肉
鱼块
蔬菜
水果
```

“肉片”可能是猪肉、牛肉或羊肉。

除非 `raw_text` 或菜谱原始文本能够明确恢复来源，否则应进入：

```text
review_ingredients.csv
```

而不是随便映射。

---

## 6. 名称清洗规则

名称清洗不要再依赖旧的“从尾部找 2/3/4 字中心词”的方式作为主要逻辑。

这正是之前产生截断和错误归一的高风险来源。

正确流程应为：

```text
原始名称
↓
Unicode NFKC 归一
↓
去首尾空格/标点
↓
识别数量描述
↓
识别单位
↓
识别加工/切法描述
↓
别名归一
↓
基础食材词典匹配
↓
KEEP / MERGE / DROP / SPLIT / REVIEW
```

---

## 7. 数量和单位残留清洗

重点处理：

```text
一个
两个
几个
一根
半根
一片
几片
一块
半个
适量
少量
若干
克
多少克
```

例子：

```text
一个洋葱 -> 洋葱
洋葱一个 -> 洋葱
香蕉一根 -> 香蕉
胡萝卜半个 -> 胡萝卜
几个土豆 -> 土豆
```

但不要简单把所有数字开头都删除。

之前的清洗曾出现：

```text
三文鱼 -> 文鱼
五花肉 -> 花肉
百香果 -> 香果
```

因此数量剥离必须要求：

> 数字/数量词 + 明确量词结构存在。

例如：

```text
一根香蕉
两个苹果
半个洋葱
三片姜
```

才允许剥离。

不能看到：

```text
三
五
百
```

就删除。

---

## 8. 切法和形态描述

以下只代表食材形态，不应该创建新 ingredient：

```text
切片
片
薄片
切丝
丝
切丁
丁
切块
块
末
碎
段
条
去皮
去籽
去蒂
```

例如：

```text
胡萝卜切丁 -> 胡萝卜
胡萝卜丝 -> 胡萝卜
黄瓜片 -> 黄瓜
猪肉薄片 -> 猪肉
```

但是不要破坏真实品种或部位。

例如以下可以继续独立存在：

```text
猪里脊
五花肉
排骨
猪蹄
牛腩
牛排
鸡翅
鸡腿
鸡胸肉
```

这些是用户实际购买时会区分的商品，而不是单纯切法。

---

## 9. 加工食品必须从核心食材表退出

重点建立加工食品黑名单规则。

肉类加工品：

```text
火腿
火腿肠
香肠
培根
午餐肉
腊肉
腊肠
肉松
肉干
熏肉
```

水产加工品：

```text
鱼丸
虾丸
蟹棒
鱼豆腐
鱼饼
罐头鱼
```

豆制品：

在本轮“只保留最基础食材”的严格模式下：

```text
豆腐
豆干
腐竹
豆皮
素鸡
```

不要进入核心原始食材表。

其原料：

```text
黄豆
黑豆
绿豆
红豆
```

可以保留。

烘焙和成品：

```text
面包
吐司
饼干
蛋糕
曲奇
巧克力
奶油
黄油
芝士
炼乳
奶粉
面包糠
泡打粉
酵母
```

默认全部退出核心食材。

---

## 10. 调味料和“配料”全部退出核心食材

例如：

```text
盐
白糖
冰糖
生抽
老抽
酱油
蚝油
醋
料酒
豆瓣酱
番茄酱
沙拉酱
味精
鸡精
花椒
八角
桂皮
香叶
食用油
橄榄油
芝麻油
```

这些不应该出现在用户“基础食材推荐”列表。

但需要特别注意：

```text
葱
姜
蒜
香菜
新鲜辣椒
```

虽然经常被用于调味，但它们本身也是新鲜植物食材。

本轮建议继续作为基础食材保留。

---

## 11. 菜谱原始文字不要删除

这一点非常重要。

虽然我们把调味料、加工食品从：

```text
main_ingredient
```

中删除，但不要破坏菜谱原始内容。

`dishes` 中：

```text
ingredient_text
instruction_text
```

必须保留原文。

例如：

```text
150g肥牛，1个西红柿，1把金针菇，5克糖，6克盐，1勺蚝油...
```

即使糖、盐、蚝油不属于核心食材，也不要从：

```text
dishes.ingredient_text
```

删除。

因为它属于菜谱内容。

需要区分两个概念：

```text
菜谱完整用料
```

和：

```text
App 核心食材库
```

不能为了清理食材库而破坏菜谱。

---

## 12. dish_ingredients.csv 必须重新构建关联

当前：

```text
dish_ingredients.csv
```

共有约 137 万行。

并且实际检查发现：

```text
role
```

这一列现在全部为空。

因此不能继续沿用。

重新生成 `role`：

```text
main       = 保留下来的基础食材
seasoning  = 调味料
other      = 加工品、工具、说明、未知内容
```

例如：

```text
番茄       role=main
鸡蛋       role=main
猪肉       role=main

盐         role=seasoning
生抽       role=seasoning
蚝油       role=seasoning

面包       role=other
培根       role=other
照片       role=other
```

### ingredient_id 处理

如果属于 KEEP：

```text
旧 ID -> 新 ID
```

如果属于 MERGE：

```text
旧 ID -> 对应 canonical ingredient 的新 ID
```

例如：

```text
香蕉一根 -> 香蕉 ID
```

如果属于 DROP：

```text
ingredient_id = NULL
```

不要删除 `raw_name` 和 `raw_text`。

这样既保留菜谱原始信息，又不会把无关配料当作基础食材。

推荐结果：

```text
raw_name      ingredient_id     role
番茄           18                main
一个洋葱       6                 main
香蕉一根       108               main
生抽           NULL              seasoning
盐             NULL              seasoning
培根           NULL              other
```

---

## 13. 不要随便修改 raw_name / raw_text

`dish_ingredients` 的：

```text
raw_name
raw_text
quantity
```

属于来源数据和审计数据。

例如：

```text
raw_name = 香蕉一根
ingredient_id = 香蕉的新 ID
```

是完全合理的。

不要为了干净，把：

```text
raw_name
```

全部替换成“香蕉”。

否则以后无法追踪：

“这个 canonical ingredient 是怎么从原文得到的？”

---

## 14. ingredient_effects.csv 必须重映射

目前：

```text
ingredient_effects.csv
```

使用旧 `ingredient_id`。

清洗以后必须通过：

```text
ingredient_id_map.csv
```

重建。

规则：

### KEEP

直接：

```text
old_id -> new_id
```

### MERGE

例如：

```text
小番茄 -> 圣女果
樱桃番茄 -> 圣女果
```

如果确认是同一种食物：

把旧 effect 迁移到新的 canonical ingredient。

然后：

```text
(new_ingredient_id, effect_id)
```

去重。

### DROP

直接删除对应关系。

例如：

```text
火腿
培根
面包
巧克力
```

被删出核心食材，则其：

```text
ingredient_effects
```

也不能继续存在。

### 重要限制

不要因为：

```text
肉片
鲜肉
鱼块
```

看起来像某类食品，就把功效迁移到：

```text
猪肉
鱼
```

只有确定是同一种食物才能迁移。

---

## 15. ingredient_groups.csv 同样处理

规则与 `ingredient_effects.csv` 一致。

MERGE 时：

```text
union + deduplicate
```

DROP 时删除。

所有结果必须保证：

```text
ingredient_groups.ingredient_id
```

均真实存在于新的：

```text
main_ingredient.id
```

---

## 16. main_ingredient 中营养数据的处理

不要对多个别名行的营养数据进行：

```text
求和
平均
随机取一个
```

例如：

```text
一个洋葱
洋葱
洋葱一个
```

最终都合并到：

```text
洋葱
```

营养数据只应该采用：

```text
canonical 洋葱
```

本身对应《中国食物成分表》的权威数据。

优先级：

```text
明确权威 nutrition_match
>
canonical 原始行
>
明确同义词的权威数据
>
NULL
```

宁可为空，也不要错误填充。

---

## 17. 营养关联的一个重要原则

以下看起来可以合并用于“搜索”，但营养上不能随便等价：

```text
蛋清 -> 鸡蛋
蛋黄 -> 鸡蛋
全蛋液 -> 鸡蛋
金枪鱼罐头 -> 金枪鱼
```

因此必须区分：

```text
同名/形态变化
```

和：

```text
营养成分已经发生明显变化
```

例如：

```text
胡萝卜切丁 -> 胡萝卜
```

营养基本可以视为同一食材。

但：

```text
蛋清 -> 鸡蛋
```

营养并不等价。

严格模式下：

```text
蛋清 / 蛋黄 / 全蛋液
```

不要迁移鸡蛋的 nutrition。

可以：

```text
ingredient_id = NULL
role = other
```

或者未来单独设计“加工/拆分食材”。

本轮不要为了提高匹配率制造假的营养数据。

---

## 18. dish_nutrition.csv 必须特别处理

清洗 `main_ingredient` 后，旧的：

```text
dish_nutrition.csv
```

不能直接默认继续准确。

因为它是根据旧：

```text
dish_ingredients
+
ingredient nutrition
+
grams
```

计算出来的。

而本轮大量食材会：

```text
MERGE
DROP
NULL
```

因此必须重新验证。

正确原则是：

> 不允许用“清洗后的基础食材表”强行计算一整道菜完整营养。

因为如果：

```text
糖
油
面粉
奶油
芝士
```

全部从核心食材表删除，而菜谱营养又只计算 core ingredient，那么热量会严重低估。

所以实现以下两种方案中的第一种。

### 推荐方案

核心业务食材库和菜谱营养计算来源分离。

核心食材库：

```text
main_ingredient
```

只保留本项目需要的基础食材。

而：

```text
dish_nutrition
```

如果继续使用，应该从原始完整营养映射或独立 nutrition reference 中重新计算。

不要依赖“展示给用户选择的核心食材表”必须包含所有营养来源。

### 如果暂时没有能力重新完整计算

则不要生成假的部分营养值。

可以暂时：

```text
保留旧 dish_nutrition
```

但必须标记：

```text
nutrition_version = legacy
```

或者暂时从应用数据交付中移除。

禁止重新计算一个只包含番茄、鸡蛋、肉，而漏掉油、糖、面粉的“整道菜营养”，然后仍然称为整道菜营养。

---

## 19. dishes.csv 的处理

以下字段：

```text
dish_name
description
cuisine
ingredient_text
instruction_text
```

原则上保持不变。

但：

```text
ingredient_count
```

需要明确口径。

推荐仍然表示：

```text
菜谱原始用料数量
```

而不是“核心食材数量”。

如果 App 需要核心食材数量，新加：

```text
main_ingredient_count
```

不要改变旧字段语义。

---

## 20. 分类体系建议同步精简

当前有：

```text
蔬菜类及其制品
水果类及其制品
畜肉类及其制品
...
其他
其他类
调味
```

本项目清理后推荐业务层使用更简单的分类：

| 分类 | 内容 |
|---|---|
| 蔬菜 | 新鲜蔬菜 |
| 水果 | 新鲜水果 |
| 畜肉 | 猪牛羊等 |
| 禽肉 | 鸡鸭鹅等 |
| 蛋类 | 鸡蛋鸭蛋等 |
| 水产 | 鱼虾蟹贝 |
| 菌菇藻类 | 香菇木耳海带等 |
| 薯芋 | 土豆山药红薯等 |
| 豆类 | 可选 |
| 谷物/坚果 | 可选 |

不要再建立：

```text
其他
其他类
```

作为大量食材的兜底分类。

一个东西如果已经无法确定是什么食材，通常就不应该进入本轮核心食材库。

---

## 21. 必须重点处理组合食材名

当前存在很多：

```text
胡萝卜土豆
葱花香菜
玉米青豆胡萝卜
胡萝卜青椒
蛋液芝麻
```

不要把它们当作单一 ingredient。

如果能够明确拆分：

```text
胡萝卜土豆
```

可以在分析阶段识别为：

```text
胡萝卜
土豆
```

但如果原始一行只有一个总重量：

```text
100g 胡萝卜土豆
```

无法知道每一种多少克。

这种情况下：

可以用于：

```text
菜谱搜索关联
```

但不得用于：

```text
营养重量计算
```

将其标记为：

```text
grams = NULL
grams_source = split_unknown
```

或者只保留在原始文本，不生成拆分营养关联。

---

## 22. 不能为了提高覆盖率而做模糊猜测

继续坚持原项目中一个正确原则：

> 食材匹配宁可漏，不可错。

以下规则禁止：

```text
字符串包含“肉” -> 猪肉
字符串包含“鱼” -> 某种鱼
字符串包含“蛋” -> 鸡蛋
```

例如：

```text
牛肉
羊肉
猪肉
```

都包含“肉”。

所以：

```text
克肉
肉片
肉馅
```

不能直接归一为猪肉。

进入 REVIEW 或保持 NULL。

---

## 23. 重新生成 excluded 文件

本轮重新生成：

```text
excluded_seasonings.csv
```

至少包含：

```text
name
usage_count
reason
```

reason 细分为：

```text
调味料
香辛料
烹饪油脂
酱料
```

重新生成：

```text
excluded_junk.csv
```

reason 建议细分：

```text
数量残留
无法识别碎片
操作说明
厨房工具
包装材料
成品食物
加工食品
混合食材
重复名称
```

不要像当前某些数据一样统一写成：

```text
非食材名（碎片/截断）
```

这样不利于审计。

---

## 24. 建立 dropped_ingredients.csv

本轮新增：

```text
dropped_ingredients.csv
```

字段：

```csv
old_id,name,usage_count,category_major,category_sub,drop_type,reason
```

例如：

```text
19,火腿,...,processed,加工肉制品
30,培根,...,processed,加工肉制品
1958,克肉,...,junk,单位残留且原食材无法确定
```

这样未来如果需要把某类食材加回来，可以追溯。

---

## 25. 建立 review_ingredients.csv

凡是程序不能 100% 确定的名字，不直接处理。

输出：

```text
old_id
name
usage_count
category_major
possible_candidates
sample_raw_text
sample_dish_ids
reason
```

例如：

```text
克肉
肉片
鲜肉
鱼块
蔬菜
水果
```

优先按：

```text
usage_count DESC
```

排序，方便人工先核查高频项。

---

## 26. 高频数据优先人工审计

在自动规则跑完以后，必须人工输出并检查：

```text
usage_count >= 20
```

的所有 KEEP / MERGE 结果。

然后抽查：

```text
usage_count 3~19
```

的数据。

因为：

> App 体验主要由高频食材决定，不需要为了几千个只出现三次的奇怪名称牺牲数据质量。

---

## 27. load_to_mysql.py 必须同步修改

当前 ingredients 使用：

```text
AUTO_INCREMENT
```

生成 ID。

本轮应修改为：

```text
main_ingredient.csv
```

包含明确：

```text
id
```

并在导入时插入：

```sql
INSERT INTO ingredients (id, ...)
```

不要再让：

```text
CSV 行顺序
```

决定外键。

以后即使 CSV 排序，也不会导致关联全部错位。

---

## 28. schema.sql 建议补充字段

建议给 ingredients 增加：

```text
is_core_raw
```

例如：

```sql
is_core_raw TINYINT(1) NOT NULL DEFAULT 1
```

不过如果本轮已经彻底只保留基础食材，也可以不加。

更推荐在清洗过程文件，而非正式业务表，维护：

```text
clean_action
old_id
canonical_name
```

这些属于审计信息。

---

## 29. 外键完整性验收

清洗完成后必须自动验证：

```text
dish_ingredients.ingredient_id
ingredient_effects.ingredient_id
ingredient_groups.ingredient_id
```

所有非 NULL 值都必须存在于：

```text
main_ingredient.id
```

必须满足：

```text
orphan dish_ingredients = 0
orphan ingredient_effects = 0
orphan ingredient_groups = 0
```

---

## 30. 名称完整性验收

最终 `main_ingredient.name` 不允许出现明显数量残留，例如：

```text
一个
两个
几个
一根
半根
一片
几片
多少
多少克
克XX
```

不允许出现：

```text
切丁
切丝
切片
切块
刷表面
用于装饰
备用
适量
少许
```

不允许存在厨房用品：

```text
塑料袋
保鲜袋
杯
碗
勺
保温杯
餐盒
模具
```

不允许出现整段说明语言。

---

## 31. 核心食材验收

至少准备一组必须存在的回归测试：

```text
葱
姜
蒜
洋葱
番茄
圣女果
黄瓜
胡萝卜
菠菜
白菜
西兰花
土豆
南瓜
苹果
香蕉
草莓
葡萄
橙子
猪肉
牛肉
羊肉
排骨
牛腩
鸡肉
鸡胸肉
鸡腿
鸡翅
鸡蛋
鸭蛋
草鱼
鲈鱼
虾
扇贝
香菇
金针菇
木耳
```

以上不能因为规则误判而删除。

---

## 32. 必须不存在的回归测试

核心 `main_ingredient` 至少检查以下内容不得存在：

```text
盐
白糖
生抽
老抽
蚝油
料酒
番茄酱
沙拉酱
火腿
火腿肠
培根
香肠
午餐肉
肉松
面包
吐司
饼干
蛋糕
巧克力
照片
塑料袋
保温杯
一个洋葱
几个土豆
香蕉一根
半根胡萝卜
刷表面蛋液
```

---

## 33. 菜谱反向关联测试

清洗完成后随机选基础食材，例如：

```text
番茄
鸡蛋
猪肉
土豆
苹果
```

执行：

```sql
SELECT d.*
FROM dishes d
JOIN dish_ingredients di ON di.dish_id = d.id
JOIN ingredients i ON i.id = di.ingredient_id
WHERE i.name = '番茄';
```

必须能正常查到菜谱。

然后检查：

原本类似：

```text
一个番茄
西红柿
番茄切丁
```

如果属于明确同义或形态变化，都应该能指向正确 canonical ingredient。

---

## 34. 功效关联验收

对于最终保留的食材：

```text
ingredient_effects
```

不允许引用被删除的 ID。

MERGE 后：

```text
ingredient_id + effect_id
```

必须唯一。

不要产生重复行。

同样适用于：

```text
ingredient_groups
```

---

## 35. 营养字段验收

如果：

```text
nutrition_match
```

存在，则：

```text
nutrition_source_name
```

必须能对应明确食物。

尤其检查：

```text
猪肉
牛肉
鸡蛋
番茄
苹果
香蕉
```

不要再次出现过去那种：

```text
肉 -> 乌龟
切段 -> 带鱼
```

之类的错误映射。

不允许使用模糊包含匹配营养表。

---

## 36. 最终 Cleaning Report 必须写清楚

生成：

```text
CLEANING_REPORT.md
```

至少报告：

```text
旧食材总数
新食材总数

KEEP 数量
MERGE 数量
DROP 数量
SPLIT 数量
REVIEW 数量

删除调味料数量
删除加工食品数量
删除非食材数量
修复数量残留数量
修复形态描述数量

dish_ingredients 总数
main 多少
seasoning 多少
other 多少

旧 ingredient_id -> 新 ingredient_id 映射成功数量

ingredient_effects 原数量 / 新数量
ingredient_groups 原数量 / 新数量

外键孤儿数量

营养数据覆盖率
功效数据覆盖率
菜谱关联覆盖率
```

必须输出具体数字，不能只写“清洗完成”。

---

## 37. 实施顺序

严格按下面顺序执行：

```text
1. 读取所有 CSV，不修改原文件

2. 给当前 main_ingredient 按行生成 old_id

3. 建立基础原始食材 canonical 词典

4. 对所有 16,693 个名字执行：
   KEEP / MERGE / DROP / SPLIT / REVIEW

5. 生成 ingredient_id_map.csv

6. 生成新的 main_ingredient.csv，并明确写入新 id

7. 重写 dish_ingredients.ingredient_id
   同时重新生成 role

8. 重写 ingredient_effects

9. 重写 ingredient_groups

10. 检查/重建 dishes 相关统计字段

11. 检查 dish_nutrition 是否仍符合口径
    不完整时不得生成伪完整营养

12. 精简分类表

13. 更新 schema.sql

14. 更新 load_to_mysql.py

15. 运行完整性检查和回归测试

16. 生成 CLEANING_REPORT.md
```

---

## 38. Codex 实现要求

请将这次清洗实现成可重复运行脚本，而不是手工改 CSV。

建议目录：

```text
scripts/
├── clean_ingredients.py
├── rebuild_dish_ingredients.py
├── rebuild_effect_relations.py
├── rebuild_group_relations.py
├── validate_database.py
└── generate_cleaning_report.py
```

要求：

1. 任何自动 MERGE 必须可追溯。
2. 任何 DROP 必须记录原因。
3. 任何不确定项必须进入 REVIEW。
4. 运行两遍应产生完全一致的结果。
5. 不允许随机匹配。
6. 不允许使用模糊包含关系强行匹配营养数据。
7. 所有输出统一 UTF-8。
8. CSV 中 NULL 的表示方式统一。
9. 写入前先进行主键、唯一性和外键检查。
10. 任意阶段失败时不得覆盖上一版成功数据。

---

## 39. 最终验收目标

最终数据库应满足：

> `main_ingredient` 是一个高质量、低噪声的基础食材字典，而不是菜谱原始用料字符串的集合。

最终用户看到的应该是：

```text
番茄
土豆
胡萝卜
苹果
香蕉
猪肉
牛肉
鸡肉
鸡蛋
鲈鱼
虾
香菇
...
```

而不是：

```text
一个洋葱
香蕉一根
胡萝卜切丁
猪肉薄片
刷表面蛋液
克肉
盐
生抽
培根
照片
塑料袋
```

同时必须保证：

```text
基础食材
   ↓
营养
功效
适用人群
菜谱
```

所有关系都能正确追溯，不出现错误 ID、孤儿记录、错误营养继承或因为删行造成的关联错位。
