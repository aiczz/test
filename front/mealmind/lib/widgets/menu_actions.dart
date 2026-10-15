import 'package:flutter/material.dart';

import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../services/backend_api.dart';
import '../state/app_state.dart';
import '../state/today_menu.dart';
import '../pages/shopping.dart';
import '../models/content.dart';

class MenuActions extends StatefulWidget {
  const MenuActions({super.key});
  @override
  State<MenuActions> createState() => _MenuActionsState();
}

class _MenuActionsState extends State<MenuActions> {
  bool _busy = false;
  bool _subtract = true;
  String? _status;
  String get _scope =>
      '${BackendStatus.instance.apiBase}:${AuthStore.instance.user?.id}';
  Future<void> _run(String action) async {
    if (_busy) return;
    if (!BackendStatus.instance.online || !AuthStore.instance.isLoggedIn) {
      setState(() => _status = '菜单已保存在本机；连接后端并登录后才能同步或生成真实购物清单。');
      return;
    }
    final scope = _scope;
    final store = TodayMenuStore.instance;
    final ids = store.items.map((r) => r.id).toList();
    final day = store.date;
    setState(() {
      _busy = true;
      _status = null;
    });
    try {
      if (action == 'restore') {
        if (ids.isNotEmpty) {
          final confirm = await showDialog<bool>(
            context: context,
            builder: (context) => AlertDialog(
              title: const Text('从云端恢复今日菜单？'),
              content: const Text('将覆盖本机今天已选的菜。'),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('取消'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('恢复'),
                ),
              ],
            ),
          );
          if (confirm != true) return;
        }
        final recipes = await BackendApi.instance.fetchTodayMenu(day);
        if (!mounted || scope != _scope || store.date != day) return;
        if (recipes == null) {
          setState(() => _status = '云端今天没有已选菜，本机菜单已保留。');
          return;
        }
        store.setItems(recipes);
        setState(() => _status = '已恢复云端今日菜单。');
      } else if (action == 'latest') {
        await Navigator.of(
          context,
        ).push(MaterialPageRoute<void>(builder: (_) => const ShoppingPage()));
      } else {
        final plan = await BackendApi.instance.saveTodayMenu(
          ids,
          people: AppState.instance.profile.people,
          date: day,
        );
        if (!mounted || scope != _scope) return;
        if (action == 'save') {
          setState(() => _status = '已保存 $day 的 ${ids.length} 道菜到云端。');
        } else {
          if (store.items.map((r) => r.id).join(',') != ids.join(',') ||
              store.date != day) {
            setState(() => _status = '菜单已变动，请按当前菜单重新生成。');
            return;
          }
          final list = await BackendApi.instance.generateShoppingList(
            plan['id'] as int,
            subtract: _subtract,
          );
          if (!mounted || scope != _scope) return;
          await Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => ShoppingPage(initial: list),
            ),
          );
        }
      }
    } catch (error) {
      if (mounted && scope == _scope) {
        setState(() => _status = describeNetworkError(error));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _replace(Recipe old) async {
    if (_busy) return;
    if (!BackendStatus.instance.online || !AuthStore.instance.isLoggedIn) {
      setState(() => _status = '连接后端后才能按当前条件推荐替换菜。');
      return;
    }
    final scope = _scope;
    final store = TodayMenuStore.instance;
    final retained = store.items
        .where((r) => r.id != old.id)
        .map((r) => int.tryParse(r.id))
        .whereType<int>()
        .toList();
    final exclude = store.items
        .map((r) => int.tryParse(r.id))
        .whereType<int>()
        .toList();
    final profile = AppState.instance.profile;
    setState(() => _busy = true);
    try {
      // Existing dishes guide pairing; the replaced dish is excluded but not counted as retained.
      final result = await BackendApi.instance.recommendRecipes(
        menuRecipeIds: retained,
        excludedRecipeIds: exclude,
        count: 1,
        people: profile.people,
        cookMinutes: profile.cookMinutes,
        lowSodium: profile.lowSodium,
        preferences: profile.preferences.toList(),
        avoid: profile.avoid.toList(),
      );
      if (!mounted || scope != _scope) return;
      if (result.recommendations.isEmpty) {
        setState(() => _status = '没有符合当前条件的替换菜，原菜单已保留。');
        return;
      }
      final pick = result.recommendations.first;
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('将${old.name}换为${pick.recipe.name}？'),
          content: Text('${pick.reason}\n其余已选菜保留。'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('替换'),
            ),
          ],
        ),
      );
      if (confirmed == true &&
          mounted &&
          scope == _scope &&
          store.contains(old.id)) {
        store.replace(old.id, pick.recipe);
        setState(() => _status = '已替换并在本机保存，请同步云端或重新生成购物清单。');
      }
    } catch (error) {
      if (mounted && scope == _scope) {
        setState(() => _status = describeNetworkError(error));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _generate() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: const Text('生成购物清单'),
          content: CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('扣除家里已有食材'),
            subtitle: const Text('仅抵扣数量明确且单位匹配的库存'),
            value: _subtract,
            onChanged: (value) => update(() => _subtract = value ?? true),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('生成'),
            ),
          ],
        ),
      ),
    );
    if (confirmed == true && mounted) await _run('generate');
  }

  Future<void> _chooseReplacement() async {
    final recipe = await showDialog<Recipe>(
      context: context,
      builder: (context) => SimpleDialog(
        title: const Text('选择要替换的菜'),
        children: [
          for (final recipe in TodayMenuStore.instance.items)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(context, recipe),
              child: Text(recipe.name),
            ),
        ],
      ),
    );
    if (recipe != null && mounted) await _replace(recipe);
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: TodayMenuStore.instance,
    builder: (context, _) => Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Wrap(
          spacing: 8,
          alignment: WrapAlignment.center,
          children: [
            OutlinedButton(
              onPressed: _busy ? null : () => _run('save'),
              child: const Text('保存到云端'),
            ),
            FilledButton(
              onPressed: _busy || TodayMenuStore.instance.isEmpty
                  ? null
                  : _generate,
              child: const Text('生成购物清单'),
            ),
            TextButton(
              onPressed: _busy ? null : () => _run('latest'),
              child: const Text('最近购物清单'),
            ),
            PopupMenuButton<String>(
              enabled: !_busy,
              tooltip: '更多操作',
              onSelected: (action) {
                if (action == 'restore') _run('restore');
                if (action == 'replace') _chooseReplacement();
              },
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'restore', child: Text('从云端恢复')),
                PopupMenuItem(
                  value: 'replace',
                  enabled: !TodayMenuStore.instance.isEmpty,
                  child: const Text('替换菜品'),
                ),
              ],
              child: const Padding(
                padding: EdgeInsets.all(12),
                child: Text('更多'),
              ),
            ),
          ],
        ),
        if (_busy) const LinearProgressIndicator(),
        if (_status != null) Text(_status!),
      ],
    ),
  );
}
