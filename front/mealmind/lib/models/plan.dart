/// 数据模型 —— 严格对应 docs/接口契约.md 的响应结构
///
/// ⚠️ 这里的字段名必须和后端返回的 JSON key 完全一致。
/// 后端改了字段名，这里也要同步改，否则解析会静默失败（显示空白）。
library;

// =====================================================================
// 元信息
// =====================================================================

class PlanMeta {
  final String generatedAt; // 生成时间
  final int solveMs; // 求解耗时（毫秒）
  final String solver; // 求解器名称

  const PlanMeta({
    required this.generatedAt,
    required this.solveMs,
    required this.solver,
  });

  factory PlanMeta.fromJson(Map<String, dynamic> j) => PlanMeta(
    generatedAt: j['generated_at'] as String? ?? '',
    solveMs: (j['solve_ms'] as num?)?.toInt() ?? 0,
    solver: j['solver'] as String? ?? '',
  );
}

// ⚠️ 这里原来有 priceDataDate / priceCity 两个字段（价格数据日期 / 城市），
//    以及下面 ShoppingItem 的 price / priceSource 和 Plan 的 budget / totalCost。
//    全部删掉了：清洗库里**没有任何价格数据**，这些数字来自手写的
//    assets/mock/plan.json（¥296 这种），却被当成「本地公示价格（置信度：高）」
//    展示出来。没有数据支撑的金额不该出现在界面上。

// =====================================================================
// 营养汇总
// =====================================================================

class PlanNutrition {
  final int calories;
  final int proteinG;
  final int vegetableG;
  final int sodiumMg;
  final int sodiumLimitMg;

  const PlanNutrition({
    required this.calories,
    required this.proteinG,
    required this.vegetableG,
    required this.sodiumMg,
    required this.sodiumLimitMg,
  });

  factory PlanNutrition.fromJson(Map<String, dynamic> j) => PlanNutrition(
    calories: (j['calories_per_person_per_day'] as num?)?.toInt() ?? 0,
    proteinG: (j['protein_g_per_person_per_day'] as num?)?.toInt() ?? 0,
    vegetableG: (j['vegetable_g_per_person_per_day'] as num?)?.toInt() ?? 0,
    sodiumMg: (j['sodium_mg_per_person_per_day'] as num?)?.toInt() ?? 0,
    sodiumLimitMg:
        (j['sodium_limit_mg_per_person_per_day'] as num?)?.toInt() ?? 2000,
  );

  /// 钠摄入占上限的百分比（0.0 ~ 1.0+），用于画进度条
  double get sodiumRatio => sodiumLimitMg <= 0 ? 0 : sodiumMg / sodiumLimitMg;
}

// =====================================================================
// 菜品 / 餐次 / 一天
// =====================================================================

class Dish {
  final int id;
  final String name;
  final int servings;
  final String reason; // ★ 推荐理由 —— 答辩卖点，必须由后端算好
  final List<String> tags;

  const Dish({
    required this.id,
    required this.name,
    required this.servings,
    required this.reason,
    required this.tags,
  });

  factory Dish.fromJson(Map<String, dynamic> j) => Dish(
    id: (j['id'] as num?)?.toInt() ?? 0,
    name: j['name'] as String? ?? '',
    servings: (j['servings'] as num?)?.toInt() ?? 1,
    reason: j['reason'] as String? ?? '',
    tags: ((j['tags'] as List?) ?? const []).map((e) => e.toString()).toList(),
  );
}

class Meal {
  final String slot; // breakfast | lunch | dinner
  final List<Dish> dishes;

  const Meal({required this.slot, required this.dishes});

  factory Meal.fromJson(Map<String, dynamic> j) => Meal(
    slot: j['slot'] as String? ?? '',
    dishes: ((j['dishes'] as List?) ?? const [])
        .map((e) => Dish.fromJson(e as Map<String, dynamic>))
        .toList(),
  );

  String get slotLabel =>
      const {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐'}[slot] ?? slot;
}

class PlanDay {
  final String date; // YYYY-MM-DD
  final String weekday; // 周一
  final List<Meal> meals;

  const PlanDay({
    required this.date,
    required this.weekday,
    required this.meals,
  });

  factory PlanDay.fromJson(Map<String, dynamic> j) => PlanDay(
    date: j['date'] as String? ?? '',
    weekday: j['weekday'] as String? ?? '',
    meals: ((j['meals'] as List?) ?? const [])
        .map((e) => Meal.fromJson(e as Map<String, dynamic>))
        .toList(),
  );

  /// 只取 MM-DD 用于显示
  String get shortDate => date.length >= 10 ? date.substring(5) : date;
}

// =====================================================================
// 采购清单
// =====================================================================

class ShoppingItem {
  final String name;
  final double amount;
  final String unit;

  const ShoppingItem({
    required this.name,
    required this.amount,
    required this.unit,
  });

  factory ShoppingItem.fromJson(Map<String, dynamic> j) => ShoppingItem(
    name: j['name'] as String? ?? '',
    amount: (j['amount'] as num?)?.toDouble() ?? 0,
    unit: j['unit'] as String? ?? '',
  );

  /// 数量显示：整数不显示小数点（500 而不是 500.0）
  String get amountLabel {
    final s = amount == amount.roundToDouble()
        ? amount.toInt().toString()
        : amount.toString();
    return '$s$unit';
  }
}

class ShoppingCategory {
  final String category;
  final List<ShoppingItem> items;

  const ShoppingCategory({required this.category, required this.items});

  factory ShoppingCategory.fromJson(Map<String, dynamic> j) => ShoppingCategory(
    category: j['category'] as String? ?? '',
    items: ((j['items'] as List?) ?? const [])
        .map((e) => ShoppingItem.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

// =====================================================================
// 顶层：一周方案
// =====================================================================

class Plan {
  final String week;
  final PlanMeta meta;
  final PlanNutrition nutrition;
  final List<PlanDay> days;
  final List<ShoppingCategory> shoppingList;

  const Plan({
    required this.week,
    required this.meta,
    required this.nutrition,
    required this.days,
    required this.shoppingList,
  });

  factory Plan.fromJson(Map<String, dynamic> j) => Plan(
    week: j['week'] as String? ?? '',
    meta: PlanMeta.fromJson((j['meta'] as Map<String, dynamic>?) ?? const {}),
    nutrition: PlanNutrition.fromJson(
      (j['nutrition'] as Map<String, dynamic>?) ?? const {},
    ),
    days: ((j['days'] as List?) ?? const [])
        .map((e) => PlanDay.fromJson(e as Map<String, dynamic>))
        .toList(),
    shoppingList: ((j['shopping_list'] as List?) ?? const [])
        .map((e) => ShoppingCategory.fromJson(e as Map<String, dynamic>))
        .toList(),
  );

  /// 清单条目总数
  int get itemCount => shoppingList.fold(0, (sum, c) => sum + c.items.length);
}
