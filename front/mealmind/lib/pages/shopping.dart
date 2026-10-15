import 'package:flutter/material.dart';

import '../services/backend_api.dart';
import '../services/auth_store.dart';
import '../services/api_config.dart';

class ShoppingPage extends StatefulWidget {
  const ShoppingPage({super.key, this.initial});
  final Map<String, dynamic>? initial;
  @override
  State<ShoppingPage> createState() => _ShoppingPageState();
}

class _ShoppingPageState extends State<ShoppingPage> {
  Map<String, dynamic>? _data;
  bool _loading = true;
  String? _error;
  final Set<int> _saving = <int>{};
  late final String _owner;
  String get _scope =>
      '${BackendStatus.instance.apiBase}:${AuthStore.instance.user?.id}';
  void _accountChanged() {
    if (!mounted || _scope == _owner) return;
    setState(() {
      _data = null;
      _loading = false;
      _error = '账号已变更，请返回菜单页重新打开购物清单。';
    });
  }

  @override
  void dispose() {
    AuthStore.instance.removeListener(_accountChanged);
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _owner = _scope;
    AuthStore.instance.addListener(_accountChanged);
    _load();
  }

  Future<void> _load() async {
    try {
      final data =
          widget.initial ?? await BackendApi.instance.fetchShoppingList();
      if (mounted && _scope == _owner) {
        setState(() {
          _data = data;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted && _scope == _owner) {
        setState(() {
          _error = describeNetworkError(e);
          _loading = false;
        });
      }
    }
  }

  Future<void> _check(Map<String, dynamic> item, bool checked) async {
    final id = item['id'] as int;
    setState(() => _saving.add(id));
    try {
      await BackendApi.instance.checkShoppingItem(id, checked);
      if (mounted && _scope == _owner) {
        setState(() {
          item['checked'] = checked;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted && _scope == _owner) {
        setState(() => _error = describeNetworkError(e));
      }
    } finally {
      if (mounted && _scope == _owner) {
        setState(() => _saving.remove(id));
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('购物清单')),
    body: _loading
        ? const Center(child: CircularProgressIndicator())
        : ListView(
            padding: const EdgeInsets.all(16),
            children: [
              if (_error != null) Text(_error!),
              if (_data == null)
                const Text('暂无购物清单，请先在今日菜单中生成。')
              else ...[
                Text(
                  _data!['title'] as String? ?? '购物清单',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                for (final warning in (_data!['warnings'] as List?) ?? [])
                  Text(
                    warning.toString(),
                    style: const TextStyle(fontSize: 12),
                  ),
                if (_data!['total_items'] == 0)
                  const Padding(
                    padding: EdgeInsets.all(12),
                    child: Text('没有待购条目，请核对库存和原菜谱用量。'),
                  ),
                for (final group
                    in ((_data!['categories'] as List?) ?? [])
                        .whereType<Map<String, dynamic>>()) ...[
                  Padding(
                    padding: const EdgeInsets.only(top: 16),
                    child: Text(group['category'] as String? ?? '其他'),
                  ),
                  for (final item
                      in ((group['items'] as List?) ?? [])
                          .whereType<Map<String, dynamic>>())
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(item['name'] as String? ?? ''),
                      subtitle: Text(
                        item['needs_confirmation'] == true
                            ? '用量待确认 · ${item['unit']}'
                            : '${item['amount']} ${item['unit']}',
                      ),
                      value: item['checked'] == true,
                      onChanged: _saving.contains(item['id'])
                          ? null
                          : (v) => _check(item, v ?? false),
                    ),
                ],
              ],
            ],
          ),
  );
}
