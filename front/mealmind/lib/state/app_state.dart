import 'package:flutter/foundation.dart';

/// =====================================================================
/// 全局共享状态 —— 家庭档案
///
/// 【为什么需要这个文件】
/// README 第 4 节约定「不引入状态管理框架，用 setState 足够」。
/// 那条约定在「5 个页面各自独立」时成立；但家庭档案是【求解器的输入】，
/// 它必须从「我的」页流向「菜单」页 —— 跨页面共享，setState 管不到别的页面。
///
/// 所以这里用 Flutter 自带的 ChangeNotifier 做一个最小的共享层：
///   · 零第三方依赖（没有 Provider / Riverpod / GetX）
///   · 仍然守住「不引入状态管理框架」这条约定
///
/// 【用法】
///   AppState.instance.profile.people            // 读
///   AppState.instance.saveProfile(...)          // 写，并通知所有监听者
///   ListenableBuilder(listenable: AppState.instance, ...)   // 需要自动重建时
///
/// 【边界】
/// 这里只存「约束」，不存「结果」。求解结果仍然由 api.dart 拿，
/// 后端 CP-SAT 就绪后本文件不用改（改的是 api.dart 里 useMock 那一行）。
/// =====================================================================

/// 家庭档案 —— 求解器的硬约束来源
@immutable
class FamilyProfile {
  /// 就餐人数
  final int people;

  /// 周预算（元）
  final double budget;

  /// 单餐可用烹饪时间（分钟）
  final double cookMinutes;

  /// 是否限钠（家里有高血压成员时为 true）
  final bool lowSodium;

  /// 是否开启采购/保质期提醒
  final bool reminders;

  /// 口味偏好
  final Set<String> preferences;

  /// 忌口（过敏原 / 不吃的东西）
  final Set<String> avoid;

  /// 家里有的厨具
  final Set<String> tools;

  const FamilyProfile({
    this.people = 3,
    this.budget = 300,
    this.cookMinutes = 45,
    this.lowSodium = true,
    this.reminders = true,
    this.preferences = const <String>{'家常', '清淡'},
    this.avoid = const <String>{'辛辣'},
    this.tools = const <String>{'炒锅', '汤锅'},
  });

  /// 每人每天的钠上限（mg）。
  /// 限钠模式按《中国居民膳食指南》的 2000mg 卡；
  /// 关闭限钠时放宽到 2400mg —— 这会让菜单页的钠进度条肉眼可见地变化，
  /// 是「约束真的被求解器管住了」的直接证据。
  int get sodiumLimitMg => lowSodium ? 2000 : 2400;

  FamilyProfile copyWith({
    int? people,
    double? budget,
    double? cookMinutes,
    bool? lowSodium,
    bool? reminders,
    Set<String>? preferences,
    Set<String>? avoid,
    Set<String>? tools,
  }) {
    return FamilyProfile(
      people: people ?? this.people,
      budget: budget ?? this.budget,
      cookMinutes: cookMinutes ?? this.cookMinutes,
      lowSodium: lowSodium ?? this.lowSodium,
      reminders: reminders ?? this.reminders,
      preferences: preferences ?? this.preferences,
      avoid: avoid ?? this.avoid,
      tools: tools ?? this.tools,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is FamilyProfile &&
          other.people == people &&
          other.budget == budget &&
          other.cookMinutes == cookMinutes &&
          other.lowSodium == lowSodium &&
          other.reminders == reminders &&
          setEquals(other.preferences, preferences) &&
          setEquals(other.avoid, avoid) &&
          setEquals(other.tools, tools);

  @override
  int get hashCode => Object.hash(
        people,
        budget,
        cookMinutes,
        lowSodium,
        reminders,
        Object.hashAllUnordered(preferences),
        Object.hashAllUnordered(avoid),
        Object.hashAllUnordered(tools),
      );
}

/// 应用级共享状态。
///
/// 用单例而不是 InheritedWidget，是因为本项目只有这一份状态、
/// 页面层级也浅 —— 单例能让 5 个页面都用零改动的方式拿到它。
class AppState extends ChangeNotifier {
  AppState._();

  static final AppState instance = AppState._();

  FamilyProfile _profile = const FamilyProfile();

  FamilyProfile get profile => _profile;

  int _revision = 0;

  /// 档案被保存的次数。菜单页监听它：一旦变了就重新求解。
  /// 用计数器而不是直接比较 profile，是为了让「保存了但值没变」
  /// 也能触发一次重算（用户按了保存，就该有反馈）。
  int get revision => _revision;

  /// 保存家庭档案 —— profile.dart 的「保存」按钮调它
  void saveProfile(FamilyProfile next) {
    if (next == _profile) {
      // 值没变也照样走一遍，让用户看到「重算」反馈
      _revision++;
      notifyListeners();
      return;
    }
    _profile = next;
    _revision++;
    notifyListeners();
  }

  /// 恢复默认（调试 / 演示用）
  void resetProfile() {
    _profile = const FamilyProfile();
    _revision++;
    notifyListeners();
  }
}
