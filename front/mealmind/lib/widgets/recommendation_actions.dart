import 'package:flutter/material.dart';

import '../models/content.dart';
import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../services/backend_api.dart';
import '../services/recipe_feedback_store.dart';

class BatchFoodButton extends StatefulWidget {
  const BatchFoodButton({super.key, required this.foods});
  final List<Food> foods;
  @override
  State<BatchFoodButton> createState() => _BatchFoodButtonState();
}

class _BatchFoodButtonState extends State<BatchFoodButton> {
  bool _busy = false;
  String get _scope =>
      '${BackendStatus.instance.apiBase}:${AuthStore.instance.user?.id}';
  void _notice(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    }
  }

  Future<void> _add() async {
    if (!AuthStore.instance.isLoggedIn) {
      _notice('请先登录，再加入我的食材');
      return;
    }
    if (!BackendStatus.instance.online) {
      _notice('连接后端后才能加入我的食材');
      return;
    }
    final scope = _scope;
    setState(() => _busy = true);
    try {
      final ids = widget.foods
          .map((f) => int.tryParse(f.id))
          .whereType<int>()
          .toList();
      if (ids.isEmpty) return;
      final result = await BackendApi.instance.addMyFoodsBatch(ids);
      if (_scope == scope) {
        _notice(
          '新增 ${result['added_count']} 样，已有 ${result['existing_count']} 样保持原数量。新项目用量待确认。',
        );
      }
    } catch (_) {
      if (_scope == scope) _notice('添加失败，可重试；已有食材不会重复累加');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => OutlinedButton.icon(
    onPressed: _busy ? null : _add,
    icon: Icon(_busy ? Icons.hourglass_top : Icons.playlist_add, size: 17),
    label: const Text('全部加入我的食材'),
  );
}

class RecipeFeedbackButton extends StatefulWidget {
  const RecipeFeedbackButton({super.key, required this.recipeId});
  final String recipeId;
  @override
  State<RecipeFeedbackButton> createState() => _RecipeFeedbackButtonState();
}

class _RecipeFeedbackButtonState extends State<RecipeFeedbackButton> {
  bool _busy = false;
  @override
  void initState() {
    super.initState();
    if (AuthStore.instance.isLoggedIn && BackendStatus.instance.online) {
      RecipeFeedbackStore.instance.load().catchError((Object _) {});
    }
  }

  Future<void> _select(String action) async {
    if (!AuthStore.instance.isLoggedIn || !BackendStatus.instance.online) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('登录并连接后端后，可保存喜好反馈')));
      return;
    }
    final id = int.tryParse(widget.recipeId);
    if (id == null || _busy) return;
    String? reason;
    if (action == 'dislike') {
      reason = await showDialog<String>(
        context: context,
        builder: (context) => SimpleDialog(
          title: const Text('为什么不喜欢这道菜？'),
          children: [
            for (final reason in ['口味不合', '食材不方便', '太费时', '其他'])
              SimpleDialogOption(
                onPressed: () => Navigator.pop(context, reason),
                child: Text(reason),
              ),
          ],
        ),
      );
      if (reason == null || !mounted) return;
    }
    setState(() => _busy = true);
    try {
      final changed = await RecipeFeedbackStore.instance.set(
        id,
        action,
        reason: reason,
      );
      if (!mounted || !changed) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            action == 'dislike'
                ? '已记录，后续 AI 推荐将避开这道菜；可随时撤销'
                : action == 'like'
                ? '已记录，在符合条件的候选中优先考虑'
                : '已撤销反馈',
          ),
        ),
      );
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('保存失败，原反馈未改变，请重试')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: RecipeFeedbackStore.instance,
    builder: (context, _) {
      final value = RecipeFeedbackStore.instance.value(
        int.tryParse(widget.recipeId) ?? -1,
      );
      return PopupMenuButton<String>(
        enabled: !_busy,
        tooltip: '喜好反馈',
        onSelected: _select,
        itemBuilder: (_) => const [
          PopupMenuItem(value: 'like', child: Text('喜欢这道菜')),
          PopupMenuItem(value: 'dislike', child: Text('不喜欢这道菜')),
          PopupMenuItem(value: 'neutral', child: Text('撤销反馈')),
        ],
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Text(
            _busy
                ? '保存中…'
                : value == 'like'
                ? '已喜欢 · 修改'
                : value == 'dislike'
                ? '已不喜欢 · 修改'
                : '喜欢 / 不喜欢',
            style: Theme.of(context).textTheme.labelMedium,
          ),
        ),
      );
    },
  );
}
