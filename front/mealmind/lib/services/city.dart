// 城市列表与当前选择。
//
// 为什么是内置城市表，而不是真实 GPS 逆地理编码：
//   逆地理编码（经纬度 → 城市名）要接地图 API（高德/百度/Google），
//   得申请 key。而后端的时令数据只到【全国】级（food_seasons.region
//   目前全是 national），城市名只用于顶部显示和 /api/home?region=xxx
//   这个参数，所以内置一张常用城市表就够了。
//
// 浏览器定位只用来【推荐】最近的城市（按经纬度粗匹配），不做逆编码 ——
// 所以即使定位失败，用户手动选一下也能用。

import 'package:flutter/foundation.dart';

@immutable
class City {
  final String name;
  final double lat;
  final double lng;

  const City(this.name, this.lat, this.lng);
}

/// 内置城市表（带坐标，供定位粗匹配用）。
/// 按经纬度算平方距离就够挑了 —— 不需要真的球面距离。
const List<City> kCities = <City>[
  City('北京', 39.90, 116.41),
  City('上海', 31.23, 121.47),
  City('广州', 23.13, 113.26),
  City('深圳', 22.54, 114.06),
  City('杭州', 30.27, 120.16),
  City('南京', 32.06, 118.80),
  City('苏州', 31.30, 120.58),
  City('成都', 30.57, 104.07),
  City('重庆', 29.56, 106.55),
  City('武汉', 30.59, 114.31),
  City('西安', 34.34, 108.94),
  City('长沙', 28.23, 112.94),
  City('青岛', 36.07, 120.38),
  City('天津', 39.08, 117.20),
  City('郑州', 34.75, 113.63),
  City('沈阳', 41.81, 123.43),
];

/// 默认城市 —— 和之前的写死值保持一致，改之前界面什么样还是什么样
const String kDefaultCityName = '杭州';

City defaultCity() => kCities.firstWhere(
  (city) => city.name == kDefaultCityName,
  orElse: () => kCities.first,
);

/// 按经纬度找最近的城市
City nearestCity(double latitude, double longitude) {
  City best = kCities.first;
  double bestScore = double.infinity;
  for (final city in kCities) {
    final dLat = city.lat - latitude;
    final dLng = city.lng - longitude;
    // 只比大小，不用开根号
    final score = dLat * dLat + dLng * dLng;
    if (score < bestScore) {
      bestScore = score;
      best = city;
    }
  }
  return best;
}

/// 当前选中的城市。全局单例，和 AppState / AuthStore 一个路子。
class CityStore extends ChangeNotifier {
  CityStore._();

  static final CityStore instance = CityStore._();

  City _city = defaultCity();
  bool _autoDetected = false;
  bool _detecting = false;
  String? _detectError;

  City get city => _city;

  /// 是不是靠定位自动选的（界面上如实说明，不假装）
  bool get autoDetected => _autoDetected;
  bool get detecting => _detecting;
  String? get detectError => _detectError;

  /// 手动选城市
  void select(City city) {
    _autoDetected = false;
    _detectError = null;
    // ★ 一定要复位：不复位的话「用当前位置」按钮会永远停在禁用状态
    _detecting = false;
    if (_city.name == city.name) {
      notifyListeners();
      return;
    }
    _city = city;
    notifyListeners();
  }

  /// 用经纬度把城市设成最近的那个（定位成功后调）
  void selectByCoordinates(double latitude, double longitude) {
    final nearest = nearestCity(latitude, longitude);
    _autoDetected = true;
    _detectError = null;
    // ★ 这里以前漏了复位，导致「定位只能成功一次」：
    //   第一次成功后 _detecting 一直是 true，按钮保持禁用，
    //   用户再点就没反应（看着像「定位半天没反应」）。
    _detecting = false;
    _city = nearest;
    notifyListeners();
  }

  void setDetecting(bool value) {
    _detecting = value;
    notifyListeners();
  }

  void setDetectError(String? message) {
    _detecting = false;
    _detectError = message;
    notifyListeners();
  }
}
