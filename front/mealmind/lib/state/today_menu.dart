import 'package:flutter/foundation.dart';

import '../models/content.dart';

/// =====================================================================
/// 今日菜单 —— 用户手动挑进来的「今天想做」的菜
///
/// 【为什么单独一个文件，不像家庭档案那样塞进 AppState】
/// AppState 的注释里写明了它「只存约束，不存结果」：
/// 家庭档案是求解器的输入，改一下就触发重算。
/// 而今日菜单是用户一道道手动加进来的结果，触发方式和生命周期都不同，
/// 混进 AppState 只会让「改档案 → 重算」这条链路的边界变模糊。
///
/// 【为什么需要它】
/// 在此之前，「加入今日菜单」按钮点了只弹一句提示就没了 ——
/// 没有任何地方真的存下来，也没有任何页面能看到加进去的菜。
/// 现在菜谱详情（recipes.dart）和 AI 助手（ai.dart）都写这里，
/// 菜谱页的「今日菜单」tab 读它。
///
/// 和 AppState 一样只用 Flutter 自带的 ChangeNotifier、零第三方依赖，
/// 守住 README 里「不引入状态管理框架」那条约定。
///
/// 【为什么不持久化】
/// 「今日菜单」顾名思义是当天的东西，重启就清空是符合预期的行为；
/// 真正需要留存的是家庭档案和「我的食材」，那两处各自有自己的存储。
/// =====================================================================
class TodayMenuStore extends ChangeNotifier {
  TodayMenuStore._();

  static final TodayMenuStore instance = TodayMenuStore._();

  final List<Recipe> _items = <Recipe>[];

  /// 只读视图 —— 外部拿不到内部 list，改不动。
  List<Recipe> get items => List<Recipe>.unmodifiable(_items);

  int get count => _items.length;

  bool get isEmpty => _items.isEmpty;

  bool contains(String recipeId) => _items.any((r) => r.id == recipeId);

  /// 加入。已经在里面就返回 false，
  /// 让调用方能分出「已加入」和「已经在今日菜单里了」两种提示。
  bool add(Recipe recipe) {
    if (contains(recipe.id)) return false;
    _items.add(recipe);
    notifyListeners();
    return true;
  }

  void remove(String recipeId) {
    final before = _items.length;
    _items.removeWhere((r) => r.id == recipeId);
    if (_items.length != before) notifyListeners();
  }

  void clear() {
    if (_items.isEmpty) return;
    _items.clear();
    notifyListeners();
  }
}
