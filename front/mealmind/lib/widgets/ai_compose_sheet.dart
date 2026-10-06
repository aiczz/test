// AI 配菜面板 —— 导航栏 AI 模块里那个「根据我选好的食材配这一餐」的入口。
//
// 【它解决什么】
// 以前 AI 页只有一个对话框：用户得自己把「我有什么」打出来。
// 现在把三样东西直接喂给后端：
//   1. 用户勾选的食材（默认取「我的食材」）
//   2. 今日菜单里已有的菜 —— 必须排除，不能重复推荐
//   3. 家庭硬约束（人数 / 可用时间 / 限钠 / 口味 / 忌口）
// 后端先按综合打分从我们自己的库里筛候选，再让大模型在候选集内挑选与解释。
// 推荐结果可以一键写进「今日菜单」（菜谱页右侧那个 tab 能看到）。
//
// 【为什么强调「候选集内」】
// 后端会把模型返回的、不在候选集里的 id 直接丢弃（见 back/app/services/
// ai_service.py 的 _coerce_picks）。所以这里显示出来的每一道菜，
// 一定真实存在于我们的清洗库里，不会是模型编的。

import 'package:flutter/material.dart';

import '../models/ai_feed.dart';
import '../models/content.dart';
import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../services/backend_api.dart';
import '../services/city.dart';
import '../state/app_state.dart';
import '../state/today_menu.dart';
import '../theme.dart';
import '../pages/recipes.dart';
import 'dish_photo.dart';

Future<void> showAiComposeSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => const AiComposeSheet(),
  );
}

class AiComposeSheet extends StatefulWidget {
  const AiComposeSheet({super.key});

  @override
  State<AiComposeSheet> createState() => _AiComposeSheetState();
}

class _AiComposeSheetState extends State<AiComposeSheet> {
  final TextEditingController _message = TextEditingController();

  List<MyFoodEntry> _pantry = const <MyFoodEntry>[];
  final Set<int> _selectedFoodIds = <int>{};

  bool _loadingPantry = false;
  bool _running = false;
  String? _error;
  AiComposeResult? _result;

  @override
  void initState() {
    super.initState();
    _loadPantry();
  }

  @override
  void dispose() {
    _message.dispose();
    super.dispose();
  }

  /// 拉「我的食材」。后端离线或没登录时保持为空 —— 面板仍然可用
  /// （不选食材就走「按时令推荐」那条路），不弹错误。
  Future<void> _loadPantry() async {
    if (!BackendStatus.instance.online || !AuthStore.instance.isLoggedIn) {
      return;
    }
    setState(() => _loadingPantry = true);
    try {
      final items = await BackendApi.instance.fetchMyFoods();
      if (!mounted) return;
      setState(() {
        _pantry = items;
        // 默认全选 —— 用户点进「配菜」通常就是想「用我现有的东西做」
        _selectedFoodIds
          ..clear()
          ..addAll(items.map((e) => e.foodId).whereType<int>());
      });
    } catch (error) {
      debugPrint('[AiComposeSheet] 我的食材加载失败：$error');
    } finally {
      if (mounted) setState(() => _loadingPantry = false);
    }
  }

  Future<void> _run() async {
    if (_running) return;
    setState(() {
      _running = true;
      _error = null;
    });

    final profile = AppState.instance.profile;
    // 今日菜单里已有的菜 —— 传 id 让后端排除掉
    final menuIds = TodayMenuStore.instance.items
        .map((recipe) => int.tryParse(recipe.id))
        .whereType<int>()
        .toList();

    try {
      final result = await BackendApi.instance.recommendRecipes(
        foodIds: _selectedFoodIds.toList(),
        menuRecipeIds: menuIds,
        message: _message.text,
        city: CityStore.instance.city.name,
        people: profile.people,
        cookMinutes: profile.cookMinutes,
        lowSodium: profile.lowSodium,
        preferences: profile.preferences.toList(),
        avoid: profile.avoid.toList(),
      );
      if (!mounted) return;
      setState(() => _result = result);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = '配菜失败：$error');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  void _addToTodayMenu(Recipe recipe) {
    final added = TodayMenuStore.instance.add(recipe);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          added ? '已把「${recipe.name}」加入今日菜单' : '「${recipe.name}」已经在今日菜单里了',
        ),
        duration: const Duration(milliseconds: 1400),
        behavior: SnackBarBehavior.floating,
        backgroundColor: orange900,
        shape: const StadiumBorder(),
      ),
    );
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.viewPaddingOf(context).bottom;
    final profile = AppState.instance.profile;
    final menuItems = TodayMenuStore.instance.items;

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.9,
      ),
      padding: EdgeInsets.fromLTRB(18, 12, 18, 16 + bottom),
      decoration: const BoxDecoration(
        color: page,
        borderRadius: BorderRadius.vertical(top: Radius.circular(rBlock)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 42,
              height: 4,
              decoration: BoxDecoration(
                color: line,
                borderRadius: BorderRadius.circular(99),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: orange700,
                  borderRadius: BorderRadius.circular(13),
                ),
                child: const Icon(
                  Icons.auto_awesome,
                  color: Colors.white,
                  size: 20,
                ),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '帮我配这一餐',
                      style: TextStyle(
                        fontSize: 19,
                        fontWeight: FontWeight.w900,
                        color: ink,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '按你的食材、口味、忌口和人数，从 ${_pantry.length} 样现有食材里配',
                      style: const TextStyle(fontSize: 11.5, color: muted),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          Flexible(
            child: ListView(
              shrinkWrap: true,
              children: [
                // ---- 硬约束回显：让用户确认算法是按这些条件筛的 ----
                Wrap(
                  spacing: 7,
                  runSpacing: 7,
                  children: [
                    _Chip(text: '${profile.people} 人'),
                    _Chip(text: '${profile.cookMinutes.round()} 分钟内'),
                    if (profile.lowSodium) const _Chip(text: '低钠'),
                    for (final item in profile.avoid) _Chip(text: '忌$item'),
                    for (final item in profile.preferences) _Chip(text: item),
                  ],
                ),
                const SizedBox(height: 18),

                // ---- 我的食材（可勾选） ----
                _SectionLabel(
                  icon: Icons.kitchen_outlined,
                  text: '我有的食材',
                  trailing: _loadingPantry ? '加载中…' : null,
                ),
                const SizedBox(height: 8),
                if (_pantry.isEmpty)
                  const _Hint(
                    '还没有「我的食材」。可以直接配菜（按时令推荐），'
                    '也可以先去食材页添加几样，推荐会更准。',
                  )
                else
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final entry in _pantry)
                        if (entry.foodId != null)
                          _SelectChip(
                            text: entry.name,
                            selected: _selectedFoodIds.contains(entry.foodId),
                            onTap: () => setState(() {
                              final id = entry.foodId!;
                              if (!_selectedFoodIds.remove(id)) {
                                _selectedFoodIds.add(id);
                              }
                            }),
                          ),
                    ],
                  ),
                const SizedBox(height: 18),

                // ---- 今日菜单已有（只读，会被排除） ----
                _SectionLabel(
                  icon: Icons.restaurant_menu,
                  text: '今日菜单已有',
                  trailing: menuItems.isEmpty ? null : '${menuItems.length} 道',
                ),
                const SizedBox(height: 8),
                if (menuItems.isEmpty)
                  const _Hint('今日菜单还是空的，这一餐可以从头配。')
                else
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final recipe in menuItems) _Chip(text: recipe.name),
                    ],
                  ),
                const SizedBox(height: 16),

                // ---- 一句话补充要求 ----
                TextField(
                  controller: _message,
                  maxLines: 2,
                  minLines: 1,
                  decoration: InputDecoration(
                    hintText: '补充一句（可选）：想喝汤 / 清淡点 / 快点做完…',
                    hintStyle: const TextStyle(fontSize: 13, color: muted),
                    filled: true,
                    fillColor: orange50,
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 12,
                    ),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
                const SizedBox(height: 14),

                if (_error != null) ...[
                  Text(
                    _error!,
                    style: const TextStyle(fontSize: 12, color: orange900),
                  ),
                  const SizedBox(height: 10),
                ],

                FilledButton.icon(
                  onPressed: _running ? null : _run,
                  icon: _running
                      ? const SizedBox(
                          width: 15,
                          height: 15,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.auto_awesome, size: 17),
                  label: Text(_running ? '正在配菜…' : '开始配菜'),
                  style: FilledButton.styleFrom(
                    backgroundColor: orange,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: const StadiumBorder(),
                  ),
                ),

                if (_result != null) ...[
                  const SizedBox(height: 20),
                  _ResultView(
                    result: _result!,
                    onAdd: _addToTodayMenu,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// 结果区
// =====================================================================

class _ResultView extends StatelessWidget {
  final AiComposeResult result;
  final ValueChanged<Recipe> onAdd;

  const _ResultView({required this.result, required this.onAdd});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SectionLabel(
          icon: result.fromAi ? Icons.auto_awesome : Icons.calculate_outlined,
          text: result.fromAi ? '小食配好了' : '算法配好了',
          trailing: result.fromAi ? result.model : '未启用 AI',
        ),
        const SizedBox(height: 10),
        if (result.answer.isNotEmpty)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white,
              border: Border.all(color: line),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Text(
              result.answer,
              style: const TextStyle(fontSize: 13, color: ink, height: 1.7),
            ),
          ),
        const SizedBox(height: 12),
        for (final pick in result.recommendations) ...[
          _ComposeCard(
            pick: pick,
            alreadyAdded: TodayMenuStore.instance.contains(pick.recipe.id),
            onAdd: () => onAdd(pick.recipe),
          ),
          const SizedBox(height: 12),
        ],
        if (result.trace.isNotEmpty) _TraceView(steps: result.trace),
      ],
    );
  }
}

class _ComposeCard extends StatelessWidget {
  final RecipeRecommendation pick;
  final bool alreadyAdded;
  final VoidCallback onAdd;

  const _ComposeCard({
    required this.pick,
    required this.alreadyAdded,
    required this.onAdd,
  });

  @override
  Widget build(BuildContext context) {
    final recipe = pick.recipe;
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: cardDeco(radius: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: 116,
            width: double.infinity,
            child: DishPhoto(asset: recipe.image),
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  recipe.name,
                  style: const TextStyle(
                    fontSize: 15.5,
                    fontWeight: FontWeight.w800,
                    color: ink,
                  ),
                ),
                const SizedBox(height: 5),
                // ★ 理由由后端给出：AI 在线时是模型在候选集内写的一句话，
                //   离线时是算法的确定性理由。两种情况都不假装。
                Text(
                  pick.reason,
                  style: const TextStyle(fontSize: 12, color: muted, height: 1.55),
                ),
                const SizedBox(height: 9),
                Wrap(
                  spacing: 7,
                  runSpacing: 7,
                  children: [
                    _Chip(text: recipe.time),
                    if (pick.matchedFoods.isNotEmpty)
                      _Chip(
                        text: '用上 ${pick.matchedFoods.join('、')}',
                        highlight: true,
                      ),
                    for (final item in pick.highlights.take(2))
                      _Chip(text: item, highlight: true),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => openRecipeDetail(context, recipe),
                        icon: const Icon(Icons.menu_book_rounded, size: 16),
                        label: const Text('查看做法'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: orange700,
                          padding: const EdgeInsets.symmetric(vertical: 11),
                        ),
                      ),
                    ),
                    const SizedBox(width: 9),
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: alreadyAdded ? null : onAdd,
                        icon: Icon(
                          alreadyAdded
                              ? Icons.check_rounded
                              : Icons.add_rounded,
                          size: 16,
                        ),
                        label: Text(alreadyAdded ? '已加入' : '加入今日菜单'),
                        style: FilledButton.styleFrom(
                          backgroundColor: orange,
                          padding: const EdgeInsets.symmetric(vertical: 11),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 后端的协作轨迹（真实发生的，不是前端演的）
class _TraceView extends StatelessWidget {
  final List<AgentStep> steps;

  const _TraceView({required this.steps});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: orange50,
        border: Border.all(color: orange100),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.account_tree_outlined,
                size: 15,
                color: orange700,
              ),
              const SizedBox(width: 6),
              const Text(
                '这次配菜实际做了什么',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  color: orange900,
                ),
              ),
              const Spacer(),
              Text(
                '${steps.fold<int>(0, (sum, s) => sum + s.ms)} ms',
                style: const TextStyle(fontSize: 10, color: orange700),
              ),
            ],
          ),
          const SizedBox(height: 10),
          for (final step in steps)
            Padding(
              padding: const EdgeInsets.only(bottom: 7),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    step.status == 'veto'
                        ? Icons.block
                        : (step.status == 'info'
                              ? Icons.info_outline
                              : Icons.check),
                    size: 12,
                    color: step.status == 'veto' ? orange : orange700,
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      '${step.agent}：${step.summary}',
                      style: const TextStyle(
                        fontSize: 11,
                        color: muted,
                        height: 1.5,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

// =====================================================================
// 小组件
// =====================================================================

class _SectionLabel extends StatelessWidget {
  final IconData icon;
  final String text;
  final String? trailing;

  const _SectionLabel({
    required this.icon,
    required this.text,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 15, color: orange700),
        const SizedBox(width: 6),
        Text(
          text,
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w800,
            color: ink,
          ),
        ),
        if (trailing != null) ...[
          const Spacer(),
          Text(
            trailing!,
            style: const TextStyle(fontSize: 10.5, color: muted),
          ),
        ],
      ],
    );
  }
}

class _Hint extends StatelessWidget {
  final String text;

  const _Hint(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(fontSize: 11.5, color: muted, height: 1.6),
    );
  }
}

class _Chip extends StatelessWidget {
  final String text;
  final bool highlight;

  const _Chip({required this.text, this.highlight = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: highlight ? orange50 : Colors.white,
        border: Border.all(color: highlight ? orange100 : line),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: highlight ? orange700 : ink,
        ),
      ),
    );
  }
}

class _SelectChip extends StatelessWidget {
  final String text;
  final bool selected;
  final VoidCallback onTap;

  const _SelectChip({
    required this.text,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(999),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
        decoration: BoxDecoration(
          color: selected ? orange : Colors.white,
          border: Border.all(color: selected ? orange : line),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              selected ? Icons.check_circle : Icons.circle_outlined,
              size: 13,
              color: selected ? Colors.white : muted,
            ),
            const SizedBox(width: 5),
            Text(
              text,
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w600,
                color: selected ? Colors.white : ink,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
