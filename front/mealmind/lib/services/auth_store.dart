// 登录状态 + token 持久化。
//
// 和 `state/app_state.dart` 一个路子：零第三方状态管理框架，
// 用 Flutter 自带的 ChangeNotifier + 全局单例。

import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_config.dart';

/// 当前登录的用户。
@immutable
class AuthUser {
  final int id;
  final String username;
  final String? nickname;
  final int familySize;

  const AuthUser({
    required this.id,
    required this.username,
    this.nickname,
    this.familySize = 3,
  });

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
    id: json['id'] as int? ?? 0,
    username: json['username'] as String? ?? '',
    nickname: json['nickname'] as String?,
    familySize: json['family_size'] as int? ?? 3,
  );

  Map<String, dynamic> toJson() => <String, dynamic>{
    'id': id,
    'username': username,
    'nickname': nickname,
    'family_size': familySize,
  };

  String get displayName =>
      (nickname == null || nickname!.isEmpty) ? username : nickname!;
}

/// 登录失败时抛这个，`message` 直接就是给用户看的中文提示。
class AuthException implements Exception {
  final String message;

  const AuthException(this.message);

  @override
  String toString() => message;
}

class AuthStore extends ChangeNotifier {
  AuthStore._();

  static final AuthStore instance = AuthStore._();

  // 演示账号 —— 答辩时评委不用注册就能进
  static const String demoUsername = 'demo';
  static const String demoPassword = 'shishi2026';

  static const String _kToken = 'auth_token';
  static const String _kUser = 'auth_user';

  String? _token;
  AuthUser? _user;
  bool _restored = false;

  String? get token => _token;
  AuthUser? get user => _user;

  /// 是否已经从本地存储恢复过（避免启动瞬间误判成"未登录"）
  bool get restored => _restored;

  bool get isLoggedIn => _token != null && _user != null;

  Dio get _dio => Dio(
    BaseOptions(
      baseUrl: BackendStatus.instance.apiBase,
      connectTimeout: const Duration(seconds: 8),
      receiveTimeout: const Duration(seconds: 8),
      sendTimeout: const Duration(seconds: 8),
      contentType: 'application/json; charset=utf-8',
    ),
  );

  /// 启动时从本地恢复登录状态。token 过期不在这里校验 ——
  /// 等真正调接口时后端返回 401，那时再清理。
  Future<void> restore() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString(_kToken);
    final rawUser = prefs.getString(_kUser);

    if (token != null && rawUser != null) {
      try {
        _token = token;
        _user = AuthUser.fromJson(jsonDecode(rawUser) as Map<String, dynamic>);
      } catch (_) {
        // 本地数据坏了就当没登录，不要让 App 起不来
        await logout();
      }
    }
    _restored = true;
    notifyListeners();
  }

  Future<void> _persist(String token, AuthUser user) async {
    _token = token;
    _user = user;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kToken, token);
    await prefs.setString(_kUser, jsonEncode(user.toJson()));
    notifyListeners();
  }

  /// 用演示账号登录 —— 「一键」就是这个。
  Future<void> loginAsDemo() => login(demoUsername, demoPassword);

  /// 登录。失败抛 [AuthException]。
  Future<void> login(String username, String password) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/api/auth/login',
        data: <String, dynamic>{'username': username, 'password': password},
      );
      final token = res.data?['access_token'] as String?;
      if (token == null || token.isEmpty) {
        throw const AuthException('登录失败：接口没有返回 token');
      }
      await _persist(token, await _fetchMe(token));
    } on DioException catch (e) {
      throw _toAuthException(e);
    }
  }

  /// 注册。成功后直接登录，不让用户再输一遍。
  Future<void> register(
    String username,
    String password, {
    int familySize = 3,
  }) async {
    try {
      await _dio.post<Map<String, dynamic>>(
        '/api/auth/register',
        data: <String, dynamic>{
          'username': username,
          'password': password,
          'family_size': familySize,
        },
      );
    } on DioException catch (e) {
      throw _toAuthException(e);
    }
    await login(username, password);
  }

  Future<AuthUser> _fetchMe(String token) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/api/auth/me',
      options: Options(headers: <String, String>{'Authorization': 'Bearer $token'}),
    );
    final data = res.data;
    if (data == null) throw const AuthException('取用户信息失败');
    return AuthUser.fromJson(data);
  }

  /// 退出登录：清掉本地 token。后端是无状态的 JWT，不需要额外通知。
  Future<void> logout() async {
    _token = null;
    _user = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kToken);
    await prefs.remove(_kUser);
    notifyListeners();
  }

  /// 带 token 的请求头。别的接口层要用。
  Map<String, String> get authHeaders =>
      _token == null ? const <String, String>{} : <String, String>{'Authorization': 'Bearer $_token'};

  /// 把 DioException 翻译成用户看得懂的中文。
  AuthException _toAuthException(DioException e) {
    final body = e.response?.data;
    if (body is Map && body['detail'] is String) {
      return AuthException(body['detail'] as String);
    }

    final code = e.response?.statusCode;
    if (code == 401) return const AuthException('用户名或密码不正确');
    if (code == 409) return const AuthException('用户名已被占用');
    if (code == 422) return const AuthException('请检查输入（用户名至少 2 位，密码至少 6 位）');

    if (code == null) {
      // 连不上后端是本地演示最常见的情况，提示要能直接照着做
      return AuthException(
        '连不上后端（${BackendStatus.instance.apiBase}）。\n'
        '先在 back/ 目录启动服务：\n'
        'python -m uvicorn app.main:app --port 8000',
      );
    }
    return AuthException('请求失败（$code）');
  }
}
