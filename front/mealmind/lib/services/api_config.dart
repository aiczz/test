// 后端连接配置与可用性探测。
//
// 为什么需要「探测」而不是一个写死的开关：
//   线上 PWA（github.io）是没有后端的，本地演示时才起 uvicorn。
//   写死 useMock，两种场景总有一个是坏的。
//   所以启动时探测一次 /api/health：
//     通了 → 用真后端
//     不通 → 静默降级到本地假数据，界面照常能用，不弹错误
//
// ⚠️ 浏览器会拦截 HTTPS 页面发起的 http:// 请求（mixed content），
//    所以**线上 PWA 永远连不上你本机的后端** —— 这是浏览器限制，不是 bug。
//    要演示前后端打通，请用 `flutter run -d chrome`（本地 http）
//    或者打包成 APK（原生 App 不受 mixed content 限制）。

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// 后端地址。
///
/// - **Android 模拟器**：必须用 `10.0.2.2` —— 模拟器里的 127.0.0.1 指模拟器自己
/// - **Web / 桌面**：`127.0.0.1`
/// - **Android 真机**：改成电脑的局域网 IP，如 `http://192.168.1.5:8000`
///   （电脑上 `ipconfig` 查 IPv4；手机和电脑连同一个 WiFi）
String get defaultApiBase {
  if (kIsWeb) return 'http://127.0.0.1:8000';
  if (defaultTargetPlatform == TargetPlatform.android) {
    return 'http://10.0.2.2:8000';
  }
  return 'http://127.0.0.1:8000';
}

/// 后端的可达状态。全局单例，启动时探测一次。
class BackendStatus extends ChangeNotifier {
  BackendStatus._();

  static final BackendStatus instance = BackendStatus._();

  String apiBase = defaultApiBase;

  bool _online = false;
  bool _probed = false;
  String? _lastError;

  /// 后端是否可用。false 时界面走本地假数据。
  bool get online => _online;

  /// 是否已经探测过（避免界面上出现"未知"状态闪烁）
  bool get probed => _probed;

  String? get lastError => _lastError;

  /// 探测后端。超时设得很短 —— 连不上是正常情况，不该让用户干等。
  Future<bool> probe({String? base}) async {
    if (base != null && base.isNotEmpty) apiBase = base;

    final dio = Dio(
      BaseOptions(
        baseUrl: apiBase,
        connectTimeout: const Duration(seconds: 2),
        receiveTimeout: const Duration(seconds: 2),
      ),
    );

    try {
      final res = await dio.get<Map<String, dynamic>>('/api/health');
      _online = res.statusCode == 200;
      _lastError = null;
    } on DioException catch (e) {
      _online = false;
      _lastError = e.message;
    } finally {
      dio.close();
    }

    _probed = true;
    notifyListeners();
    return _online;
  }
}
