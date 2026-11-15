import 'package:dio/dio.dart';

import 'api_config.dart';
import 'auth_store.dart';

/// Shared cache across cards and detail sheets, isolated by backend and login.
class ImageStore {
  static final _cache =
      <String, ({DateTime expires, Map<String, dynamic> data})>{};
  static final _pending = <String, Future<Map<String, dynamic>>>{};

  static Future<Map<String, dynamic>> resolve(String kind, String name) {
    final key =
        '${BackendStatus.instance.apiBase}|${AuthStore.instance.isLoggedIn}|$kind|$name';
    final cached = _cache[key];
    if (cached != null && cached.expires.isAfter(DateTime.now())) {
      return Future.value(cached.data);
    }
    return _pending.putIfAbsent(key, () => _fetch(kind, name, key));
  }

  static Future<Map<String, dynamic>> _fetch(
    String kind,
    String name,
    String key,
  ) async {
    final dio = createApiDio();
    try {
      final response = await dio.post<Map<String, dynamic>>(
        '/api/images/resolve',
        data: {'kind': kind, 'name': name},
        options: Options(headers: AuthStore.instance.authHeaders),
      );
      final data = response.data ?? <String, dynamic>{};
      final seconds = data['status'] == 'ready'
          ? 3600
          : data['status'] == 'generating'
          ? 3
          : 30;
      _cache[key] = (
        expires: DateTime.now().add(Duration(seconds: seconds)),
        data: data,
      );
      return data;
    } catch (_) {
      final data = <String, dynamic>{'status': 'unavailable'};
      _cache[key] = (
        expires: DateTime.now().add(const Duration(seconds: 20)),
        data: data,
      );
      return data;
    } finally {
      dio.close();
      _pending.remove(key);
    }
  }
}
