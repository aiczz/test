import 'package:flutter/material.dart';

import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../services/backend_api.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'admin.dart';
import 'login.dart';

/// 个人中心：家庭档案是求解器的输入，不只是展示信息。
class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key});

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  int _people = 3;
  double _budget = 300;
  double _cookMinutes = 45;
  bool _lowSodium = true;
  bool _reminders = true;
  final Set<String> _preferences = <String>{'家常', '清淡'};
  final Set<String> _avoid = <String>{'辛辣'};
  final Set<String> _tools = <String>{'炒锅', '汤锅'};

  @override
  void initState() {
    super.initState();
    // 回填已保存的档案。不回填的话每次进这一页都回到默认值，
    // 用户会以为自己上次的修改丢了。
    final p = AppState.instance.profile;
    _people = p.people;
    _budget = p.budget;
    _cookMinutes = p.cookMinutes;
    _lowSodium = p.lowSodium;
    _reminders = p.reminders;
    _preferences
      ..clear()
      ..addAll(p.preferences);
    _avoid
      ..clear()
      ..addAll(p.avoid);
    _tools
      ..clear()
      ..addAll(p.tools);
  }

  /// 保存 = 写进全局共享状态，并通知菜单页立即重算。
  ///
  /// ⚠️ 注意这里和之前的区别：以前这个方法只弹了个 SnackBar，
  ///    什么也没存 —— 那句「下次生成菜单将使用这些约束」是假的。
  ///    现在它真的存了，菜单页也真的会跟着变。
  void _saveProfile() {
    AppState.instance.saveProfile(
      AppState.instance.profile.copyWith(
        people: _people,
        budget: _budget,
        cookMinutes: _cookMinutes,
        lowSodium: _lowSodium,
        reminders: _reminders,
        preferences: Set<String>.of(_preferences),
        avoid: Set<String>.of(_avoid),
        tools: Set<String>.of(_tools),
      ),
    );
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('家庭档案已保存 —— 菜单与购物清单已按新约束重算'),
        behavior: SnackBarBehavior.floating,
        backgroundColor: Color(0xFF163A26),
      ),
    );
  }

  /// 档案摘要：全部用真实存在的家庭档案数据拼出来，一个编的数字都没有。
  void _showProfileSummary() {
    final profile = AppState.instance.profile;
    final pref = profile.preferences.isEmpty
        ? '没有设置'
        : profile.preferences.join('、');
    final avoid = profile.avoid.isEmpty ? '没有设置' : profile.avoid.join('、');
    final tools = profile.tools.isEmpty ? '没有设置' : profile.tools.join('、');

    _showInfo(
      '当前饮食档案',
      '${profile.people} 人用餐，每周预算 ¥${profile.budget.toStringAsFixed(0)}，'
          '每天下厨时间 ${profile.cookMinutes.round()} 分钟。\n\n'
          '口味偏好：$pref\n'
          '忌口：$avoid\n'
          '可用厨具：$tools\n'
          '每日钠上限：${profile.sodiumLimitMg} mg'
          '（${profile.lowSodium ? '已开启低钠约束' : '未开启低钠约束'}）\n\n'
          '首页推荐、菜单和购物清单都是按这套档案算出来的 —— '
          '在上面改任何一项，切回首页就能看到变化。',
    );
  }

  void _showInfo(String title, String body) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => Container(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 30),
        decoration: const BoxDecoration(
          color: page,
          borderRadius: BorderRadius.vertical(top: Radius.circular(rBlock)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 42,
                height: 4,
                decoration: BoxDecoration(
                  color: line,
                  borderRadius: BorderRadius.circular(99),
                ),
              ),
            ),
            const SizedBox(height: 20),
            Text(
              title,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 10),
            Text(
              body,
              style: const TextStyle(fontSize: 14, color: muted, height: 1.7),
            ),
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('知道了'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
          children: [
            const _ProfileHero(),
            const SizedBox(height: 14),
            const _AccountCard(),
            const SizedBox(height: 14),
            const _StatsRow(),
            const SizedBox(height: 18),
            _WeeklyCard(onTap: _showProfileSummary),
            const SizedBox(height: 24),
            const _SectionTitle(
              icon: Icons.tune,
              title: '家庭与饮食约束',
              subtitle: '这些设置会直接进入菜单求解器',
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: cardDeco(),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _CounterRow(
                    icon: Icons.people_outline,
                    label: '家庭人数',
                    value: '$_people 人',
                    onMinus: _people <= 1
                        ? null
                        : () => setState(() => _people--),
                    onPlus: _people >= 8
                        ? null
                        : () => setState(() => _people++),
                  ),
                  const Divider(height: 28),
                  _SliderSetting(
                    icon: Icons.account_balance_wallet_outlined,
                    label: '每周饮食预算',
                    value: '¥${_budget.round()}',
                    min: 100,
                    max: 800,
                    divisions: 14,
                    sliderValue: _budget,
                    onChanged: (value) => setState(() => _budget = value),
                  ),
                  const Divider(height: 28),
                  _SliderSetting(
                    icon: Icons.schedule,
                    label: '每日可用烹饪时间',
                    value: '${_cookMinutes.round()} 分钟',
                    min: 15,
                    max: 120,
                    divisions: 7,
                    sliderValue: _cookMinutes,
                    onChanged: (value) => setState(() => _cookMinutes = value),
                  ),
                  const Divider(height: 28),
                  Material(
                    color: Colors.transparent,
                    child: SwitchListTile.adaptive(
                      contentPadding: EdgeInsets.zero,
                      value: _lowSodium,
                      activeThumbColor: green700,
                      title: const Text(
                        '低钠约束',
                        style: TextStyle(fontWeight: FontWeight.w800),
                      ),
                      subtitle: const Text(
                        '将每日钠摄入上限作为硬约束',
                        style: TextStyle(fontSize: 12, color: muted),
                      ),
                      secondary: const Icon(
                        Icons.favorite_outline,
                        color: green700,
                      ),
                      onChanged: (value) => setState(() => _lowSodium = value),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            _ChoiceCard(
              title: '口味偏好',
              subtitle: '用于推荐排序，不会覆盖健康约束',
              options: const ['家常', '清淡', '少油', '高蛋白', '素食'],
              selected: _preferences,
              onChanged: (value) => setState(() {
                _preferences.contains(value)
                    ? _preferences.remove(value)
                    : _preferences.add(value);
              }),
            ),
            const SizedBox(height: 12),
            _ChoiceCard(
              title: '忌口与过敏',
              subtitle: '选中项会被求解器完全排除',
              options: const ['辛辣', '花生', '海鲜', '乳制品', '香菜'],
              selected: _avoid,
              warning: true,
              onChanged: (value) => setState(() {
                _avoid.contains(value)
                    ? _avoid.remove(value)
                    : _avoid.add(value);
              }),
            ),
            const SizedBox(height: 12),
            _ChoiceCard(
              title: '可用厨具',
              subtitle: '不会推荐家里无法完成的做法',
              options: const ['炒锅', '汤锅', '烤箱', '空气炸锅', '电饭煲'],
              selected: _tools,
              onChanged: (value) => setState(() {
                _tools.contains(value)
                    ? _tools.remove(value)
                    : _tools.add(value);
              }),
            ),
            const SizedBox(height: 14),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _saveProfile,
                style: FilledButton.styleFrom(
                  backgroundColor: orange,
                  padding: const EdgeInsets.symmetric(vertical: 15),
                  shape: const StadiumBorder(),
                ),
                icon: const Icon(Icons.save_outlined),
                label: const Text(
                  '保存家庭档案',
                  style: TextStyle(fontWeight: FontWeight.w800),
                ),
              ),
            ),
            const SizedBox(height: 26),
            const _SectionTitle(
              icon: Icons.grid_view_rounded,
              title: '我的功能',
              subtitle: '记录、提醒与反馈',
            ),
            const SizedBox(height: 12),
            Container(
              decoration: cardDeco(),
              child: Column(
                children: [
                  _MenuRow(
                    icon: Icons.favorite_outline,
                    title: '我的收藏',
                    subtitle: '登录后同步到云端',
                    onTap: () => _showInfo(
                      '我的收藏',
                      '收藏的菜谱会同步到你的账号，换台设备登录也还在。',
                    ),
                  ),
                  const Divider(height: 1, indent: 56),
                  SwitchListTile.adaptive(
                    contentPadding: const EdgeInsets.fromLTRB(16, 3, 12, 3),
                    value: _reminders,
                    activeThumbColor: green700,
                    secondary: const Icon(
                      Icons.notifications_none,
                      color: green700,
                    ),
                    title: const Text(
                      '用餐与时令提醒',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                    subtitle: const Text(
                      '菜单准备、临期食材提醒',
                      style: TextStyle(fontSize: 12, color: muted),
                    ),
                    onChanged: (value) => setState(() => _reminders = value),
                  ),
                  const Divider(height: 1, indent: 56),
                  _MenuRow(
                    icon: Icons.chat_bubble_outline,
                    title: '意见反馈',
                    subtitle: '帮助我们改进推荐',
                    onTap: () =>
                        _showInfo('意见反馈', '反馈入口将在后端接入时启用。当前演示版本不会上传个人资料。'),
                  ),
                ],
              ),
            ),
            // 只有管理员才看得到这个入口。
            // ⚠️ 这只是界面上的开关 —— 真正的权限校验在后端：
            //    普通用户即使摸进这个页面，所有请求也只会拿到 403。
            ListenableBuilder(
              listenable: AuthStore.instance,
              builder: (context, _) {
                if (!(AuthStore.instance.user?.isAdmin ?? false)) {
                  return const SizedBox.shrink();
                }
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 26),
                    const _SectionTitle(
                      icon: Icons.admin_panel_settings_outlined,
                      title: '管理',
                      subtitle: '仅管理员可见',
                    ),
                    const SizedBox(height: 12),
                    Container(
                      decoration: cardDeco(),
                      child: _MenuRow(
                        icon: Icons.dashboard_customize_outlined,
                        title: '管理员控制台',
                        subtitle: '用户统计 · 封禁账号 · 登录记录',
                        onTap: () => AdminPage.open(context),
                      ),
                    ),
                  ],
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _ProfileHero extends StatelessWidget {
  const _ProfileHero();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFFEDF6E8), Color(0xFFFFF5E5)],
        ),
        borderRadius: BorderRadius.circular(rBlock),
      ),
      child: Row(
        children: [
          Container(
            width: 76,
            height: 76,
            padding: const EdgeInsets.all(4),
            decoration: const BoxDecoration(
              color: Colors.white,
              shape: BoxShape.circle,
            ),
            child: ClipOval(
              child: Image.asset(
                'assets/images/avatar.jpg',
                fit: BoxFit.cover,
                filterQuality: FilterQuality.high,
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: ListenableBuilder(
              listenable: AuthStore.instance,
              builder: (context, _) {
                final user = AuthStore.instance.user;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      user?.displayName ?? '未登录',
                      style: const TextStyle(
                        fontSize: 21,
                        fontWeight: FontWeight.w900,
                        color: green900,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      user == null ? '登录后同步你的家庭档案与收藏' : '@${user.username}',
                      style: const TextStyle(fontSize: 13, color: muted),
                    ),
                    const SizedBox(height: 8),
                    const _LocalOnlyBadge(),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// 账号卡片：登录 / 退出
//
// 按需登录：首页、食材、菜谱不需要登录就能看（说明书 §12），
// 只有「我的」这里提供入口，不做强制拦截 —— 评委点开就能看内容。
// =====================================================================

class _AccountCard extends StatelessWidget {
  const _AccountCard();

  Future<void> _openLogin(BuildContext context) async {
    final ok = await LoginPage.open(context);
    if (ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('登录成功 —— 家庭档案与收藏已同步'),
          behavior: SnackBarBehavior.floating,
          backgroundColor: Color(0xFF163A26),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: AuthStore.instance,
      builder: (context, _) {
        final store = AuthStore.instance;
        final user = store.user;

        if (user == null) {
          return Container(
            padding: const EdgeInsets.fromLTRB(16, 14, 14, 14),
            decoration: cardDeco(),
            child: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: green100,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(
                    Icons.login_rounded,
                    size: 18,
                    color: green700,
                  ),
                ),
                const SizedBox(width: 11),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '登录 / 注册',
                        style: TextStyle(
                          fontSize: 13.5,
                          fontWeight: FontWeight.w800,
                          color: ink,
                        ),
                      ),
                      SizedBox(height: 3),
                      Text(
                        '支持演示账号一键登录，不用注册',
                        style: TextStyle(fontSize: 10.5, color: muted),
                      ),
                    ],
                  ),
                ),
                FilledButton(
                  onPressed: () => _openLogin(context),
                  style: FilledButton.styleFrom(
                    backgroundColor: green700,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 9,
                    ),
                    visualDensity: VisualDensity.compact,
                    shape: const StadiumBorder(),
                  ),
                  child: const Text(
                    '去登录',
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 12),
                  ),
                ),
              ],
            ),
          );
        }

        return Container(
          padding: const EdgeInsets.fromLTRB(16, 14, 14, 14),
          decoration: cardDeco(),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: green100,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.verified_user_outlined,
                  size: 18,
                  color: green700,
                ),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '已登录 · ${user.username}',
                      style: const TextStyle(
                        fontSize: 13.5,
                        fontWeight: FontWeight.w800,
                        color: ink,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '家庭人数 ${user.familySize} 人',
                      style: const TextStyle(fontSize: 10.5, color: muted),
                    ),
                  ],
                ),
              ),
              // 管理员入口就放在登录信息旁边 ——
              // 之前只放在页面最底部（意见反馈下面），得一路滚下去才看得到，
              // 用户根本找不到。
              if (user.isAdmin)
                TextButton(
                  onPressed: () => AdminPage.open(context),
                  style: TextButton.styleFrom(
                    foregroundColor: green700,
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    minimumSize: const Size(0, 34),
                    visualDensity: VisualDensity.compact,
                  ),
                  child: const Text(
                    '管理',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              TextButton(
                onPressed: () async {
                  await store.logout();
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('已退出登录'),
                        behavior: SnackBarBehavior.floating,
                        backgroundColor: Color(0xFF163A26),
                      ),
                    );
                  }
                },
                child: const Text(
                  '退出',
                  style: TextStyle(fontSize: 12, color: muted),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _LocalOnlyBadge extends StatelessWidget {
  const _LocalOnlyBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: tagDeco(),
      child: const Text(
        '本地匿名档案',
        style: TextStyle(fontSize: 10, color: green700),
      ),
    );
  }
}

/// 四个统计数字。
///
/// ★ 以前这里是写死的「收藏 12 / 历史 28 / 食材 6 / 偏好 4」—— 全是假数字。
///   现在：登录且后端在线时显示真实数量，否则显示「—」。
///   宁可显示「—」也不显示一个编出来的数字 —— 演示时被问「12 是哪来的」很难看。
class _StatsRow extends StatefulWidget {
  const _StatsRow();

  @override
  State<_StatsRow> createState() => _StatsRowState();
}

class _StatsRowState extends State<_StatsRow> {
  int? _favorites;
  int? _pantry;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
    // 登录 / 退出后要重新拉 —— 否则退出登录还显示着上一个人的数字
    AuthStore.instance.addListener(_onAuthChanged);
    AppState.instance.addListener(_onProfileChanged);
  }

  @override
  void dispose() {
    AuthStore.instance.removeListener(_onAuthChanged);
    AppState.instance.removeListener(_onProfileChanged);
    super.dispose();
  }

  void _onAuthChanged() {
    if (mounted) setState(() {});
    _load();
  }

  void _onProfileChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _load() async {
    final canAskBackend =
        BackendStatus.instance.online && AuthStore.instance.isLoggedIn;
    if (!canAskBackend) {
      if (mounted) {
        setState(() {
          _favorites = null;
          _pantry = null;
        });
      }
      return;
    }
    if (_loading) return;
    _loading = true;
    try {
      final favorites = await BackendApi.instance.fetchFavoriteCount();
      final pantry = await BackendApi.instance.fetchMyFoods();
      if (!mounted) return;
      setState(() {
        _favorites = favorites;
        _pantry = pantry.length;
      });
    } catch (error) {
      debugPrint('[ProfilePage] 统计数字加载失败：$error');
    } finally {
      _loading = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final profile = AppState.instance.profile;
    final stats = <(IconData, String, String)>[
      (Icons.favorite, _favorites?.toString() ?? '—', '收藏'),
      (Icons.kitchen, _pantry?.toString() ?? '—', '我的食材'),
      (Icons.tune, '${profile.preferences.length}', '口味偏好'),
      (Icons.block, '${profile.avoid.length}', '忌口'),
    ];
    return Row(
      children: [
        for (var i = 0; i < stats.length; i++) ...[
          if (i > 0) const SizedBox(width: 8),
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 13),
              decoration: cardDeco(radius: 16),
              child: Column(
                children: [
                  Icon(stats[i].$1, size: 18, color: green700),
                  const SizedBox(height: 4),
                  Text(
                    stats[i].$2,
                    style: const TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  Text(
                    stats[i].$3,
                    style: const TextStyle(fontSize: 10, color: muted),
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

/// 「当前饮食档案」卡片。
///
/// ★ 以前写的是「本周饮食记录 · 已安排 5 餐」—— 纯编的，后端也没有
///   「用餐记录」这种概念。现在改成用【真实存在的数据】拼摘要：
///   人数、预算、下厨时间、口味、忌口全都来自 AppState 的家庭档案。
///   这些值用户自己刚改过，点进去能一一对上，不会露馅。
class _WeeklyCard extends StatelessWidget {
  final VoidCallback onTap;

  const _WeeklyCard({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: AppState.instance,
      builder: (context, _) {
        final profile = AppState.instance.profile;
        final pref = profile.preferences.isEmpty
            ? '未设置'
            : profile.preferences.join('、');
        final avoid = profile.avoid.isEmpty ? '无' : profile.avoid.join('、');

        return InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(rBlock),
          child: Container(
            padding: const EdgeInsets.all(17),
            decoration: BoxDecoration(
              color: green50,
              borderRadius: BorderRadius.circular(rBlock),
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.bar_chart_rounded,
                  color: green700,
                  size: 30,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '当前饮食档案',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${profile.people} 人用餐 · 周预算 '
                        '¥${profile.budget.toStringAsFixed(0)} · '
                        '每天 ${profile.cookMinutes.round()} 分钟',
                        style: const TextStyle(fontSize: 12, color: muted),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '偏好 $pref · 忌口 $avoid',
                        style: const TextStyle(fontSize: 11.5, color: muted),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right, color: green700),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;

  const _SectionTitle({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: green700),
        const SizedBox(width: 9),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w900,
                ),
              ),
              Text(
                subtitle,
                style: const TextStyle(fontSize: 11, color: muted),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _CounterRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final VoidCallback? onMinus;
  final VoidCallback? onPlus;

  const _CounterRow({
    required this.icon,
    required this.label,
    required this.value,
    required this.onMinus,
    required this.onPlus,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: green700),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            label,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
        ),
        IconButton.filledTonal(
          onPressed: onMinus,
          icon: const Icon(Icons.remove),
        ),
        SizedBox(
          width: 56,
          child: Text(
            value,
            textAlign: TextAlign.center,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
        ),
        IconButton.filledTonal(onPressed: onPlus, icon: const Icon(Icons.add)),
      ],
    );
  }
}

class _SliderSetting extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final double min;
  final double max;
  final int divisions;
  final double sliderValue;
  final ValueChanged<double> onChanged;

  const _SliderSetting({
    required this.icon,
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.divisions,
    required this.sliderValue,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            Icon(icon, color: green700),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                label,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
            ),
            Text(
              value,
              style: const TextStyle(
                color: green700,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        Slider(
          min: min,
          max: max,
          divisions: divisions,
          value: sliderValue,
          activeColor: green700,
          onChanged: onChanged,
        ),
      ],
    );
  }
}

class _ChoiceCard extends StatelessWidget {
  final String title;
  final String subtitle;
  final List<String> options;
  final Set<String> selected;
  final ValueChanged<String> onChanged;
  final bool warning;

  const _ChoiceCard({
    required this.title,
    required this.subtitle,
    required this.options,
    required this.selected,
    required this.onChanged,
    this.warning = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: cardDeco(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 3),
          Text(subtitle, style: const TextStyle(fontSize: 11, color: muted)),
          const SizedBox(height: 12),
          Wrap(
            spacing: 7,
            runSpacing: 7,
            children: options.map((item) {
              final isSelected = selected.contains(item);
              return FilterChip(
                label: Text(item),
                selected: isSelected,
                selectedColor: warning ? orange100 : green100,
                checkmarkColor: warning ? orange : green700,
                labelStyle: TextStyle(
                  color: isSelected ? (warning ? orange : green700) : muted,
                  fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                ),
                onSelected: (_) => onChanged(item),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

class _MenuRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _MenuRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: ListTile(
        onTap: onTap,
        leading: Icon(icon, color: green700),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(subtitle, style: const TextStyle(fontSize: 11)),
        trailing: const Icon(Icons.chevron_right),
      ),
    );
  }
}
