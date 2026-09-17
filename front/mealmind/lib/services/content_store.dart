// 内容数据源：后端在线就用后端，否则用本地假数据。
//
// 为什么要有这一层：
//   线上 PWA 没有后端，本地演示有后端。
//   页面如果直接写死 mockFoods，接了后端也看不出来；
//   直接写死后端，线上就白屏。
//   所以页面统一从 ContentStore 读，由它决定数据从哪来。
//
// ⚠️ 降级是【静默】的 —— 后端连不上不弹任何错误，
//    界面照常能用，只是数据来源不同（sourceLabel 会如实说明）。

import 'package:flutter/foundation.dart';

import '../data/mock.dart';
import '../models/content.dart';
import 'api_config.dart';
import 'backend_api.dart';

class ContentStore extends ChangeNotifier {
  ContentStore._();

  static final ContentStore instance = ContentStore._();

  List<Food> _foods = mockFoods;
  List<Recipe> _recipes = mockRecipes;
  bool _fromBackend = false;

  List<Food> get foods => _foods;

  List<Recipe> get recipes => _recipes;

  /// 数据是否来自真后端。界面上可以如实标注，不夸大。
  bool get fromBackend => _fromBackend;

  /// 给人看的数据来源说明
  String get sourceLabel => _fromBackend ? '后端数据' : '本地演示数据';

  /// 加载内容数据。后端不在线或请求失败都静默降级到本地假数据。
  Future<void> load() async {
    if (!BackendStatus.instance.online) {
      _useLocal();
      return;
    }

    try {
      final foods = await BackendApi.instance.fetchFoods();
      final recipes = await BackendApi.instance.fetchRecipes();

      // 后端返回空列表时【不】覆盖本地数据 ——
      // 空白界面比假数据更糟，演示时尤其明显。
      _foods = foods.isEmpty ? mockFoods : foods;
      _recipes = recipes.isEmpty ? mockRecipes : recipes;
      _fromBackend = foods.isNotEmpty || recipes.isNotEmpty;
      notifyListeners();
    } catch (error) {
      debugPrint('[ContentStore] 后端内容加载失败，降级到本地数据：$error');
      _useLocal();
    }
  }

  void _useLocal() {
    _foods = mockFoods;
    _recipes = mockRecipes;
    _fromBackend = false;
    notifyListeners();
  }
}
