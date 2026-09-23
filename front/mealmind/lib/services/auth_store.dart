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

  // 管理后台演示账号。后端在线时使用数据库中的同名种子账号；
  // GitHub Pages 没有后端时，只创建本机浏览器内的演示管理员会话。
  static const String adminUsername = 'admin';
  static const String adminPassword = 'admin123456';

  static const String _kToken = 'auth_token';
  static const String _kUser = 'auth_user';
  static const String _kRegisteredPhones = 'registered_phones';

  /// 后端离线时「演示账号一键登录」写的假 token。
  /// 它能让登录门禁放行，但后端不认 —— 见 [isOfflineDemo]。
  static const String offlineDemoToken = 'local-demo-token';

  /// 手机号登录写的假 token 前缀（这套流程目前是纯前端本地闭环）。
  static const String phoneTokenPrefix = 'demo-phone-';

  /// 后端离线时用 admin 账号登录写的假 token（见 [login] 的离线分支）。
  static const String localAdminToken = 'local-admin-token';

  String? _token;
  AuthUser? _user;
  bool _restored = false;

  /// 一次性提示（目前用于「登录已失效」），由登录页取走后清空。
  String? _notice;

  String? get token => _token;
  AuthUser? get user => _user;

  /// 是否已经从本地存储恢复过（避免启动瞬间误判成"未登录"）
  bool get restored => _restored;

  bool get isLoggedIn => _token != null && _user != null;

  /// 给登录页看的一次性提示。取走后请调用 [clearNotice]。
  String? get notice => _notice;

  void clearNotice() => _notice = null;

  /// 当前登录是不是「后端不认的本地演示登录」。
  ///
  /// 三种情况会写这种 token：
  ///   1. 后端离线时点「演示账号一键登录」—— 公网静态站永远走这条
  ///   2. 手机号验证码登录 —— 这套流程目前是纯前端本地闭环，后端没有对应接口
  ///   3. 后端离线时用 admin 账号登录 —— 同上，只在浏览器里造一个演示管理员会话
  ///
  /// 这类会话能进 App，但**所有需要登录的接口都会 401**：收藏数、我的食材、
  /// 管理后台全是空的。所以界面必须如实标注，不能让用户以为数据被保存了。
  bool get isOfflineDemo =>
      _token == offlineDemoToken ||
      _token == localAdminToken ||
      (_token?.startsWith(phoneTokenPrefix) ?? false);

  /// token 失效（过期 / 账号被封禁）时调用：清掉本地登录态，并留一句提示。
  ///
  /// ★ 这是「封禁立刻生效」在前端真正落地的地方。
  ///   后端 `get_current_user*` 对被封禁账号直接返回 401/403，
  ///   但如果没有这一条，用户会停在一个「显示着已登录、却什么都做不了」的状态。
  void expireSession() {
    if (_token == null) return;
    _notice = '登录已失效，请重新登录';
    // 不 await：这里跑在 Dio 拦截器里，不需要等本地存储落盘
    logout();
  }

  // 统一走 createApiDio：它会挂上 401 拦截器。
  // 自己 new 一个 Dio 就会漏掉「封禁 / token 过期」的处理。
  Dio get _dio => createApiDio();

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
    _notice = null; // 登录成功，清掉上一条「登录已失效」
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
      offlineDemoToken,
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
    if (BackendStatus.instance.online) {
      try {
        await _dio.post<Map<String, dynamic>>(
          '/api/auth/sms/register',
          data: <String, dynamic>{'phone': normalized, 'code': code},
        );
        return;
      } on DioException catch (e) {
        throw _toAuthException(e);
      }
    }
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
    if (BackendStatus.instance.online) {
      try {
        final res = await _dio.post<Map<String, dynamic>>(
          '/api/auth/sms/login',
          data: <String, dynamic>{'phone': normalized, 'code': code},
        );
        final token = res.data?['access_token'] as String?;
        if (token == null || token.isEmpty) {
          throw const AuthException('登录失败：接口没有返回 token');
        }
        await _persist(token, await _fetchMe(token));
        return;
      } on DioException catch (e) {
        throw _toAuthException(e);
      }
    }
    final prefs = await SharedPreferences.getInstance();
    final phones = prefs.getStringList(_kRegisteredPhones) ?? <String>[];
    if (!phones.contains(normalized)) {
      throw const AuthException('该手机号还没有注册，请先完成注册');
    }

    final suffix = normalized.substring(normalized.length - 4);
    await _persist(
      '$phoneTokenPrefix$normalized',
      AuthUser(
        id: normalized.hashCode & 0x7fffffff,
        username: 'phone_$suffix',
        nickname: '用户$suffix',
      ),
    );
  }

  /// 登录。失败抛 [AuthException]。
  Future<void> login(String username, String password) async {
    if (!BackendStatus.instance.online) {
      if (username == adminUsername && password == adminPassword) {
        await _persist(
          localAdminToken,
          const AuthUser(
            id: -1,
            username: adminUsername,
            nickname: '食时管理员',
            isAdmin: true,
          ),
        );
        return;
      }
      if (username == demoUsername && password == demoPassword) {
        await loginAsDemo();
        return;
      }
      throw const AuthException('演示站账号不存在或密码不正确');
    }

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

/// 建一个带统一 401 处理的 Dio。
///
/// 为什么必须统一：`/api/my-foods`、`/api/favorites`、`/api/admin/*` 都靠
/// `Authorization` 头。token 一旦失效（过期，或者账号被管理员封禁），后端返回 401。
/// 如果各处自己 catch，就会出现「有的地方清了登录态、有的地方没清」——
/// 用户最终卡在一个「看着已登录、其实什么都做不了」的界面里。
///
/// 现在只有一条路径：任何 401 → [AuthStore.expireSession] → 登录门禁自动回到登录页。
/// 这也正是「封禁立刻生效」在前端真正落地的地方。
Dio createApiDio({
  Duration connectTimeout = const Duration(seconds: 8),
  Duration receiveTimeout = const Duration(seconds: 8),
  Duration? sendTimeout,
}) {
  final dio = Dio(
    BaseOptions(
      baseUrl: BackendStatus.instance.apiBase,
      connectTimeout: connectTimeout,
      receiveTimeout: receiveTimeout,
      sendTimeout: sendTimeout,
      contentType: 'application/json; charset=utf-8',
    ),
  );

  dio.interceptors.add(
    InterceptorsWrapper(
      onError: (DioException error, ErrorInterceptorHandler handler) {
        if (error.response?.statusCode == 401) {
          AuthStore.instance.expireSession();
        }
        handler.next(error);
      },
    ),
  );

  return dio;
}
