import 'package:flutter/foundation.dart';

import 'api_config.dart';
import 'auth_store.dart';
import 'backend_api.dart';

/// Explicit account feedback. A load from an old account cannot replace current state.
class RecipeFeedbackStore extends ChangeNotifier {
  RecipeFeedbackStore({
    required this.scope,
    required this.fetch,
    required this.save,
  });
  static final instance = RecipeFeedbackStore(
    scope: () =>
        '${BackendStatus.instance.apiBase}:${AuthStore.instance.user?.id ?? 'guest'}',
    fetch: BackendApi.instance.fetchRecipeFeedback,
    save: BackendApi.instance.setRecipeFeedback,
  );
  final String Function() scope;
  final Future<List<Map<String, dynamic>>> Function() fetch;
  final Future<void> Function(int, String, String?) save;
  String? _scope;
  Future<void>? _loading;
  bool _loaded = false;
  final Map<int, String> _values = {};

  void _sync() {
    if (_scope == scope()) return;
    _scope = scope();
    _values.clear();
    _loading = null;
    _loaded = false;
  }

  String value(int id) {
    _sync();
    return _values[id] ?? 'neutral';
  }

  Future<void> load() {
    _sync();
    if (_loaded) return Future.value();
    if (_loading != null) return _loading!;
    final requestScope = scope();
    final future = _load(requestScope);
    _loading = future;
    return future;
  }

  Future<void> _load(String requestScope) async {
    try {
      final rows = await fetch();
      if (scope() != requestScope || _scope != requestScope) return;
      _values.clear();
      for (final row in rows) {
        final id = row['recipe_id'];
        if (id is int && row['value'] is String) {
          _values[id] = row['value'] as String;
        }
      }
      _loaded = true;
      notifyListeners();
    } finally {
      if (_scope == requestScope) _loading = null;
    }
  }

  Future<bool> set(int id, String value, {String? reason}) async {
    final requestScope = scope();
    await load();
    if (scope() != requestScope) return false;
    await save(id, value, reason);
    if (scope() != requestScope || _scope != requestScope) return false;
    if (value == 'neutral') {
      _values.remove(id);
    } else {
      _values[id] = value;
    }
    notifyListeners();
    return true;
  }
}
