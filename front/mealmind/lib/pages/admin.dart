// 管理员控制台。
//
// 「我的」页只在 is_admin 时显示入口，但真正的权限校验在后端 ——
// 普通用户即使摸到这个页面，所有请求也会拿到 403，页面会显示
// 「当前账号没有管理员权限」而不是白屏。
//
// 视觉沿用队友的设计稿：白卡片 + 1px 边线 + 20 圆角（theme.dart 的 cardDeco）。

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../services/backend_api.dart';
import '../theme.dart';

class AdminPage extends StatefulWidget {
  const AdminPage({super.key});

  static Future<void> open(BuildContext context) => Navigator.of(context).push(
    MaterialPageRoute<void>(builder: (_) => const AdminPage()),
  );

  @override
  State<AdminPage> createState() => _AdminPageState();
}

class _AdminPageState extends State<AdminPage>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 2, vsync: this);
  final TextEditingController _search = TextEditingController();

  AdminStats? _stats;
  List<AdminUser> _users = const <AdminUser>[];
  List<LoginLogEntry> _logs = const <LoginLogEntry>[];

  bool _loading = true;
  bool _onlyFailed = false;
  String? _error;
  // 正在处理中的用户 id，避免连点两次封禁
  int? _busyUserId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _tabs.dispose();
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final stats = await BackendApi.instance.fetchAdminStats();
      final users = await BackendApi.instance.fetchAdminUsers(
        keyword: _search.text.trim().isEmpty ? null : _search.text.trim(),
      );
      final logs = await BackendApi.instance.fetchLoginLogs(
        onlyFailed: _onlyFailed,
      );
      if (!mounted) return;
      setState(() {
        _stats = stats;
        _users = users.items;
        _logs = logs.items;
        _loading = false;
      });
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.response?.statusCode == 403
            ? '当前账号没有管理员权限'
            : '加载失败：${error.response?.statusCode ?? error.message}';
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = '加载失败：$error';
        _loading = false;
      });
    }
  }

  Future<void> _toggleBan(AdminUser user) async {
    if (_busyUserId != null) return;
    setState(() => _busyUserId = user.id);
    try {
      await BackendApi.instance.setUserBanned(
        user.id,
        banned: !user.isBanned,
      );
      if (!mounted) return;
      _toast(user.isBanned ? '已解封 ${user.username}' : '已封禁 ${user.username}');
      await _load();
    } on DioException catch (error) {
      if (!mounted) return;
      final detail = error.response?.data;
      final message = (detail is Map && detail['detail'] is String)
          ? detail['detail'] as String
          : '操作失败（${error.response?.statusCode ?? error.message}）';
      _toast(message);
    } finally {
      if (mounted) setState(() => _busyUserId = null);
    }
  }

  void _toast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        backgroundColor: const Color(0xFF163A26),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: page,
      appBar: AppBar(
        backgroundColor: page,
        elevation: 0,
        foregroundColor: ink,
        title: const Text(
          '管理员控制台',
          style: TextStyle(fontWeight: FontWeight.w900, fontSize: 17),
        ),
        bottom: TabBar(
          controller: _tabs,
          labelColor: green700,
          unselectedLabelColor: muted,
          indicatorColor: green700,
          labelStyle: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13),
          tabs: const <Widget>[
            Tab(text: '用户'),
            Tab(text: '登录记录'),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: green700))
          : _error != null
          ? _errorView()
          : Column(
              children: <Widget>[
                if (_stats != null) _statsGrid(_stats!),
                Expanded(
                  child: TabBarView(
                    controller: _tabs,
                    children: <Widget>[_usersTab(), _logsTab()],
                  ),
                ),
              ],
            ),
    );
  }

  Widget _errorView() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(Icons.lock_outline, size: 40, color: muted),
            const SizedBox(height: 14),
            Text(
              _error!,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 13, color: ink, height: 1.6),
            ),
            const SizedBox(height: 18),
            OutlinedButton(onPressed: _load, child: const Text('重试')),
          ],
        ),
      ),
    );
  }

  // ---------------------------------------------------------------- 统计

  Widget _statsGrid(AdminStats stats) {
    final cells = <(String, int, Color)>[
      ('用户总数', stats.totalUsers, green700),
      ('今日新增', stats.newUsersToday, green700),
      ('今日活跃', stats.activeUsersToday, green700),
      ('已封禁', stats.bannedUsers, stats.bannedUsers > 0 ? orange : muted),
      ('登录总次数', stats.totalLogins, muted),
      ('今日登录', stats.loginsToday, muted),
      ('今日失败', stats.failedLoginsToday,
          stats.failedLoginsToday > 0 ? orange : muted),
      ('管理员', stats.adminUsers, muted),
    ];

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
      child: Wrap(
        spacing: 9,
        runSpacing: 9,
        children: <Widget>[
          for (final (label, value, color) in cells)
            SizedBox(
              width: (MediaQuery.of(context).size.width - 32 - 27) / 4,
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 11, horizontal: 8),
                decoration: cardDeco(radius: 14),
                child: Column(
                  children: <Widget>[
                    Text(
                      '$value',
                      style: TextStyle(
                        fontSize: 19,
                        fontWeight: FontWeight.w900,
                        color: color,
                        height: 1.1,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      label,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 9.5, color: muted),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------- 用户

  Widget _usersTab() {
    return Column(
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
          child: TextField(
            controller: _search,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _load(),
            style: const TextStyle(fontSize: 13),
            decoration: InputDecoration(
              hintText: '按用户名 / 昵称搜索',
              hintStyle: const TextStyle(fontSize: 12, color: muted),
              prefixIcon: const Icon(Icons.search, size: 18, color: muted),
              suffixIcon: _search.text.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.close, size: 16, color: muted),
                      onPressed: () {
                        _search.clear();
                        _load();
                      },
                    ),
              isDense: true,
              filled: true,
              fillColor: Colors.white,
              contentPadding: const EdgeInsets.symmetric(vertical: 11),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: line),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: line),
              ),
            ),
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            color: green700,
            onRefresh: _load,
            child: _users.isEmpty
                ? ListView(
                    children: const <Widget>[
                      SizedBox(height: 60),
                      Center(
                        child: Text(
                          '没有匹配的用户',
                          style: TextStyle(fontSize: 13, color: muted),
                        ),
                      ),
                    ],
                  )
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(16, 6, 16, 24),
                    itemCount: _users.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 9),
                    itemBuilder: (context, index) => _userCard(_users[index]),
                  ),
          ),
        ),
      ],
    );
  }

  Widget _userCard(AdminUser user) {
    final busy = _busyUserId == user.id;

    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
      decoration: cardDeco(radius: 16),
      child: Row(
        children: <Widget>[
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: user.isBanned
                  ? orange100
                  : (user.isAdmin ? green700 : green100),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              user.isAdmin ? Icons.shield_moon_outlined : Icons.person_outline,
              size: 18,
              color: user.isBanned
                  ? orange
                  : (user.isAdmin ? Colors.white : green700),
            ),
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Flexible(
                      child: Text(
                        user.username,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w800,
                          color: ink,
                        ),
                      ),
                    ),
                    if (user.isAdmin) ...<Widget>[
                      const SizedBox(width: 6),
                      _chip('管理员', green100, green700),
                    ],
                    if (user.isBanned) ...<Widget>[
                      const SizedBox(width: 6),
                      _chip('已封禁', orange100, orange),
                    ],
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  '登录 ${user.loginCount} 次'
                  '${user.lastLoginAt == null ? '' : ' · 最近 ${_fmt(user.lastLoginAt)}'}',
                  style: const TextStyle(fontSize: 10.5, color: muted),
                ),
              ],
            ),
          ),
          const SizedBox(width: 6),
          // 管理员账号不给封禁按钮 —— 后端也会拦（400），
          // 前端直接不显示，省得用户点了才知道不行
          if (!user.isAdmin)
            busy
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: green700,
                    ),
                  )
                : TextButton(
                    onPressed: () => _toggleBan(user),
                    style: TextButton.styleFrom(
                      foregroundColor: user.isBanned ? green700 : orange,
                      padding: const EdgeInsets.symmetric(horizontal: 10),
                      minimumSize: const Size(0, 34),
                      visualDensity: VisualDensity.compact,
                    ),
                    child: Text(
                      user.isBanned ? '解封' : '封禁',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------- 登录记录

  Widget _logsTab() {
    return Column(
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Row(
            children: <Widget>[
              const Icon(Icons.history, size: 15, color: muted),
              const SizedBox(width: 6),
              Text(
                '共 ${_logs.length} 条',
                style: const TextStyle(fontSize: 11.5, color: muted),
              ),
              const Spacer(),
              // 只看失败 —— 刷密码的行为一眼就能看出来
              FilterChip(
                label: const Text('只看失败', style: TextStyle(fontSize: 11)),
                selected: _onlyFailed,
                onSelected: (value) {
                  setState(() => _onlyFailed = value);
                  _load();
                },
                selectedColor: orange100,
                checkmarkColor: orange,
                labelStyle: TextStyle(
                  color: _onlyFailed ? orange : muted,
                  fontWeight: FontWeight.w700,
                ),
                side: BorderSide(color: _onlyFailed ? orange : line),
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            color: green700,
            onRefresh: _load,
            child: _logs.isEmpty
                ? ListView(
                    children: const <Widget>[
                      SizedBox(height: 60),
                      Center(
                        child: Text(
                          '还没有登录记录',
                          style: TextStyle(fontSize: 13, color: muted),
                        ),
                      ),
                    ],
                  )
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(16, 6, 16, 24),
                    itemCount: _logs.length,
                    separatorBuilder: (_, _) =>
                        const Divider(height: 1, color: line),
                    itemBuilder: (context, index) => _logRow(_logs[index]),
                  ),
          ),
        ),
      ],
    );
  }

  Widget _logRow(LoginLogEntry log) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            log.success ? Icons.check_circle : Icons.cancel,
            size: 15,
            color: log.success ? green700 : orange,
          ),
          const SizedBox(width: 9),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Text(
                      log.username,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: ink,
                      ),
                    ),
                    const SizedBox(width: 8),
                    if (log.detail != null)
                      Flexible(
                        child: Text(
                          log.detail!,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 10.5, color: orange),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(
                  '${_fmt(log.createdAt)}'
                  '${log.ip == null ? '' : ' · ${log.ip}'}',
                  style: const TextStyle(fontSize: 10, color: muted),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------- 小工具

  Widget _chip(String text, Color bg, Color fg) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(rTag),
      ),
      child: Text(
        text,
        style: TextStyle(fontSize: 9.5, color: fg, fontWeight: FontWeight.w700),
      ),
    );
  }

  /// 后端存的是 UTC，这里已经转成本地时间了
  String _fmt(DateTime? time) {
    if (time == null) return '时间未知';
    String two(int value) => value.toString().padLeft(2, '0');
    return '${two(time.month)}-${two(time.day)} ${two(time.hour)}:${two(time.minute)}';
  }
}
