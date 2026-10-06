import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_config.dart';
import '../services/backend_api.dart';

/// =====================================================================
/// 全局共享状态 —— 家庭档案
///
/// 【为什么需要这个文件】
/// README 第 4 节约定「不引入状态管理框架，用 setState 足够」。
/// 那条约定在「5 个页面各自独立」时成立；但家庭档案是【求解器的输入】，
/// 它必须从「我的」页流向首页 / 菜单 / AI —— 跨页面共享，setState 管不到别的页面。
///
/// 所以这里用 Flutter 自带的 ChangeNotifier 做一个最小的共享层：
///   · 零第三方依赖（没有 Provider / Riverpod / GetX）
///   · 仍然守住「不引入状态管理框架」这条约定
///
/// 【用法】
///   AppState.instance.profile.people            // 读
///   await AppState.instance.saveProfile(...)    // 写：内存 + 本机 + 账号
///   ListenableBuilder(listenable: AppState.instance, ...)   // 需要自动重建时
///
/// 【★ 三层存储，缺一不可】
///   1. 内存（这个单例）—— 页面之间立刻同步，不用等网络
///   2. SharedPreferences —— 没登录 / 断网时也不会一刷新就丢
///   3. 账号（PUT /api/profile）—— 换设备、换浏览器还在
///
///   以前只有第 1 层。后果是：在「我的」页把人数从 3 改成 5、切到首页
///   和 AI 页看到的还是 3（刷新后连「我的」页自己也变回 3）。
///   第 2、3 层就是这次补上的。
/// =====================================================================

/// 家庭档案 —— 求解器的硬约束来源
@immutable
class FamilyProfile {
  /// 就餐人数
  final int people;

  /// 单餐可用烹饪时间（分钟）
  final double cookMinutes;

  /// 是否限钠（家里有高血压成员时为 true）
  final bool lowSodium;

  /// 口味偏好
  final Set<String> preferences;

  /// 忌口（过敏原 / 不吃的东西）
  final Set<String> avoid;

  /// 家里有的厨具
  final Set<String> tools;

  // ⚠️ 这里原来还有一个 `budget`（每周饮食预算）。
  //    已删：清洗库里**没有任何价格数据**，那个数字纯粹是前端编的，
  //    还被拿去做「预算进度条」和「¥296 / 预算 ¥300」这种展示。
  //    没有数据支撑的指标不该出现在界面上。

  const FamilyProfile({
    this.people = 3,
    this.cookMinutes = 45,
    this.lowSodium = true,
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
    double? cookMinutes,
    bool? lowSodium,
    Set<String>? preferences,
    Set<String>? avoid,
    Set<String>? tools,
  }) {
    return FamilyProfile(
      people: people ?? this.people,
      cookMinutes: cookMinutes ?? this.cookMinutes,
      lowSodium: lowSodium ?? this.lowSodium,
      preferences: preferences ?? this.preferences,
      avoid: avoid ?? this.avoid,
      tools: tools ?? this.tools,
    );
  }

  // ---- 和后端 /api/profile 的互转 ----

  /// 后端字段名 → 本模型。
  ///
  /// `family_size` 在后端是「默认菜单人数」，语义和这里的 people 是同一个。
  factory FamilyProfile.fromServerJson(Map<String, dynamic> j) {
    List<String> strList(Object? value) =>
        ((value as List?) ?? const <dynamic>[])
            .map((e) => e.toString())
            .where((e) => e.isNotEmpty)
            .toList();

    return FamilyProfile(
      people: (j['family_size'] as num?)?.toInt() ?? 3,
      cookMinutes: ((j['cook_minutes'] as num?)?.toDouble() ?? 45),
      lowSodium: j['low_sodium'] as bool? ?? true,
      preferences: strList(j['preferences']).toSet(),
      avoid: strList(j['avoid_foods']).toSet(),
      tools: strList(j['tools']).toSet(),
    );
  }

  /// 本模型 → 后端字段名。
  ///
  /// ⚠️ 只发这几个字段：后端 `PreferenceUpdate` 是「没传的保持原值」，
  ///    把 taste / diet_style / favorite_categories 一起发过去会用 null 清掉它们。
  Map<String, dynamic> toServerJson() => <String, dynamic>{
    'family_size': people,
    'cook_minutes': cookMinutes.round(),
    'low_sodium': lowSodium,
    'preferences': preferences.toList(),
    'avoid_foods': avoid.toList(),
    'tools': tools.toList(),
  };

  /// 本机缓存（SharedPreferences）用的编解码。
  Map<String, dynamic> toCacheJson() => <String, dynamic>{
    'people': people,
    'cook_minutes': cookMinutes,
    'low_sodium': lowSodium,
    'preferences': preferences.toList(),
    'avoid': avoid.toList(),
    'tools': tools.toList(),
  };

  factory FamilyProfile.fromCacheJson(Map<String, dynamic> j) {
    List<String> strList(Object? value) =>
        ((value as List?) ?? const <dynamic>[])
            .map((e) => e.toString())
            .toList();
    return FamilyProfile(
      people: (j['people'] as num?)?.toInt() ?? 3,
      cookMinutes: (j['cook_minutes'] as num?)?.toDouble() ?? 45,
      lowSodium: j['low_sodium'] as bool? ?? true,
      preferences: strList(j['preferences']).toSet(),
      avoid: strList(j['avoid']).toSet(),
      tools: strList(j['tools']).toSet(),
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is FamilyProfile &&
          other.people == people &&
          other.cookMinutes == cookMinutes &&
          other.lowSodium == lowSodium &&
          setEquals(other.preferences, preferences) &&
          setEquals(other.avoid, avoid) &&
          setEquals(other.tools, tools);

  @override
  int get hashCode => Object.hash(
    people,
    cookMinutes,
    lowSodium,
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

  static const String _kCacheKey = 'family_profile';

  FamilyProfile _profile = const FamilyProfile();

  FamilyProfile get profile => _profile;

  int _revision = 0;

  /// 档案被保存的次数。菜单页监听它：一旦变了就重新求解。
  /// 用计数器而不是直接比较 profile，是为了让「保存了但值没变」
  /// 也能触发一次重算（用户按了保存，就该有反馈）。
  int get revision => _revision;

  /// 启动时把档案恢复出来：先读本机缓存（快、离线也有），
  /// 再问服务器（权威，可能是别的设备改的）。
  ///
  /// 读不到就保持现状 —— **绝不拿默认值覆盖已恢复的本地值**。
  Future<void> load() async {
    await _loadCache();
    final remote = await BackendApi.instance.fetchProfile();
    if (remote != null && remote != _profile) {
      _profile = remote;
      _revision++;
      await _saveCache();
      notifyListeners();
    }
  }

  Future<void> _loadCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_kCacheKey);
      if (raw == null || raw.isEmpty) return;
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) return;
      _profile = FamilyProfile.fromCacheJson(decoded);
      notifyListeners();
    } catch (error) {
      debugPrint('[AppState] 家庭档案本机缓存读取失败：$error');
    }
  }

  Future<void> _saveCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kCacheKey, jsonEncode(_profile.toCacheJson()));
    } catch (error) {
      debugPrint('[AppState] 家庭档案本机缓存写入失败：$error');
    }
  }

  /// 保存家庭档案。
  ///
  /// 顺序是刻意的：**先改内存并通知**（界面立刻同步，不等网络），
  /// 再写本机缓存，最后才推服务器。推失败不抛给界面 —— 但也不假装成功，
  /// 返回值如实告诉调用方「存到哪一层了」。
  Future<ProfileSaveResult> saveProfile(FamilyProfile next) async {
    // 值没变也照样走一遍，让用户看到「重算」反馈
    _profile = next;
    _revision++;
    notifyListeners();

    await _saveCache();

    if (!BackendStatus.instance.online) {
      return ProfileSaveResult.localOnly('后端未连接');
    }
    if (!BackendApi.instance.canUseProfileApi) {
      return ProfileSaveResult.localOnly('还没有登录');
    }
    try {
      final saved = await BackendApi.instance.pushProfile(next);
      _profile = saved;
      await _saveCache();
      notifyListeners();
      return ProfileSaveResult.synced();
    } catch (error) {
      debugPrint('[AppState] 家庭档案上传失败：$error');
      return ProfileSaveResult.localOnly('同步到账号失败');
    }
  }

  /// 恢复默认（调试 / 演示用）。**会一并写本机缓存**，也就是把用户自己的
  /// 档案冲掉。想只清内存（比如测试里模拟「重启 App」）用 [debugResetMemory]。
  Future<void> resetProfile() async {
    await saveProfile(const FamilyProfile());
  }

  /// 仅供测试：只清掉内存里的档案，**不碰本机缓存**。
  ///
  /// 为什么需要它：测试要模拟「重启 App」，也就是「内存空、缓存还在」。
  /// 用 [resetProfile] 做不到 —— 它会把默认值写进缓存，重启后读到的自然
  /// 还是默认值，看着像「缓存没生效」，其实是测试自己把缓存覆盖掉了。
  @visibleForTesting
  void debugResetMemory() {
    _profile = const FamilyProfile();
    _revision++;
    notifyListeners();
  }
}

/// 保存结果 —— 让界面能如实说明「存到本机了」还是「存到账号了」。
@immutable
class ProfileSaveResult {
  final bool synced;
  final String? reason;

  const ProfileSaveResult._(this.synced, this.reason);

  factory ProfileSaveResult.synced() => const ProfileSaveResult._(true, null);
  factory ProfileSaveResult.localOnly(String reason) =>
      ProfileSaveResult._(false, reason);

  /// 给用户看的一句话。
  String get message => synced
      ? '家庭档案已保存 —— 首页、菜单与 AI 助手都按新约束重算'
      : '家庭档案已保存在本机（$reason），登录并连上后端后会同步到账号';
}
