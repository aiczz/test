// 定位入口。
//
// 真正的实现在 geolocation_web.dart（Web）或 geolocation_stub.dart（其他平台）。
//
// 为什么要条件导入：package:web 依赖 dart:js_interop，在原生平台编译不过，
// 所以不能无条件 import。
//
// 用法：
//   final coords = await currentCoordinates();
//   if (coords != null) CityStore.instance.selectByCoordinates(coords.$1, coords.$2);

export 'geolocation_stub.dart'
    if (dart.library.js_interop) 'geolocation_web.dart';
