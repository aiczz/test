// 首页推荐流：从后端拿「算法 + AI」算出来的今日推荐。
//
// 【为什么单独一层，而不塞进 ContentStore】
// ContentStore 管的是「内容库」（590 食材 / 10000 菜谱，全 App 共用，变化很慢）。
// 首页推荐是**每天、每地区、每份家庭档案都会变**的东西，生命周期完全不同：
//   换城市 → 要重算
//   改忌口 / 人数 / 可用时间 → 要重算
//   跨天 → 要重算（后端按日期轮换，同地区同一天所有人一致）
// 混在一起会让「内容库」被频繁无谓地重新拉取。
//
// 【降级策略】
// 后端不在线、或者这次请求失败 —— feed 保持为 null，
// 首页会退回本地那套 pickForHome()（纯规则），界面照常能用、不弹错误。
// 这和项目里其它地方的「静默降级」是同一个口径。
//
// ⚠️ 一个真实踩过的坑：换城市后推荐不跟着变。
//    原因有两个，都在这儿修掉了：
//      1. 监听器原先是在 main.dart 的 _prepare() 里注册的 —— 只要那一步有任何
//         意外，**监听就永远不会挂上**，换城市只改了顶部的标签、数据一动不动，
//         而且完全没有报错。现在改成在自己的 load() 里自挂（幂等）。
//      2. 正在请求时又换了城市，第二次请求被 `if (_loading) return;` 丢掉，
//         界面就停在**上一个城市**的数据上不再更新。现在会记一个「待重算」
//         标记，当前请求结束后自动按最新城市再算一次。

import 'package:flutter/foundation.dart';

import '../models/ai_feed.dart';
import '../services/api_config.dart';
import '../services/backend_api.dart';
import '../services/city.dart';
import 'app_state.dart';

class HomeFeedStore extends ChangeNotifier {
  HomeFeedStore._();

  static final HomeFeedStore instance = HomeFeedStore._();

  HomeFeed? _feed;
  bool _loading = false;
  String? _lastError;
  bool _reloadQueued = false;
  bool _wired = false;

  /// 正在为哪个城市计算（界面用它显示「正在按 XX 重新计算…」）
  String? _loadingRegion;

  /// 上一次加载用的签名（城市 + 档案 + 日期）。
  /// 签名没变就不重复打接口 —— 首页会被频繁重建，不设这道闸会打爆后端。
  String _signature = '';

  HomeFeed? get feed => _feed;
  bool get loading => _loading;
  String? get loadingRegion => _loadingRegion;
  String? get lastError => _lastError;

  /// 后端的推荐是否可用。false 时首页走本地规则。
  bool get hasFeed => _feed != null;

  /// 这份推荐是哪个地区的（界面上如实标注 —— 换城市时一眼能看出变没变）
  String? get region => _feed?.region;

  /// 把「城市变了 / 档案变了」接到自己身上。
  ///
  /// 以前是 main.dart 启动流程里注册的 —— 那样一旦启动流程有意外，
  /// 这个监听就静默失效（换城市完全没反应，还不报错）。
  /// 改成自己挂，幂等，谁先调用都不会重复。
  void _wire() {
    if (_wired) return;
    _wired = true;
    CityStore.instance.addListener(refreshIfStale);
    AppState.instance.addListener(refreshIfStale);
  }

  String _signatureFor(String city, FamilyProfile profile) {
    final avoid = (profile.avoid.toList()..sort()).join(',');
    final prefs = (profile.preferences.toList()..sort()).join(',');
    return [
      city,
      DateTime.now().toIso8601String().substring(0, 10),
      profile.people,
      profile.cookMinutes,
      profile.lowSodium,
      avoid,
      prefs,
    ].join('|');
  }

  /// 按当前城市与家庭档案加载首页推荐。
  ///
  /// [force] 为 true 时会忽略签名、强制重算（下拉刷新 / 演示时用）。
  Future<void> load({bool force = false}) async {
    _wire();

    if (!BackendStatus.instance.online) {
      // 后端不在线：清掉旧 feed，首页退回本地规则
      if (_feed != null) {
        _feed = null;
        notifyListeners();
      }
      return;
    }

    final profile = AppState.instance.profile;
    final city = CityStore.instance.city;
    final signature = _signatureFor(city.name, profile);

    if (!force && signature == _signature && _feed != null) return;

    if (_loading) {
      // 正在为**别的**输入计算 —— 别丢掉这次变化：
      // 标记一下，等当前这次结束立刻按最新的城市/档案再算一遍。
      _reloadQueued = true;
      return;
    }

    _loading = true;
    _loadingRegion = city.name;
    notifyListeners();

    try {
      final feed = await BackendApi.instance.fetchHomeFeed(
        city: city.name,
        lat: city.lat,
        lon: city.lng,
        people: profile.people,
        cookMinutes: profile.cookMinutes,
        lowSodium: profile.lowSodium,
        preferences: profile.preferences.toList(),
        avoid: profile.avoid.toList(),
      );
      _feed = feed;
      _signature = signature;
      _lastError = null;
    } catch (error) {
      // 静默降级：保留上一份 feed（比空白好），但记下错误便于排查
      debugPrint('[HomeFeedStore] 首页推荐加载失败，改用本地规则：$error');
      _lastError = '$error';
      // ⚠️ 失败也要更新签名 —— 否则每次重建都会重试同一个失败请求，
      //    首页会变成「一直在转圈」。用户主动换城市/改档案时签名会变，
      //    那时自然会再试一次。
      _signature = signature;
    } finally {
      _loading = false;
      _loadingRegion = null;
      notifyListeners();

      if (_reloadQueued) {
        _reloadQueued = false;
        // 用 microtask 而不是直接 await：避免在 notifyListeners 的同步回调链里
        // 立刻递归进 load，把一次 UI 通知拖成一串同步重入。
        Future<void>.microtask(load);
      }
    }
  }

  /// 换城市 / 改档案后调用。签名变了才会真的发请求。
  Future<void> refreshIfStale() => load();

  void clear() {
    _feed = null;
    _signature = '';
    notifyListeners();
  }
}
