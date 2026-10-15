import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/content.dart';
import '../services/auth_store.dart';
import '../services/api_config.dart';

/// Date and account scoped menu; local edits survive restarts and work offline.
class TodayMenuStore extends ChangeNotifier {
  TodayMenuStore({String Function()? scopeProvider, DateTime Function()? clock})
    : _scopeProvider =
          scopeProvider ??
          (() =>
              '${BackendStatus.instance.apiBase}:${AuthStore.instance.user?.id ?? 'guest'}'),
      _clock = clock ?? DateTime.now;
  static final TodayMenuStore instance = TodayMenuStore();
  final String Function() _scopeProvider;
  final DateTime Function() _clock;
  final List<Recipe> _items = <Recipe>[];
  String? _key;
  int _revision = 0;
  bool _wired = false;
  Future<void> _pending = Future<void>.value();
  String get date => _clock().toIso8601String().split('T').first;
  String get _currentKey =>
      'today_menu_v2_${Uri.encodeComponent(_scopeProvider())}_$date';
  void _ensureScope() {
    if (_key == _currentKey) return;
    _key = _currentKey;
    _items.clear();
    _revision++;
  }

  Future<void> load() async {
    _ensureScope();
    final key = _key!;
    final revision = _revision;
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(key);
      final decoded = raw == null ? <dynamic>[] : jsonDecode(raw) as List;
      if (key != _currentKey || revision != _revision) return;
      _items
        ..clear()
        ..addAll(
          decoded
              .whereType<Map<String, dynamic>>()
              .map(Recipe.fromJson)
              .where((recipe) => recipe.image.trim().isNotEmpty),
        );
      notifyListeners();
    } catch (_) {
      /* Keep local edits if storage is unavailable. */
    }
  }

  Future<void> initialize() async {
    if (!_wired) {
      AuthStore.instance.addListener(_accountChanged);
      _wired = true;
    }
    await load();
  }

  void _accountChanged() {
    if (_key == _currentKey) return;
    _ensureScope();
    notifyListeners();
    load();
  }

  List<Recipe> get items {
    _ensureScope();
    return List<Recipe>.unmodifiable(
      _items.where((recipe) => recipe.image.trim().isNotEmpty),
    );
  }

  int get count => items.length;
  bool get isEmpty => items.isEmpty;
  bool contains(String id) => items.any((r) => r.id == id);
  bool add(Recipe recipe) {
    _ensureScope();
    if (recipe.image.trim().isEmpty || contains(recipe.id)) return false;
    _items.add(recipe);
    _changed();
    return true;
  }

  void remove(String id) {
    _ensureScope();
    _items.removeWhere((r) => r.id == id);
    _changed();
  }

  void replace(String oldId, Recipe recipe) {
    _ensureScope();
    final index = _items.indexWhere((r) => r.id == oldId);
    if (recipe.image.trim().isEmpty ||
        index < 0 ||
        (recipe.id != oldId && contains(recipe.id))) {
      return;
    }
    _items[index] = recipe;
    _changed();
  }

  void setItems(List<Recipe> recipes) {
    _ensureScope();
    _items
      ..clear()
      ..addAll(
        {
          for (final r in recipes)
            if (r.image.trim().isNotEmpty) r.id: r,
        }.values,
      );
    _changed();
  }

  void clear() {
    _ensureScope();
    _items.clear();
    _changed();
  }

  void _changed() {
    _revision++;
    final key = _key!;
    final raw = jsonEncode(
      _items
          .map(
            (r) => <String, dynamic>{
              'id': r.id,
              'name': r.name,
              'image': r.image,
              'desc': r.desc,
              'time': r.time,
              'people': r.people,
              'tags': r.tags,
              'ingredients': r.ingredients,
              'steps': r.steps,
              'difficulty': r.difficulty,
              'duration_note': r.durationNote,
            },
          )
          .toList(),
    );
    _pending = _pending.then((_) async {
      try {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString(key, raw);
      } catch (_) {}
    });
    notifyListeners();
  }

  Future<void> flush() => _pending;
  @override
  void dispose() {
    if (_wired) AuthStore.instance.removeListener(_accountChanged);
    super.dispose();
  }
}
