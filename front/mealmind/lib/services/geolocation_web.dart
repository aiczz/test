// Web 平台的浏览器定位实现。
//
// ⚠️ 只在 Web 编译 —— package:web 用了 dart:js_interop，原生平台编译不过，
//    所以必须通过 geolocation.dart 的条件导入进来。
//
// 注意：浏览器只在【安全上下文】下给定位。
//   https://  ✓（线上 PWA 可以）
//   http://localhost ✓（Chrome 把 localhost 当安全上下文）
//   http://192.168.x.x ✗（局域网 IP 拿不到定位 —— 真机演示时手动选城市）

import 'dart:async';
import 'dart:js_interop';

import 'package:web/web.dart' as web;

bool get supportsBrowserGeolocation => true;

String get geolocationUnsupportedHint => '浏览器没有返回位置，请手动选择城市';

/// 浏览器定位。用户拒绝授权 / 超时 / 浏览器不支持，一律返回 null。
Future<(double, double)?> currentCoordinates() async {
  final completer = Completer<(double, double)?>();

  void finish((double, double)? value) {
    if (!completer.isCompleted) completer.complete(value);
  }

  try {
    web.window.navigator.geolocation.getCurrentPosition(
      ((web.GeolocationPosition position) {
        finish((
          position.coords.latitude.toDouble(),
          position.coords.longitude.toDouble(),
        ));
      }).toJS,
      ((web.GeolocationPositionError _) => finish(null)).toJS,
    );
  } catch (_) {
    return null;
  }

  // 浏览器没有可靠的回调保证，自己加一道兜底 —— 否则用户可能永远看着转圈
  return completer.future.timeout(
    const Duration(seconds: 10),
    onTimeout: () => null,
  );
}
