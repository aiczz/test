import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../services/backend_api.dart';
import '../theme.dart';

const _blue = Color(0xFF3C6FE8);
const _softBlue = Color(0xFFEAF2FF);
const _gold = Color(0xFFE89A22);
const _softGold = Color(0xFFFFF3DA);

class AdminPage extends StatefulWidget {
  const AdminPage({super.key});

  static Future<void> open(BuildContext context) => Navigator.of(context).push(
    MaterialPageRoute<void>(builder: (_) => const AdminPage()),
  );

  @override
  State<AdminPage> createState() => _AdminPageState();
}

class _AdminPageState extends State<AdminPage> {
  final TextEditingController _search = TextEditingController();
  AdminStats? _stats;
  List<AdminUser> _users = const <AdminUser>[];
  List<LoginLogEntry> _logs = const <LoginLogEntry>[];
  int _section = 0;
  int? _busyUserId;
  bool _loading = true;
  bool _onlyFailed = false;
  String? _error;

  bool get _demoMode => !BackendStatus.instance.online;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    if (_demoMode) {
      await Future<void>.delayed(const Duration(milliseconds: 160));
      if (!mounted) return;
      final data = _demoData();
      setState(() {
        _stats = data.$1;
        _users = data.$2;
        _logs = data.$3;
        _loading = false;
      });
      return;
    }
    try {
      final result = await Future.wait<Object>(<Future<Object>>[
        BackendApi.instance.fetchAdminStats(),
        BackendApi.instance.fetchAdminUsers(
          keyword: _search.text.trim().isEmpty ? null : _search.text.trim(),
        ),
        BackendApi.instance.fetchLoginLogs(onlyFailed: _onlyFailed),
      ]);
      if (!mounted) return;
      setState(() {
        _stats = result[0] as AdminStats;
        _users = (result[1] as AdminUserPage).items;
        _logs = (result[2] as LoginLogPage).items;
        _loading = false;
      });
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.response?.statusCode == 403
            ? '当前账号没有管理员权限'
            : '后台数据加载失败，请检查服务连接';
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = '后台数据加载失败，请稍后重试';
        _loading = false;
      });
    }
  }

  (AdminStats, List<AdminUser>, List<LoginLogEntry>) _demoData() {
    final now = DateTime.now();
    return (
      const AdminStats(
        totalUsers: 128,
        adminUsers: 1,
        bannedUsers: 3,
        newUsersToday: 8,
        totalLogins: 1260,
        loginsToday: 46,
        failedLoginsToday: 4,
        activeUsersToday: 31,
      ),
      <AdminUser>[
        AdminUser(
          id: -1,
          username: 'admin',
          nickname: '食时管理员',
          email: 'admin@shishi.demo',
          isAdmin: true,
          createdAt: now.subtract(const Duration(days: 86)),
          lastLoginAt: now.subtract(const Duration(minutes: 2)),
          loginCount: 48,
        ),
        AdminUser(
          id: 1,
          username: 'demo',
          nickname: '演示用户',
          familySize: 3,
          lastLoginAt: now.subtract(const Duration(hours: 1)),
          loginCount: 21,
        ),
        AdminUser(
          id: 2,
          username: 'phone_8000',
          nickname: '用户8000',
          familySize: 2,
          lastLoginAt: now.subtract(const Duration(hours: 4)),
          loginCount: 7,
        ),
        AdminUser(
          id: 3,
          username: 'spring_home',
          nickname: '春日小家',
          familySize: 4,
          lastLoginAt: now.subtract(const Duration(days: 1)),
          loginCount: 5,
        ),
        AdminUser(
          id: 4,
          username: 'blocked_sample',
          nickname: '受限账号示例',
          isBanned: true,
          lastLoginAt: now.subtract(const Duration(days: 5)),
          loginCount: 3,
        ),
      ],
      <LoginLogEntry>[
        LoginLogEntry(
          id: 1,
          username: 'admin',
          success: true,
          ip: '127.0.0.1',
          createdAt: now.subtract(const Duration(minutes: 2)),
        ),
        LoginLogEntry(
          id: 2,
          username: 'phone_8000',
          success: true,
          ip: '192.168.1.23',
          createdAt: now.subtract(const Duration(hours: 4)),
        ),
        LoginLogEntry(
          id: 3,
          username: 'unknown_user',
          success: false,
          ip: '192.168.1.51',
          detail: '用户名或密码不正确',
          createdAt: now.subtract(const Duration(hours: 6)),
        ),
        LoginLogEntry(
          id: 4,
          username: 'demo',
          success: true,
          ip: '127.0.0.1',
          createdAt: now.subtract(const Duration(days: 1)),
        ),
      ],
    );
  }

  Future<void> _toggleBan(AdminUser user) async {
    if (_busyUserId != null || user.isAdmin) return;
    setState(() => _busyUserId = user.id);
    try {
      final updated = _demoMode
          ? await _mockToggle(user)
          : await BackendApi.instance.setUserBanned(
              user.id,
              banned: !user.isBanned,
            );
      if (!mounted) return;
      setState(() {
        _users = _users
            .map((item) => item.id == user.id ? updated : item)
            .toList();
      });
      _toast(updated.isBanned ? '已封禁 ${user.display}' : '已解除账号限制');
    } on DioException catch (error) {
      if (!mounted) return;
      final body = error.response?.data;
      _toast(body is Map && body['detail'] is String
          ? body['detail'] as String
          : '操作失败，请稍后再试');
    } finally {
      if (mounted) setState(() => _busyUserId = null);
    }
  }

  Future<AdminUser> _mockToggle(AdminUser user) async {
    await Future<void>.delayed(const Duration(milliseconds: 240));
    return AdminUser(
      id: user.id,
      username: user.username,
      nickname: user.nickname,
      email: user.email,
      familySize: user.familySize,
      isAdmin: user.isAdmin,
      isBanned: !user.isBanned,
      createdAt: user.createdAt,
      lastLoginAt: user.lastLoginAt,
      loginCount: user.loginCount,
    );
  }

  void _toast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        backgroundColor: green900,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: page,
      appBar: AppBar(
        backgroundColor: page,
        foregroundColor: ink,
        elevation: 0,
        titleSpacing: 4,
        title: Row(
          children: <Widget>[
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                color: green700,
                borderRadius: BorderRadius.circular(11),
              ),
              child: const Icon(
                Icons.admin_panel_settings_rounded,
                color: Colors.white,
                size: 19,
              ),
            ),
            const SizedBox(width: 10),
            const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  '食时管理台',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900),
                ),
                Text(
                  '运营与账号安全',
                  style: TextStyle(fontSize: 9.5, color: muted),
                ),
              ],
            ),
          ],
        ),
        actions: <Widget>[
          Center(child: _statusPill()),
          IconButton(
            tooltip: '刷新数据',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh_rounded),
          ),
          const SizedBox(width: 6),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: green700))
          : _error != null
          ? _errorView()
          : SafeArea(
              child: Column(
                children: <Widget>[
                  _sectionBar(),
                  Expanded(
                    child: IndexedStack(
                      index: _section,
                      children: <Widget>[
                        _dashboard(),
                        _usersView(),
                        _logsView(),
                      ],
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  Widget _statusPill() => Container(
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
    decoration: BoxDecoration(
      color: _demoMode ? _softGold : green100,
      borderRadius: BorderRadius.circular(20),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
            color: _demoMode ? _gold : green600,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 5),
        Text(
          _demoMode ? '演示数据' : '服务在线',
          style: TextStyle(
            color: _demoMode ? _gold : green700,
            fontSize: 10,
            fontWeight: FontWeight.w800,
          ),
        ),
      ],
    ),
  );

  Widget _sectionBar() {
    const items = <(IconData, String)>[
      (Icons.space_dashboard_rounded, '总览'),
      (Icons.group_rounded, '用户管理'),
      (Icons.shield_outlined, '登录安全'),
    ];
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: const Color(0xFFE9EFE7),
        borderRadius: BorderRadius.circular(15),
      ),
      child: Row(
        children: <Widget>[
          for (var index = 0; index < items.length; index++)
            Expanded(
              child: InkWell(
                borderRadius: BorderRadius.circular(12),
                onTap: () => setState(() => _section = index),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 180),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: BoxDecoration(
                    color: _section == index ? Colors.white : Colors.transparent,
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: _section == index
                        ? const <BoxShadow>[
                            BoxShadow(
                              color: Color(0x10122C1C),
                              blurRadius: 12,
                              offset: Offset(0, 3),
                            ),
                          ]
                        : null,
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: <Widget>[
                      Icon(
                        items[index].$1,
                        size: 16,
                        color: _section == index ? green700 : muted,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        items[index].$2,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w800,
                          color: _section == index ? green700 : muted,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _dashboard() {
    final stats = _stats!;
    final name = AuthStore.instance.user?.displayName ?? '管理员';
    return RefreshIndicator(
      color: green700,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 6, 16, 30),
        children: <Widget>[
          _hero(name, stats),
          const SizedBox(height: 14),
          _statsGrid(stats),
          const SizedBox(height: 18),
          _sectionTitle('需要关注', '今天的账号与安全动态'),
          const SizedBox(height: 10),
          _attentionCard(
            icon: Icons.person_add_alt_1_rounded,
            iconColor: _blue,
            iconBackground: _softBlue,
            title: '${stats.newUsersToday} 位新用户',
            description: '今日新增账号，较昨日保持稳定',
            action: '查看用户',
            onTap: () => setState(() => _section = 1),
          ),
          const SizedBox(height: 10),
          _attentionCard(
            icon: Icons.gpp_maybe_rounded,
            iconColor: orange,
            iconBackground: orange100,
            title: '${stats.failedLoginsToday} 次失败登录',
            description: '建议检查短时间内重复失败的账号',
            action: '查看记录',
            onTap: () => setState(() => _section = 2),
          ),
          const SizedBox(height: 18),
          _sectionTitle('最近登录', '最新 3 条活动'),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            decoration: cardDeco(radius: 18),
            child: Column(
              children: <Widget>[
                for (final log in _logs.take(3)) _logTile(log, compact: true),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _hero(String name, AdminStats stats) => Container(
    padding: const EdgeInsets.all(22),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(24),
      gradient: const LinearGradient(
        colors: <Color>[Color(0xFF0F5F35), Color(0xFF25884C)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      boxShadow: const <BoxShadow>[
        BoxShadow(
          color: Color(0x33227346),
          blurRadius: 24,
          offset: Offset(0, 10),
        ),
      ],
    ),
    child: Row(
      children: <Widget>[
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                '早上好，$name',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 23,
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 7),
              Text(
                '今天已有 ${stats.activeUsersToday} 位用户使用食时，系统运行正常。',
                style: const TextStyle(
                  color: Color(0xDFFFFFFF),
                  fontSize: 12,
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                decoration: BoxDecoration(
                  color: const Color(0x22FFFFFF),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0x33FFFFFF)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Icon(Icons.check_circle_rounded, color: Colors.white, size: 14),
                    SizedBox(width: 6),
                    Text(
                      '账号服务运行正常',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 10.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 14),
        Container(
          width: 74,
          height: 74,
          decoration: BoxDecoration(
            color: const Color(0x1FFFFFFF),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: const Color(0x33FFFFFF)),
          ),
          child: const Icon(Icons.insights_rounded, color: Colors.white, size: 36),
        ),
      ],
    ),
  );

  Widget _statsGrid(AdminStats stats) {
    final cells = <(String, int, IconData, Color, Color)>[
      ('全部用户', stats.totalUsers, Icons.groups_2_rounded, green700, green100),
      ('今日活跃', stats.activeUsersToday, Icons.bolt_rounded, _blue, _softBlue),
      ('今日新增', stats.newUsersToday, Icons.person_add_alt_1_rounded, _gold, _softGold),
      ('受限账号', stats.bannedUsers, Icons.block_rounded, orange, orange100),
    ];
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth >= 760 ? 4 : 2;
        final width = (constraints.maxWidth - (columns - 1) * 10) / columns;
        return Wrap(
          spacing: 10,
          runSpacing: 10,
          children: <Widget>[
            for (final item in cells)
              SizedBox(
                width: width,
                child: Container(
                  padding: const EdgeInsets.all(15),
                  decoration: cardDeco(radius: 17),
                  child: Row(
                    children: <Widget>[
                      Container(
                        width: 38,
                        height: 38,
                        decoration: BoxDecoration(
                          color: item.$5,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(item.$3, color: item.$4, size: 19),
                      ),
                      const SizedBox(width: 11),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              '${item.$2}',
                              style: const TextStyle(
                                color: ink,
                                fontSize: 20,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                            Text(
                              item.$1,
                              style: const TextStyle(color: muted, fontSize: 10.5),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  Widget _attentionCard({
    required IconData icon,
    required Color iconColor,
    required Color iconBackground,
    required String title,
    required String description,
    required String action,
    required VoidCallback onTap,
  }) => Container(
    padding: const EdgeInsets.all(16),
    decoration: cardDeco(radius: 18),
    child: Row(
      children: <Widget>[
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: iconBackground,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Icon(icon, color: iconColor, size: 21),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                title,
                style: const TextStyle(
                  color: ink,
                  fontWeight: FontWeight.w800,
                  fontSize: 13,
                ),
              ),
              const SizedBox(height: 3),
              Text(description, style: const TextStyle(color: muted, fontSize: 10.5)),
            ],
          ),
        ),
        TextButton(onPressed: onTap, child: Text(action)),
      ],
    ),
  );

  Widget _usersView() {
    final keyword = _search.text.trim().toLowerCase();
    final users = _demoMode && keyword.isNotEmpty
        ? _users
              .where(
                (user) =>
                    user.username.toLowerCase().contains(keyword) ||
                    user.display.toLowerCase().contains(keyword),
              )
              .toList()
        : _users;
    return Column(
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 6, 16, 10),
          child: Row(
            children: <Widget>[
              Expanded(
                child: TextField(
                  controller: _search,
                  textInputAction: TextInputAction.search,
                  onChanged: _demoMode ? (_) => setState(() {}) : null,
                  onSubmitted: (_) => _load(),
                  decoration: InputDecoration(
                    hintText: '搜索用户名或昵称',
                    prefixIcon: const Icon(Icons.search_rounded, size: 19),
                    filled: true,
                    fillColor: Colors.white,
                    isDense: true,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14),
                      borderSide: const BorderSide(color: line),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14),
                      borderSide: const BorderSide(color: line),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 13),
                decoration: cardDeco(radius: 14),
                child: Text(
                  '${users.length} 位',
                  style: const TextStyle(
                    color: green700,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            color: green700,
            onRefresh: _load,
            child: users.isEmpty
                ? ListView(children: const <Widget>[_EmptyState(text: '没有匹配的用户')])
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
                    itemCount: users.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 10),
                    itemBuilder: (_, index) => _userCard(users[index]),
                  ),
          ),
        ),
      ],
    );
  }

  Widget _userCard(AdminUser user) => Container(
    padding: const EdgeInsets.all(15),
    decoration: cardDeco(radius: 18),
    child: Row(
      children: <Widget>[
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: user.isAdmin ? green700 : (user.isBanned ? orange100 : green100),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Icon(
            user.isAdmin ? Icons.shield_rounded : Icons.person_rounded,
            color: user.isAdmin ? Colors.white : (user.isBanned ? orange : green700),
            size: 21,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Flexible(
                    child: Text(
                      user.display,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: ink,
                        fontSize: 14,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                  if (user.isAdmin) _badge('管理员', green100, green700),
                  if (user.isBanned) _badge('已封禁', orange100, orange),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                '@${user.username} · ${user.familySize} 人家庭 · 登录 ${user.loginCount} 次',
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: muted, fontSize: 10.5),
              ),
              const SizedBox(height: 3),
              Text(
                user.lastLoginAt == null ? '尚未登录' : '最近活动 ${_fmt(user.lastLoginAt)}',
                style: const TextStyle(color: muted, fontSize: 9.5),
              ),
            ],
          ),
        ),
        if (!user.isAdmin)
          _busyUserId == user.id
              ? const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2, color: green700),
                )
              : PopupMenuButton<String>(
                  tooltip: '账号操作',
                  onSelected: (_) => _toggleBan(user),
                  itemBuilder: (_) => <PopupMenuEntry<String>>[
                    PopupMenuItem<String>(
                      value: 'toggle',
                      child: Row(
                        children: <Widget>[
                          Icon(
                            user.isBanned ? Icons.lock_open_rounded : Icons.block_rounded,
                            size: 18,
                            color: user.isBanned ? green700 : orange,
                          ),
                          const SizedBox(width: 9),
                          Text(user.isBanned ? '解除封禁' : '封禁账号'),
                        ],
                      ),
                    ),
                  ],
                ),
      ],
    ),
  );

  Widget _logsView() {
    final logs = _onlyFailed ? _logs.where((log) => !log.success).toList() : _logs;
    return Column(
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 6, 16, 10),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: cardDeco(radius: 16),
            child: Row(
              children: <Widget>[
                const Icon(Icons.security_rounded, color: green700, size: 19),
                const SizedBox(width: 9),
                Expanded(
                  child: Text(
                    '共 ${logs.length} 条登录活动',
                    style: const TextStyle(
                      color: ink,
                      fontWeight: FontWeight.w800,
                      fontSize: 12,
                    ),
                  ),
                ),
                FilterChip(
                  label: const Text('只看失败'),
                  selected: _onlyFailed,
                  onSelected: (value) {
                    setState(() => _onlyFailed = value);
                    if (!_demoMode) _load();
                  },
                  selectedColor: orange100,
                  checkmarkColor: orange,
                  side: BorderSide(color: _onlyFailed ? orange : line),
                  labelStyle: TextStyle(
                    color: _onlyFailed ? orange : muted,
                    fontSize: 10.5,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            color: green700,
            onRefresh: _load,
            child: logs.isEmpty
                ? ListView(children: const <Widget>[_EmptyState(text: '没有符合条件的登录记录')])
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
                    itemCount: logs.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 9),
                    itemBuilder: (_, index) => Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14),
                      decoration: cardDeco(radius: 16),
                      child: _logTile(logs[index]),
                    ),
                  ),
          ),
        ),
      ],
    );
  }

  Widget _logTile(LoginLogEntry log, {bool compact = false}) => Padding(
    padding: EdgeInsets.symmetric(vertical: compact ? 11 : 14),
    child: Row(
      children: <Widget>[
        Container(
          width: 34,
          height: 34,
          decoration: BoxDecoration(
            color: log.success ? green100 : orange100,
            borderRadius: BorderRadius.circular(11),
          ),
          child: Icon(
            log.success ? Icons.login_rounded : Icons.warning_amber_rounded,
            color: log.success ? green700 : orange,
            size: 17,
          ),
        ),
        const SizedBox(width: 11),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                '${log.username} ${log.success ? '登录成功' : '登录失败'}',
                style: const TextStyle(
                  color: ink,
                  fontWeight: FontWeight.w800,
                  fontSize: 12.5,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                '${_fmt(log.createdAt)}${log.ip == null ? '' : ' · ${log.ip}'}',
                style: const TextStyle(color: muted, fontSize: 9.5),
              ),
              if (!compact && log.detail != null) ...<Widget>[
                const SizedBox(height: 4),
                Text(log.detail!, style: const TextStyle(color: orange, fontSize: 10)),
              ],
            ],
          ),
        ),
        _badge(
          log.success ? '正常' : '异常',
          log.success ? green100 : orange100,
          log.success ? green700 : orange,
        ),
      ],
    ),
  );

  Widget _sectionTitle(String title, String subtitle) => Row(
    crossAxisAlignment: CrossAxisAlignment.end,
    children: <Widget>[
      Text(
        title,
        style: const TextStyle(color: ink, fontWeight: FontWeight.w900, fontSize: 15),
      ),
      const SizedBox(width: 8),
      Text(subtitle, style: const TextStyle(color: muted, fontSize: 10)),
    ],
  );

  Widget _badge(String text, Color background, Color foreground) => Container(
    margin: const EdgeInsets.only(left: 6),
    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
    decoration: BoxDecoration(
      color: background,
      borderRadius: BorderRadius.circular(20),
    ),
    child: Text(
      text,
      style: TextStyle(color: foreground, fontSize: 9, fontWeight: FontWeight.w800),
    ),
  );

  Widget _errorView() => Center(
    child: Container(
      margin: const EdgeInsets.all(24),
      padding: const EdgeInsets.all(24),
      decoration: cardDeco(),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(Icons.lock_outline_rounded, color: orange, size: 38),
          const SizedBox(height: 12),
          Text(
            _error!,
            textAlign: TextAlign.center,
            style: const TextStyle(color: ink, height: 1.5),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('重新加载'),
          ),
        ],
      ),
    ),
  );

  String _fmt(DateTime? time) {
    if (time == null) return '时间未知';
    String two(int value) => value.toString().padLeft(2, '0');
    return '${two(time.month)}-${two(time.day)} ${two(time.hour)}:${two(time.minute)}';
  }
}

class _EmptyState extends StatelessWidget {
  final String text;

  const _EmptyState({required this.text});

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 80),
    child: Column(
      children: <Widget>[
        const Icon(Icons.inbox_outlined, color: muted, size: 36),
        const SizedBox(height: 10),
        Text(text, style: const TextStyle(color: muted, fontSize: 12)),
      ],
    ),
  );
}
