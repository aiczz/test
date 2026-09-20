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

  /// 是不是管理员 —— 决定「我的」页要不要显示控制台入口。
  /// ⚠️ 这只是【界面】上的开关，真正的权限校验在后端：
  ///    管理员接口对普通用户返回 403，前端改这个值也没用。
  final bool isAdmin;

  const AuthUser({
    required this.id,
    required this.username,
    this.nickname,
    this.familySize = 3,
    this.isAdmin = false,
  });

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
    id: json['id'] as int? ?? 0,
    username: json['username'] as String? ?? '',
    nickname: json['nickname'] as String?,
    familySize: json['family_size'] as int? ?? 3,
    isAdmin: json['is_admin'] as bool? ?? false,
  );

  Map<String, dynamic> toJson() => <String, dynamic>{
    'id': id,
    'username': username,
    'nickname': nickname,
    'family_size': familySize,
    'is_admin': isAdmin,
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
  static const String _kRegisteredPhones = 'registered_phones';

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

  /// 用后端刷新当前用户信息。
  ///
  /// ★ 为什么必须有这一步：本地缓存的用户 JSON 可能是【旧版本】写下的。
  ///   `is_admin` 就是后加的字段 —— 老缓存里没它，读出来是 false，
  ///   结果管理员明明登录着却看不到「管理」入口。
  ///   启动时刷一次，旧缓存就能自愈，不用让用户手动退出重登。
  Future<void> refreshUser() async {
    final token = _token;
    if (token == null) return;
    try {
      final fresh = await _fetchMe(token);
      await _persist(token, fresh);
    } catch (_) {
      // 后端不在线、token 过期都先不管 ——
      // 真正调接口时后端会返回 401，那时再处理
    }
  }

  Future<void> _persist(String token, AuthUser user) async {
    _token = token;
    _user = user;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kToken, token);
    await prefs.setString(_kUser, jsonEncode(user.toJson()));
    notifyListeners();
  }

  /// 用演示账号登录 —— 公网静态演示没有后端时也必须能进入应用。
  Future<void> loginAsDemo() async {
    if (BackendStatus.instance.online) {
      await login(demoUsername, demoPassword);
      return;
    }
    await _persist(
      'local-demo-token',
      const AuthUser(id: 0, username: demoUsername, nickname: '演示用户'),
    );
  }

  String _normalizePhone(String phone) => phone.replaceAll(RegExp(r'\s+'), '');

  void _validatePhoneCode(String phone, String code) {
    if (!RegExp(r'^1\d{10}$').hasMatch(phone)) {
      throw const AuthException('请输入正确的 11 位手机号');
    }
    if (code != '123456') {
      throw const AuthException('验证码不正确，请输入 123456');
    }
  }

  /// 手机验证码注册。注册成功只保存账号，不自动登录。
  Future<void> registerPhone(String phone, String code) async {
    final normalized = _normalizePhone(phone);
    _validatePhoneCode(normalized, code);
    final prefs = await SharedPreferences.getInstance();
    final phones = prefs.getStringList(_kRegisteredPhones) ?? <String>[];
    if (phones.contains(normalized)) {
      throw const AuthException('该手机号已经注册，请直接登录');
    }
    await prefs.setStringList(_kRegisteredPhones, <String>[
      ...phones,
      normalized,
    ]);
  }

  /// 手机验证码登录的本地演示闭环。
  ///
  /// 当前仓库没有短信供应商配置，公网静态站也没有可用的认证后端，
  /// 因此先用固定演示码完成可操作流程。接入真实短信服务后，只需把这里
  /// 替换为 `/api/auth/sms/login` 请求，登录页本身无需改动。
  Future<void> loginWithPhone(String phone, String code) async {
    final normalized = _normalizePhone(phone);
    _validatePhoneCode(normalized, code);
    final prefs = await SharedPreferences.getInstance();
    final phones = prefs.getStringList(_kRegisteredPhones) ?? <String>[];
    if (!phones.contains(normalized)) {
      throw const AuthException('该手机号还没有注册，请先完成注册');
    }

    final suffix = normalized.substring(normalized.length - 4);
    await _persist(
      'demo-phone-$normalized',
      AuthUser(
        id: normalized.hashCode & 0x7fffffff,
        username: 'phone_$suffix',
        nickname: '用户$suffix',
      ),
    );
  }

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

  /// 注册账号。注册成功后仍需回到登录页完成登录。
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
  }

  Future<AuthUser> _fetchMe(String token) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/api/auth/me',
      options: Options(
        headers: <String, String>{'Authorization': 'Bearer $token'},
      ),
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
  Map<String, String> get authHeaders => _token == null
      ? const <String, String>{}
      : <String, String>{'Authorization': 'Bearer $_token'};

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
