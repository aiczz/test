import 'package:flutter/material.dart';

import '../models/content.dart';
import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../services/backend_api.dart';
import '../theme.dart';

class AddFoodToPantryButton extends StatefulWidget {
  final Food food;
  const AddFoodToPantryButton({super.key, required this.food});

  @override
  State<AddFoodToPantryButton> createState() => _AddFoodToPantryButtonState();
}

class _AddFoodToPantryButtonState extends State<AddFoodToPantryButton> {
  bool _busy = false;
  String? _addedScope;
  String get _scope =>
      '${BackendStatus.instance.apiBase}:${AuthStore.instance.user?.id}';

  void _notice(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _add() async {
    if (!AuthStore.instance.isLoggedIn) {
      _notice('请先登录，再加入我的食材');
      return;
    }
    final id = int.tryParse(widget.food.id);
    if (!BackendStatus.instance.online || id == null) {
      _notice('请连接后端后再加入我的食材');
      return;
    }
    final scope = _scope;
    setState(() => _busy = true);
    try {
      final inventory = await BackendApi.instance.fetchMyFoods();
      if (!mounted || _scope != scope) return;
      final existing = inventory
          .where((entry) => entry.foodId == id)
          .firstOrNull;
      if (existing == null) {
        await BackendApi.instance.addMyFood(foodId: id);
      }
      if (!mounted || _scope != scope) return;
      setState(() => _addedScope = scope);
      _notice(
        existing == null
            ? '已加入「${widget.food.name}」'
            : '「${widget.food.name}」已在我的食材中',
      );
    } catch (_) {
      if (_scope == scope) _notice('加入失败，请检查网络或登录状态后重试');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: AuthStore.instance,
    builder: (context, _) {
      final added = _addedScope == _scope;
      return TextButton.icon(
        onPressed: _busy || added ? null : _add,
        style: TextButton.styleFrom(
          foregroundColor: brand700,
          backgroundColor: brand700.withValues(alpha: 0.06),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(999),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        ),
        icon: _busy
            ? const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : Icon(
                added ? Icons.check_circle_outline : Icons.add_circle_outline,
                size: 16,
              ),
        label: Text(added ? '已加入我的食材' : '加入我的食材'),
      );
    },
  );
}
