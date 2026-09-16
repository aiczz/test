import 'package:flutter/material.dart';

import '../models/plan.dart';
import '../services/api.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// =====================================================================
/// 今日 / 本周菜单 + 购物清单
///
/// 这一页是「吃什么 + 买什么」的落点，也是答辩主战场。
/// 三样东西是别的队伍做不出来的，都在这里：
///   1. 权衡滑杆（省钱 ↔ 健康）—— 多目标优化的可视化
///   2. 钠摄入 / 上限进度条 —— 硬约束真的被求解器管住了
///   3. 每项价格带【来源 + 置信度】—— 三级降级的诚实标注
/// =====================================================================

class MenuPage extends StatefulWidget {
  const MenuPage({super.key});

  @override
  State<MenuPage> createState() => _MenuPageState();
}

class _MenuPageState extends State<MenuPage> {
  late Future<Plan> _future;

  /// 权衡滑杆：0 = 只图省钱，100 = 只图健康
  /// 后端接上之后，这个值会作为权重传给求解器触发重解
  double _weight = 50;

  @override
  void initState() {
    super.initState();
    _future = _load();
    // ★ 监听家庭档案：用户在「我的」页一点保存，这里立刻按新约束重算。
    //   这是「家庭档案是求解器的输入」这句注释的兑现处 ——
    //   在此之前它只是一句注释，界面上没有任何东西真的用到了家庭档案。
    AppState.instance.addListener(_onProfileChanged);
  }

  @override
  void dispose() {
    AppState.instance.removeListener(_onProfileChanged);
    super.dispose();
  }

  void _onProfileChanged() {
    if (!mounted) return;
    _reload();
  }

  /// 从共享状态取家庭档案，作为求解输入
  Future<Plan> _load() {
    final p = AppState.instance.profile;
    return fetchPlan(
      people: p.people,
      budget: p.budget,
      lowSodium: p.lowSodium,
      preferences: p.preferences.toList(),
      avoid: p.avoid.toList(),
    );
  }

  void _reload() => setState(() => _future = _load());

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          '本周菜单',
          style: TextStyle(fontWeight: FontWeight.w800),
        ),
        actions: [
          IconButton(
            onPressed: _reload,
            icon: const Icon(Icons.refresh),
            tooltip: '重新求解',
          ),
        ],
      ),
      body: FutureBuilder<Plan>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const _Loading();
          }
          if (snap.hasError) {
            return _ErrorView(error: snap.error!, onRetry: _reload);
          }
          return _PlanBody(
            plan: snap.data!,
            weight: _weight,
            onWeightChanged: (v) => setState(() => _weight = v),
          );
        },
      ),
    );
  }
}

// =====================================================================
// 加载 / 错误
// =====================================================================

class _Loading extends StatelessWidget {
  const _Loading();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(color: green700),
          SizedBox(height: 16),
          Text('正在求解本周方案…', style: TextStyle(color: muted)),
        ],
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final Object error;
  final VoidCallback onRetry;

  const _ErrorView({required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    // 契约里的 INFEASIBLE（约束冲突）给不一样的提示
    final isInfeasible = error is PlanApiException &&
        (error as PlanApiException).isInfeasible;

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isInfeasible ? Icons.tune : Icons.cloud_off,
              size: 44,
              color: muted,
            ),
            const SizedBox(height: 16),
            Text(
              isInfeasible ? '当前约束下无解' : '方案加载失败',
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: ink,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              isInfeasible
                  ? '预算、营养与忌口要求无法同时满足，\n可以试着放宽一条约束。'
                  : '$error',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 13, color: muted, height: 1.6),
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: onRetry,
              style: FilledButton.styleFrom(backgroundColor: green700),
              child: const Text('重试'),
            ),
          ],
        ),
      ),
    );
  }
}

// =====================================================================
// 主体
// =====================================================================

class _PlanBody extends StatelessWidget {
  final Plan plan;
  final double weight;
  final ValueChanged<double> onWeightChanged;

  const _PlanBody({
    required this.plan,
    required this.weight,
    required this.onWeightChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            children: [
              const _ActiveConstraintsCard(),
              const SizedBox(height: 12),
              _WeightSlider(value: weight, onChanged: onWeightChanged),
              const SizedBox(height: 14),
              _SummaryCard(plan: plan),
              const SizedBox(height: 22),
              for (final day in plan.days) ...[
                _DayCard(day: day),
                const SizedBox(height: 12),
              ],
              const SizedBox(height: 4),
              _MetaFooter(plan: plan),
            ],
          ),
        ),
        _ShoppingBar(plan: plan),
      ],
    );
  }
}

// ---- 本次求解实际采用的约束 ----
//
// 这一栏是「家庭档案 → 求解输入」这条链路的显式证据：
// 在「我的」页改完设置再回到这一页，人数 / 预算 / 钠上限立刻对得上号。
// 答辩时这是最省事的一段演示。

class _ActiveConstraintsCard extends StatelessWidget {
  const _ActiveConstraintsCard();

  @override
  Widget build(BuildContext context) {
    final p = AppState.instance.profile;
    final prefText = p.preferences.isEmpty ? '无' : p.preferences.join('、');
    final avoidText = p.avoid.isEmpty ? '无' : p.avoid.join('、');

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      decoration: cardDeco(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.tune, size: 16, color: green700),
              const SizedBox(width: 6),
              const Text(
                '本次求解采用的约束',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  color: ink,
                ),
              ),
              const Spacer(),
              const Text(
                '来自「我的」家庭档案',
                style: TextStyle(fontSize: 10, color: muted),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _Tag(text: '${p.people} 人', bg: green100, fg: green700),
              _Tag(
                text: '预算 ¥${p.budget.toStringAsFixed(0)}',
                bg: green100,
                fg: green700,
              ),
              _Tag(
                text: '钠上限 ${p.sodiumLimitMg}mg',
                bg: p.lowSodium ? green100 : orange100,
                fg: p.lowSodium ? green700 : orange,
              ),
              _Tag(text: '忌口 $avoidText', bg: green100, fg: green700),
              _Tag(text: '口味 $prefText', bg: green100, fg: green700),
              _Tag(
                text: '厨具 ${p.tools.length} 种',
                bg: green100,
                fg: green700,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ---- 权衡滑杆 ----

class _WeightSlider extends StatelessWidget {
  final double value;
  final ValueChanged<double> onChanged;

  const _WeightSlider({required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    // 滑杆左右端的标签随位置高亮
    final leftOn = value < 35;
    final rightOn = value > 65;

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
      decoration: cardDeco(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '省钱',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: leftOn ? FontWeight.w800 : FontWeight.w500,
                  color: leftOn ? green700 : muted,
                ),
              ),
              const Spacer(),
              const Text(
                '权衡',
                style: TextStyle(fontSize: 11, color: muted),
              ),
              const Spacer(),
              Text(
                '健康',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: rightOn ? FontWeight.w800 : FontWeight.w500,
                  color: rightOn ? green700 : muted,
                ),
              ),
            ],
          ),
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: green600,
              inactiveTrackColor: green100,
              thumbColor: green700,
              overlayColor: const Color(0x1A17733D),
            ),
            child: Slider(
              value: value,
              min: 0,
              max: 100,
              onChanged: onChanged,
            ),
          ),
          Text(
            '拖动滑杆重新权衡（接上求解器后会实时重解）',
            style: const TextStyle(fontSize: 11, color: muted),
          ),
        ],
      ),
    );
  }
}

// ---- 预算 + 营养汇总 ----

class _SummaryCard extends StatelessWidget {
  final Plan plan;

  const _SummaryCard({required this.plan});

  @override
  Widget build(BuildContext context) {
    final over = plan.budgetRatio > 1;
    final sodium = plan.nutrition;

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: cardDeco(radius: rBlock),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '¥${plan.totalCost.toStringAsFixed(0)}',
                style: const TextStyle(
                  fontSize: 30,
                  fontWeight: FontWeight.w900,
                  color: green900,
                  height: 1,
                ),
              ),
              const SizedBox(width: 6),
              Text(
                '/ 预算 ¥${plan.budget.toStringAsFixed(0)}',
                style: const TextStyle(fontSize: 13, color: muted),
              ),
              const Spacer(),
              _Tag(
                text: '${(plan.budgetRatio * 100).toStringAsFixed(0)}%',
                bg: over ? orange100 : green100,
                fg: over ? orange : green700,
              ),
            ],
          ),
          const SizedBox(height: 10),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: plan.budgetRatio.clamp(0.0, 1.0).toDouble(),
              minHeight: 7,
              backgroundColor: line,
              valueColor: AlwaysStoppedAnimation<Color>(
                over ? orange : green600,
              ),
            ),
          ),
          const SizedBox(height: 18),
          const Divider(height: 1, color: line),
          const SizedBox(height: 16),

          // 钠摄入 —— 慢病硬约束的直观体现
          Row(
            children: [
              const Icon(Icons.water_drop_outlined, size: 15, color: muted),
              const SizedBox(width: 6),
              const Text(
                '钠摄入',
                style: TextStyle(fontSize: 13, color: ink),
              ),
              const Spacer(),
              Text(
                '${sodium.sodiumMg} / ${sodium.sodiumLimitMg} mg',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: sodium.sodiumRatio > 1 ? orange : green700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: sodium.sodiumRatio.clamp(0.0, 1.0).toDouble(),
              minHeight: 6,
              backgroundColor: line,
              valueColor: AlwaysStoppedAnimation<Color>(
                sodium.sodiumRatio > 0.95 ? orange : green600,
              ),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            sodium.sodiumRatio > 0.95
                ? '已接近上限 —— 这是求解器管住的硬约束，不是打分项'
                : '在限值以内',
            style: const TextStyle(fontSize: 11, color: muted),
          ),

          const SizedBox(height: 16),
          // 营养三项
          Row(
            children: [
              _NutriChip(
                label: '热量',
                value: '${sodium.calories}',
                unit: 'kcal',
              ),
              const SizedBox(width: 8),
              _NutriChip(
                label: '蛋白',
                value: '${sodium.proteinG}',
                unit: 'g',
              ),
              const SizedBox(width: 8),
              _NutriChip(
                label: '蔬菜',
                value: '${sodium.vegetableG}',
                unit: 'g',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _NutriChip extends StatelessWidget {
  final String label;
  final String value;
  final String unit;

  const _NutriChip({
    required this.label,
    required this.value,
    required this.unit,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
        decoration: BoxDecoration(
          color: green50,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          children: [
            Text(
              label,
              style: const TextStyle(fontSize: 10, color: muted),
            ),
            const SizedBox(height: 4),
            RichText(
              text: TextSpan(
                children: [
                  TextSpan(
                    text: value,
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w800,
                      color: ink,
                    ),
                  ),
                  TextSpan(
                    text: ' $unit',
                    style: const TextStyle(fontSize: 10, color: muted),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 2),
            const Text(
              '每人每天',
              style: TextStyle(fontSize: 9, color: muted),
            ),
          ],
        ),
      ),
    );
  }
}

// ---- 每天的菜单 ----

class _DayCard extends StatelessWidget {
  final PlanDay day;

  const _DayCard({required this.day});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: cardDeco(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                day.weekday,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                  color: ink,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                day.shortDate,
                style: const TextStyle(fontSize: 12, color: muted),
              ),
            ],
          ),
          const SizedBox(height: 12),
          for (var i = 0; i < day.meals.length; i++) ...[
            if (i > 0) const SizedBox(height: 14),
            _MealBlock(meal: day.meals[i]),
          ],
        ],
      ),
    );
  }
}

class _MealBlock extends StatelessWidget {
  final Meal meal;

  const _MealBlock({required this.meal});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: tagDeco(),
              child: Text(
                meal.slotLabel,
                style: const TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  color: green700,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        for (final dish in meal.dishes) _DishTile(dish: dish),
      ],
    );
  }
}

class _DishTile extends StatelessWidget {
  final Dish dish;

  const _DishTile({required this.dish});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  dish.name,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: ink,
                  ),
                ),
              ),
              Text(
                '${dish.servings} 份',
                style: const TextStyle(fontSize: 11, color: muted),
              ),
            ],
          ),
          if (dish.reason.isNotEmpty) ...[
            const SizedBox(height: 5),
            Container(
              padding: const EdgeInsets.fromLTRB(9, 7, 9, 7),
              decoration: BoxDecoration(
                color: green50,
                borderRadius: BorderRadius.circular(10),
                border: const Border(
                  left: BorderSide(color: green600, width: 2.5),
                ),
              ),
              child: Text(
                dish.reason,
                style: const TextStyle(
                  fontSize: 11.5,
                  color: muted,
                  height: 1.55,
                ),
              ),
            ),
          ],
          const SizedBox(height: 6),
          Wrap(
            spacing: 5,
            runSpacing: 5,
            children: [
              for (final t in dish.tags)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: tagDeco(),
                  child: Text(
                    t,
                    style: const TextStyle(
                      fontSize: 10,
                      color: green700,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

// ---- 底部元信息 ----

class _MetaFooter extends StatelessWidget {
  final Plan plan;

  const _MetaFooter({required this.plan});

  @override
  Widget build(BuildContext context) {
    final m = plan.meta;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: green50,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          const Icon(Icons.info_outline, size: 14, color: muted),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '价格数据来自 ${m.priceCity} 官方公示（更新于 ${m.priceDataDate}）· '
              '由 ${m.solver} 求解，耗时 ${m.solveMs} ms',
              style: const TextStyle(fontSize: 11, color: muted, height: 1.5),
            ),
          ),
        ],
      ),
    );
  }
}

// ---- 底部购物清单入口 ----

class _ShoppingBar extends StatelessWidget {
  final Plan plan;

  const _ShoppingBar({required this.plan});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: line)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          child: SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: () => _openShoppingList(context, plan),
              style: FilledButton.styleFrom(
                backgroundColor: orange,
                padding: const EdgeInsets.symmetric(vertical: 15),
                shape: const StadiumBorder(),
              ),
              child: Text(
                '查看购物清单 · ${plan.itemCount} 项 · ¥${plan.totalCost.toStringAsFixed(0)}',
                style: const TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 15,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// =====================================================================
// 购物清单弹层
// =====================================================================

void _openShoppingList(BuildContext context, Plan plan) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.white,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(rBlock)),
    ),
    builder: (_) => _ShoppingSheet(plan: plan),
  );
}

class _ShoppingSheet extends StatelessWidget {
  final Plan plan;

  const _ShoppingSheet({required this.plan});

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.82,
      maxChildSize: 0.95,
      minChildSize: 0.4,
      builder: (context, controller) {
        return Column(
          children: [
            // 拖拽把手
            Container(
              margin: const EdgeInsets.only(top: 10, bottom: 6),
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: line,
                borderRadius: BorderRadius.circular(999),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 6, 12, 10),
              child: Row(
                children: [
                  const Text(
                    '购物清单',
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w900,
                      color: ink,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    '${plan.itemCount} 项 · 合计 ¥${plan.totalCost.toStringAsFixed(0)}',
                    style: const TextStyle(fontSize: 12, color: muted),
                  ),
                  const Spacer(),
                  IconButton(
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close, color: muted),
                  ),
                ],
              ),
            ),
            const Divider(height: 1, color: line),
            Expanded(
              child: ListView(
                controller: controller,
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
                children: [
                  for (final cat in plan.shoppingList) _CategoryBlock(cat: cat),
                  const SizedBox(height: 8),
                  const _PriceLegend(),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

class _CategoryBlock extends StatelessWidget {
  final ShoppingCategory cat;

  const _CategoryBlock({required this.cat});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 18, bottom: 8),
          child: Row(
            children: [
              Text(
                cat.category,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  color: ink,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '小计 ¥${cat.subtotal.toStringAsFixed(1)}',
                style: const TextStyle(fontSize: 11, color: muted),
              ),
            ],
          ),
        ),
        for (final item in cat.items) _ShoppingRow(item: item),
      ],
    );
  }
}

class _ShoppingRow extends StatelessWidget {
  final ShoppingItem item;

  const _ShoppingRow({required this.item});

  @override
  Widget build(BuildContext context) {
    // 三级降级：不同来源给不同颜色的标签
    final bg = _sourceBg(item.priceSource);
    final fg = _sourceFg(item.priceSource);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        children: [
          const Icon(Icons.check_box_outline_blank, size: 17, color: line),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.name,
                  style: const TextStyle(fontSize: 13.5, color: ink),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: bg,
                        borderRadius: BorderRadius.circular(rTag),
                      ),
                      child: Text(
                        item.sourceLabel,
                        style: TextStyle(
                          fontSize: 9.5,
                          color: fg,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    const SizedBox(width: 5),
                    Text(
                      '置信度 ${item.confidenceLabel}',
                      style: const TextStyle(fontSize: 9.5, color: muted),
                    ),
                  ],
                ),
              ],
            ),
          ),
          Text(
            item.amountLabel,
            style: const TextStyle(fontSize: 12, color: muted),
          ),
          const SizedBox(width: 12),
          SizedBox(
            width: 54,
            child: Text(
              '¥${item.price.toStringAsFixed(1)}',
              textAlign: TextAlign.right,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: ink,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 价格来源图例 —— 答辩时这一块能直接讲"我们不假装全国都有精确数据"
class _PriceLegend extends StatelessWidget {
  const _PriceLegend();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: green50,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.info_outline, size: 14, color: muted),
              const SizedBox(width: 6),
              const Text(
                '价格来源说明',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: ink,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          const _LegendRow(
            label: '本地公示价格',
            desc: '该城市有官方开放数据接口，直接采用',
            color: green100,
            fg: green700,
          ),
          const SizedBox(height: 6),
          const _LegendRow(
            label: '周边城市参考价',
            desc: '本地无接口，用同省城市均价折算',
            color: orange100,
            fg: orange,
          ),
          const SizedBox(height: 6),
          const _LegendRow(
            label: '全国均价估算',
            desc: '完全无数据，用全国均价 × 城市系数',
            color: Color(0xFFEFEFEF),
            fg: muted,
          ),
        ],
      ),
    );
  }
}

class _LegendRow extends StatelessWidget {
  final String label;
  final String desc;
  final Color color;
  final Color fg;

  const _LegendRow({
    required this.label,
    required this.desc,
    required this.color,
    required this.fg,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          margin: const EdgeInsets.only(top: 1),
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(rTag),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 9.5,
              color: fg,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            desc,
            style: const TextStyle(fontSize: 10.5, color: muted, height: 1.5),
          ),
        ),
      ],
    );
  }
}

// =====================================================================
// 价格来源配色（三级降级）
// =====================================================================

Color _sourceBg(String source) {
  switch (source) {
    case 'local':
      return green100;
    case 'nearby':
      return orange100;
    default:
      return const Color(0xFFEFEFEF);
  }
}

Color _sourceFg(String source) {
  switch (source) {
    case 'local':
      return green700;
    case 'nearby':
      return orange;
    default:
      return muted;
  }
}

// =====================================================================
// 小标签
// =====================================================================

class _Tag extends StatelessWidget {
  final String text;
  final Color bg;
  final Color fg;

  const _Tag({required this.text, required this.bg, required this.fg});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(rTag),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w800,
          color: fg,
        ),
      ),
    );
  }
}
