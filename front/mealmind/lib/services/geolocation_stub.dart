// 非 Web 平台的占位实现。
//
// 原生端（Android / iOS / 桌面）要用真实 GPS，得再加 geolocator 之类的
// 插件（又要开发者模式 + 安卓权限声明）。这一版先不做 ——
// 手动选城市在【所有】平台都能用，只是少了「自动推荐」这一步。

/// 返回 (纬度, 经度)；拿不到返回 null。
Future<(double, double)?> currentCoordinates() async => null;

/// 这个平台支不支持浏览器定位
bool get supportsBrowserGeolocation => false;

/// 不支持时的说明文案
String get geolocationUnsupportedHint => '当前平台不支持自动定位，请手动选择城市';
