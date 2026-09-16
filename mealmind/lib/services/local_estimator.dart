import '../models/plan.dart';
import '../state/app_state.dart';

/// =====================================================================
/// 本地估算 —— 在真求解器就绪前，用【确定性规则】把家庭档案作用到基准方案上
///
/// ⚠️ 说清楚这是什么，不含糊：
///    这不是求解器，也不是 AI。它是本地派生，界面上必须如实标注。
///    它存在的唯一目的，是让「家庭档案 → 菜单 / 购物清单」这条链路
///    现在就是通的、可演示的、可验证的。
///
/// 规则（全部确定性，可复现）：
///    人数    → 采购量与金额按 (人数 / 3) 线性缩放，菜量 servings = 人数
///    预算    → 换成用户设定值，预算占比由界面重算（超支会变色）
///    限钠    → 钠上限 2000mg（限钠）/ 2400mg（不限钠）
///    忌口    → 过滤掉 tags 命中忌口词的菜
///    厨具/时间 → 本期只记录进约束栏，不做过滤
///              （基准数据里还没有「所需厨具」「耗时」这两个字段，
///                硬造一个过滤规则反而是假的）
///
/// 后端 CP-SAT 就绪后：删掉这个文件，把 api.dart 里 useMock 改成 false。
/// =====================================================================

/// 基准方案（assets/mock/plan.json）是按 3 人做的
const int kBasePeople = 3;

/// 把家庭档案作用到基准方案上，返回派生后的方案
Plan applyProfile(Plan base, FamilyProfile p) {
  final ratio = p.people / kBasePeople;

  // ---- 1. 采购量与金额按人数缩放 ----
  final shopping = base.shoppingList.map((cat) {
    final items = cat.items
        .map(
          (it) => ShoppingItem(
            name: it.name,
            amount: _roundAmount(it.amount * ratio),
            unit: it.unit,
            price: _round2(it.price * ratio),
            priceSource: it.priceSource,
          ),
        )
        .toList();
    return ShoppingCategory(category: cat.category, items: items);
  }).toList();

  // 总价按缩放后的明细重算 —— 不做 base.totalCost * ratio，
  // 因为取整之后两者会有分位差，重算才能保证「合计 = 分项之和」对得上。
  final totalCost = _round2(
    shopping.fold<double>(0.0, (sum, cat) => sum + cat.subtotal),
  );

  // ---- 2. 忌口过滤 + 菜量跟随人数 ----
  final days = base.days.map((day) {
    final meals = day.meals.map((meal) {
      final kept = meal.dishes
          .where((d) => !d.tags.any((t) => p.avoid.contains(t)))
          .map(
            (d) => Dish(
              id: d.id,
              name: d.name,
              servings: p.people,
              reason: d.reason,
              tags: d.tags,
            ),
          )
          .toList();
      return Meal(
        // 万一某餐被过滤空了，保留原样 —— 宁可少过滤，也不给用户一个空餐次
        slot: meal.slot,
        dishes: kept.isEmpty ? meal.dishes : kept,
      );
    }).toList();
    return PlanDay(date: day.date, weekday: day.weekday, meals: meals);
  }).toList();

  // ---- 3. 营养是【每人每天】口径，所以人数变了这些值不变，
  //         变的只有钠【上限】（限钠开关控制）----
  final nutrition = PlanNutrition(
    calories: base.nutrition.calories,
    proteinG: base.nutrition.proteinG,
    vegetableG: base.nutrition.vegetableG,
    sodiumMg: base.nutrition.sodiumMg,
    sodiumLimitMg: p.sodiumLimitMg,
  );

  return Plan(
    week: base.week,
    budget: p.budget,
    totalCost: totalCost,
    meta: PlanMeta(
      generatedAt: base.meta.generatedAt,
      priceDataDate: base.meta.priceDataDate,
      priceCity: base.meta.priceCity,
      solveMs: 0,
      solver: '本地估算（待接 CP-SAT 求解器）',
    ),
    nutrition: nutrition,
    days: days,
    shoppingList: shopping,
  );
}

// =====================================================================
// 取整助手 —— 采购量要取整到「买菜时说得出口」的粒度
// =====================================================================

double _round2(double v) => (v * 100).roundToDouble() / 100;

/// 500g → 670g 合理；1.5kg → 2.5kg 合理；0.5 盒 → 1 盒合理
double _roundAmount(double v) {
  if (v >= 100) return (v / 10).roundToDouble() * 10;
  if (v >= 10) return v.roundToDouble();
  return (v * 10).roundToDouble() / 10;
}
