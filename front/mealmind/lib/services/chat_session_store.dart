import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Structured constraints only, scoped by account and backend; no chat text.
class ChatSessionStore {
  static String storageKey(String scope) =>
      'ai_session_v1_${Uri.encodeComponent(scope)}';

  static Future<Map<String, dynamic>?> load(String scope) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(storageKey(scope));
    if (raw == null) return null;
    try {
      return jsonDecode(raw) as Map<String, dynamic>;
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }

  static Future<void> save(String scope, Map<String, dynamic> value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(storageKey(scope), jsonEncode(value));
  }

  static Future<void> clear(String scope) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(storageKey(scope));
  }
}
