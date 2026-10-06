// 后端连接配置与可用性探测。
//
// 为什么需要「探测」而不是一个写死的开关：
//   线上静态站可能没有后端（比如 GitHub Pages 那份），本地演示时才起 uvicorn。
//   写死 useMock，两种场景总有一个是坏的。
//   所以启动时探测 /api/health：
//     通了 → 用真后端
//     不通 → 静默降级到本地假数据，界面照常能用，不弹错误
//
// ★ 本次改动：网页版默认走【同源】，不再把服务器 IP 编进包里。
//
//   为什么必须这么改：以前网页版的后端地址是构建时用
//   `--dart-define=API_BASE=http://8.148.69.56:8000` 写死的。后果是
//   换一台服务器、换个 IP、或者要上域名/HTTPS，都得重新构建一份产物 ——
//   运维拿到源码也跑不起来。现在改成「页面从哪来，就调哪的 /api」，
//   由 nginx 把 /api 反代到后端：
//     · 换 IP / 换域名 / 上 HTTPS —— 都不用重新构建
//     · 天然没有 mixed content（页面和接口同源）
//     · 前端不再需要知道后端在哪个端口
//   部署配置见仓库根的 deploy/ 目录。
//
// ⚠️ APK（原生）**不能**同源 —— 原生应用没有「页面来源」这个概念，
//    必须编译时把绝对地址打进去。所以 build-apk.yml 里那个
//    --dart-define=API_BASE 是必要的，换服务器时要改。

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// 编译期注入的后端地址（可选，优先级最高）。
///
/// 用法：
///     flutter run -d chrome --dart-define=API_BASE=http://127.0.0.1:8020
///     flutter build apk --dart-define=API_BASE=http://8.148.69.56:8000
///
/// 网页版**不传也能用**（走同源）；APK 必须传。
const String _apiBaseOverride = String.fromEnvironment('API_BASE');

/// 当前页面的来源（scheme://host[:port]）。
///
/// 同源部署时，后端就在这个来源的 /api 上。用 `Uri.base` 是 Flutter Web
/// 里拿当前页面地址的标准做法，比在包里写死 IP 稳得多。
String get _pageOrigin {
  if (!kIsWeb) return '';
  final base = Uri.base;
  if (base.scheme != 'http' && base.scheme != 'https') return '';
  if (base.host.isEmpty) return '';
  return base.origin;
}

/// 后端地址的候选列表，**按优先级依次探测，第一个通的就用**。
///
/// 为什么要「列表」而不是一个值：
///   同源部署（生产）和本地开发（flutter run -d chrome 起在随机端口）
///   需要的地址不一样。让探测自己挑，就不必给两种场景各构建一份产物。
List<String> get apiBaseCandidates {
  // 命令行显式指定 —— 只用它，不做任何猜测
  if (_apiBaseOverride.isNotEmpty) return <String>[_apiBaseOverride];

  if (kIsWeb) {
    return <String>[
      // 1) 同源：服务器上用 nginx 把 /api 反代到后端
      if (_pageOrigin.isNotEmpty) _pageOrigin,
      // 2) 本地开发：flutter run -d chrome 起在随机端口，同源拿不到后端，
      //    于是回退到本机 uvicorn 的默认端口
      'http://127.0.0.1:8000',
    ];
  }
  // Android 模拟器：模拟器里的 127.0.0.1 指模拟器自己，必须用 10.0.2.2
  if (defaultTargetPlatform == TargetPlatform.android) {
    return const <String>['http://10.0.2.2:8000'];
  }
  return const <String>['http://127.0.0.1:8000'];
}

/// 首个候选（界面/日志里展示用）。
String get defaultApiBase => apiBaseCandidates.first;

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

  /// 测试需要固定走本地闭环，避免开发机上恰好启动的后端改变测试结果。
  @visibleForTesting
  void setOfflineForTesting() {
    _online = false;
    _probed = true;
    _lastError = null;
  }

  /// 探测后端。超时设得很短 —— 连不上是正常情况，不该让用户干等。
  ///
  /// ★ 会依次试 [apiBaseCandidates]，**第一个通的就锁定为 apiBase**。
  ///   这样同源部署（生产）和本地开发（随机端口）用同一份产物，
  ///   不用为了换地址重新构建。
  Future<bool> probe({String? base}) async {
    final candidates = (base != null && base.isNotEmpty)
        ? <String>[base]
        : apiBaseCandidates;

    for (final candidate in candidates) {
      final dio = Dio(
        BaseOptions(
          baseUrl: candidate,
          connectTimeout: const Duration(seconds: 2),
          receiveTimeout: const Duration(seconds: 2),
        ),
      );
      try {
        // ⚠️ 不能只看 HTTP 200！
        //    Flutter 的 dev server（flutter run -d chrome/edge）对未知路径会
        //    回退返回 index.html —— 也是 200。只看状态码的话，探测会把
        //    「dev server 自己」当成后端锁住，之后所有 /api 请求拿回 HTML，
        //    解析全失败，界面静默退回本地假数据：**看得见界面、看不见 AI**。
        //    所以必须校验它真的返回了我们的健康检查 JSON。
        final res = await dio.get<Map<String, dynamic>>('/api/health');
        final body = res.data;
        final ok = res.statusCode == 200 &&
            body != null &&
            body['status'] == 'ok';
        if (ok) {
          apiBase = candidate;
          _online = true;
          _lastError = null;
          _probed = true;
          notifyListeners();
          return true;
        }
        _lastError = res.statusCode == 200
            ? '返回的不是食时后端（可能是 dev server 的 index.html 回退）'
            : 'HTTP ${res.statusCode}';
      } on DioException catch (e) {
        _lastError = e.message;
      } catch (e) {
        _lastError = '$e';
      } finally {
        dio.close();
      }
    }

    // 全部不通：退回第一个候选，界面走本地假数据（静默降级）
    apiBase = candidates.first;
    _online = false;
    _probed = true;
    notifyListeners();
    return false;
  }

  /// 当前用的是不是同源地址（部署相关的问题排查用）
  bool get sameOrigin =>
      kIsWeb && apiBase.isNotEmpty && apiBase == _pageOrigin;
}
