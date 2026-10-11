// 登录状态 + token 持久化。
//
// 和 `state/app_state.dart` 一个路子：零第三方状态管理框架，
// 用 Flutter 自带的 ChangeNotifier + 全局单例。

import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../state/app_state.dart';
import '../state/today_menu.dart';
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
  static const String _kPhonePasswordHashes = 'phone_password_hashes';

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

  /// 一次性提示，由登录页取走后清空。两种来源：
  ///   · 登录失效（token 过期 / 账号被封禁，见 [expireSession]）
  ///   · 注销成功（见 [deleteAccount]）
  /// 两者都是「界面已经切回登录页了，但用户需要知道刚才发生了什么」。
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
  //
  // 测试可以先用 [debugUseDio] 换掉它 —— 注销是真删，用例不能真连后端。
  Dio get _dio => _debugDio ?? createApiDio();

  Dio? _debugDio;

  @visibleForTesting
  void debugUseDio(Dio? dio) => _debugDio = dio;

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

  String _localPasswordHash(String phone, String password) => sha256
      .convert(utf8.encode('shishi-local-v1:$phone:$password'))
      .toString();

  void _validatePhoneCode(String phone, String code) {
    if (!RegExp(r'^1\d{10}$').hasMatch(phone)) {
      throw const AuthException('请输入正确的 11 位手机号');
    }
    if (code != '123456') {
      throw const AuthException('验证码不正确，请输入 123456');
    }
  }

  /// 手机验证码注册。注册成功只保存账号，不自动登录。
  Future<void> registerPhone(String phone, String code, String password) async {
    final normalized = _normalizePhone(phone);
    _validatePhoneCode(normalized, code);
    if (BackendStatus.instance.online) {
      try {
        await _dio.post<Map<String, dynamic>>(
          '/api/auth/sms/register',
          data: <String, dynamic>{
            'phone': normalized,
            'code': code,
            'password': password,
          },
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
    final storedHashes = prefs.getString(_kPhonePasswordHashes);
    final hashes = storedHashes == null
        ? <String, dynamic>{}
        : jsonDecode(storedHashes) as Map<String, dynamic>;
    hashes[normalized] = _localPasswordHash(normalized, password);
    await prefs.setString(_kPhonePasswordHashes, jsonEncode(hashes));
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

  // ---------------------------------------------------------------- 邮箱验证码
  //
  // 这条路是【真的】：验证码由后端随机生成，有 5 分钟有效期、60 秒重发间隔、
  // 每小时上限，校验失败次数封顶，用掉即作废（防重放）。码通过邮件下发
  // （后端 mail_backend=smtp 时真发邮件；没配则只打到服务日志）。
  //
  // 离线时【不】提供本地闭环 —— 收不到邮件就是收不到，假装能过没有意义。

  static final RegExp _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

  bool _isEmail(String email) => _emailPattern.hasMatch(email);

  String _normalizeEmail(String email) => email.trim().toLowerCase();

  void _requireOnlineForEmail() {
    if (!BackendStatus.instance.online) {
      throw const AuthException('邮箱验证码需要连接后端，当前是离线演示模式');
    }
  }

  /// 请求发送邮箱验证码，返回后端实际用的通道（smtp / console）。
  Future<String> sendEmailCode(
    String email, {
    String purpose = 'register',
  }) async {
    final normalized = _normalizeEmail(email);
    if (!_isEmail(normalized)) {
      throw const AuthException('请输入正确的邮箱地址');
    }
    _requireOnlineForEmail();
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/api/auth/email/send-code',
        data: <String, dynamic>{'email': normalized, 'purpose': purpose},
      );
      return res.data?['channel']?.toString() ?? 'console';
    } on DioException catch (e) {
      throw _toAuthException(e);
    }
  }

  /// 邮箱验证码注册。注册成功只建账号，不自动登录。
  Future<void> registerEmail(String email, String code, String password) async {
    final normalized = _normalizeEmail(email);
    if (!_isEmail(normalized)) {
      throw const AuthException('请输入正确的邮箱地址');
    }
    _requireOnlineForEmail();
    try {
      await _dio.post<Map<String, dynamic>>(
        '/api/auth/email/register',
        data: <String, dynamic>{
          'email': normalized,
          'code': code,
          'password': password,
        },
      );
    } on DioException catch (e) {
      throw _toAuthException(e);
    }
  }

  /// 邮箱验证码登录。
  Future<void> loginWithEmail(String email, String code) async {
    final normalized = _normalizeEmail(email);
    if (!_isEmail(normalized)) {
      throw const AuthException('请输入正确的邮箱地址');
    }
    _requireOnlineForEmail();
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/api/auth/email/login',
        data: <String, dynamic>{'email': normalized, 'code': code},
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
      final normalized = _normalizePhone(username);
      final prefs = await SharedPreferences.getInstance();
      final storedHashes = prefs.getString(_kPhonePasswordHashes);
      if (storedHashes != null && RegExp(r'^1\d{10}$').hasMatch(normalized)) {
        final hashes = jsonDecode(storedHashes) as Map<String, dynamic>;
        if (hashes[normalized] == _localPasswordHash(normalized, password)) {
          final suffix = normalized.substring(normalized.length - 4);
          await _persist(
            '$phoneTokenPrefix$normalized',
            AuthUser(
              id: normalized.hashCode & 0x7fffffff,
              username: normalized,
              nickname: '用户$suffix',
            ),
          );
          return;
        }
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

  /// 注销账号：让后端【真正删掉】这个人和他名下的全部数据，然后就地退登。
  ///
  /// 和 [logout] 的区别是量级：logout 只是本机退出，换台设备登录数据还在；
  /// 这个是服务端的收藏 / 菜单 / 购物清单 / 口味偏好**一并消失，不可恢复**。
  /// 所以调用方必须先做二次确认（见 profile.dart 的注销弹窗），
  /// 这个函数只负责「把请求发出去、把后端的话原样带回来」。
  ///
  /// 失败一律抛 [AuthException]，`message` 就是后端的 detail。管理员 / 演示
  /// 账号会拿到 403 —— 那句说明必须原样透出去：用户得知道「不是我操作错了，
  /// 是这类账号不让自助注销」，自己编一句「注销失败」只会让人反复重试。
  ///
  /// 成功后调 [logout]：服务端已经没有这个人了，本地再留着 token 只会让
  /// App 停在一个「显示着已登录、调什么接口都 401」的状态。
  Future<void> deleteAccount() async {
    final token = _token;
    if (token == null) {
      throw const AuthException('未登录，无法注销账号');
    }

    try {
      await _dio.delete<void>(
        '/api/auth/me',
        options: Options(
          headers: <String, String>{'Authorization': 'Bearer $token'},
        ),
      );
    } on DioException catch (e) {
      throw _toAuthException(e);
    }

    // 注销会连同门禁一起把界面切回登录页。登录页只显示 [notice]，
    // 不留一句话的话，用户看到的就是「点了确认，然后莫名其妙回到登录页」——
    // 到底删成功没有，只能靠猜。
    _notice = '账号已注销，你的数据已经永久删除';

    // 服务端删干净了，本机也得跟上：只清 token 的话，上一个人的家庭档案
    // 还躺在这台设备上 —— 换另一个账号登进来就会看到别人的家庭人数和忌口，
    // 而且那份残留还会在保存时被推给新账号。
    //
    // ★ 顺序是刻意的，必须在 logout() **之前**清：logout() 一返回，登录门禁
    //   就会把登录页带出来，用户下一秒就可能用另一个账号登进去 —— 那时
    //   AppState.load() 会先读本机缓存，读到的还是上一个人的档案。
    await AppState.instance.clearLocalCache();
    // 今日菜单（用户一道道挑进来的菜）同样是个人数据。它单独一个 store、
    // 只活在内存里，所以不跟着 AppState 走，得单独清一次。
    TodayMenuStore.instance.clear();

    await logout();
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
    if (code == 422) {
      return const AuthException('请检查输入（密码须为不少于 6 位的数字）');
    }

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
