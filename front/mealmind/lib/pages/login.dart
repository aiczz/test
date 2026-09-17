// 登录 / 注册页。
//
// 对应说明书的认证接口：POST /api/auth/login → {access_token, token_type}
//
// 「演示账号一键登录」是专门为答辩准备的 ——
// 评委不该被注册流程挡在门外，一步就要能进去看。

import 'package:flutter/material.dart';

import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../theme.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  /// 打开登录页；返回 true 表示登录成功。
  static Future<bool> open(BuildContext context) async {
    final ok = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(builder: (_) => const LoginPage()),
    );
    return ok ?? false;
  }

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final TextEditingController _username = TextEditingController();
  final TextEditingController _password = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  bool _registerMode = false;
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit({bool demo = false}) async {
    if (_busy) return;

    if (!demo && !(_formKey.currentState?.validate() ?? false)) return;

    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      if (demo) {
        await AuthStore.instance.loginAsDemo();
      } else {
        final name = _username.text.trim();
        final password = _password.text;
        if (_registerMode) {
          await AuthStore.instance.register(name, password);
        } else {
          await AuthStore.instance.login(name, password);
        }
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on AuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _busy = false;
      });
    }
  }

  void _switchMode() {
    setState(() {
      _registerMode = !_registerMode;
      _error = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: page,
      appBar: AppBar(
        backgroundColor: page,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.close, color: ink),
          tooltip: '关闭',
          onPressed: () => Navigator.of(context).maybePop(),
        ),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(22, 0, 22, 28),
          children: [
            const _Brand(),
            const SizedBox(height: 24),
            _formCard(),
            const SizedBox(height: 16),
            const _BackendHint(),
          ],
        ),
      ),
    );
  }

  Widget _formCard() {
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 20),
      decoration: cardDeco(),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _registerMode ? '注册新账号' : '登录',
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w900,
                color: ink,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              _registerMode ? '注册后直接登录，不用再输一遍' : '登录后可以同步家庭档案、收藏和购物清单',
              style: const TextStyle(fontSize: 11.5, color: muted),
            ),
            const SizedBox(height: 18),

            _field(
              controller: _username,
              label: '用户名',
              icon: Icons.person_outline,
              validator: (value) {
                final text = (value ?? '').trim();
                if (text.isEmpty) return '请输入用户名';
                if (text.length < 2) return '用户名至少 2 位';
                return null;
              },
            ),
            const SizedBox(height: 12),
            _field(
              controller: _password,
              label: '密码',
              icon: Icons.lock_outline,
              obscure: _obscure,
              validator: (value) {
                final text = value ?? '';
                if (text.isEmpty) return '请输入密码';
                if (text.length < 6) return '密码至少 6 位';
                return null;
              },
              suffix: IconButton(
                icon: Icon(
                  _obscure ? Icons.visibility_off : Icons.visibility,
                  size: 18,
                  color: muted,
                ),
                tooltip: _obscure ? '显示密码' : '隐藏密码',
                onPressed: () => setState(() => _obscure = !_obscure),
              ),
            ),

            if (_error != null) ...[
              const SizedBox(height: 14),
              _errorBox(_error!),
            ],

            const SizedBox(height: 18),
            FilledButton(
              onPressed: _busy ? null : () => _submit(),
              style: FilledButton.styleFrom(
                backgroundColor: green700,
                padding: const EdgeInsets.symmetric(vertical: 15),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              child: _busy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : Text(
                      _registerMode ? '注册并登录' : '登录',
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 14,
                      ),
                    ),
            ),

            const SizedBox(height: 6),
            TextButton(
              onPressed: _busy ? null : _switchMode,
              child: Text(
                _registerMode ? '已有账号？去登录' : '还没有账号？去注册',
                style: const TextStyle(fontSize: 12, color: green700),
              ),
            ),

            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Row(
                children: [
                  Expanded(child: Divider(color: line)),
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: 10),
                    child: Text(
                      '或者',
                      style: TextStyle(fontSize: 11, color: muted),
                    ),
                  ),
                  Expanded(child: Divider(color: line)),
                ],
              ),
            ),

            OutlinedButton.icon(
              onPressed: _busy ? null : () => _submit(demo: true),
              icon: const Icon(Icons.bolt, size: 18, color: orange),
              label: const Text(
                '使用演示账号一键登录',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13),
              ),
              style: OutlinedButton.styleFrom(
                foregroundColor: ink,
                side: const BorderSide(color: orange),
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '演示账号：demo / shishi2026',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 10.5, color: muted),
            ),
          ],
        ),
      ),
    );
  }

  Widget _field({
    required TextEditingController controller,
    required String label,
    required IconData icon,
    required String? Function(String?) validator,
    bool obscure = false,
    Widget? suffix,
  }) {
    return TextFormField(
      controller: controller,
      obscureText: obscure,
      validator: validator,
      enabled: !_busy,
      style: const TextStyle(fontSize: 14, color: ink),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(fontSize: 13, color: muted),
        prefixIcon: Icon(icon, size: 18, color: green700),
        suffixIcon: suffix,
        filled: true,
        fillColor: green50,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: green700, width: 1.4),
        ),
      ),
    );
  }

  Widget _errorBox(String message) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: orange100,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: orange),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.error_outline, size: 16, color: orange),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(fontSize: 11.5, color: ink, height: 1.5),
            ),
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// 品牌区
// =====================================================================

class _Brand extends StatelessWidget {
  const _Brand();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          width: 62,
          height: 62,
          decoration: BoxDecoration(
            color: green700,
            borderRadius: BorderRadius.circular(20),
            boxShadow: cardShadow,
          ),
          child: const Icon(Icons.rice_bowl, size: 32, color: cream),
        ),
        const SizedBox(height: 14),
        const Text(
          '食时',
          style: TextStyle(
            fontSize: 27,
            fontWeight: FontWeight.w900,
            color: green900,
            letterSpacing: -1.2,
            height: 1,
          ),
        ),
        const SizedBox(height: 6),
        const Text(
          '顺应时令 · 智慧饮食',
          style: TextStyle(
            fontSize: 10.5,
            color: green700,
            fontWeight: FontWeight.w600,
            letterSpacing: 1.2,
          ),
        ),
      ],
    );
  }
}

// =====================================================================
// 后端未连接时的提示
//
// 线上 PWA 永远连不上本机后端（浏览器的 mixed content 限制），
// 所以这里不是"报错"，而是告诉你怎么把本地后端跑起来。
// =====================================================================

class _BackendHint extends StatelessWidget {
  const _BackendHint();

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: BackendStatus.instance,
      builder: (context, _) {
        final status = BackendStatus.instance;
        if (status.online) {
          return Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: green100,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                const Icon(Icons.check_circle_outline, size: 15, color: green700),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '已连接后端 ${status.apiBase}',
                    style: const TextStyle(fontSize: 11, color: green700),
                  ),
                ),
              ],
            ),
          );
        }

        return Container(
          padding: const EdgeInsets.all(13),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: line),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.info_outline, size: 15, color: muted),
                  const SizedBox(width: 7),
                  const Text(
                    '还没连上后端',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w800,
                      color: ink,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                '界面现在用的是本地演示数据，功能都能看。\n'
                '想连真后端，在 back/ 目录执行：',
                style: TextStyle(fontSize: 11, color: muted, height: 1.6),
              ),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: green50,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text(
                  'python -m uvicorn app.main:app --port 8000',
                  style: TextStyle(
                    fontSize: 10.5,
                    color: green900,
                    fontFamily: 'monospace',
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '当前尝试的地址：${BackendStatus.instance.apiBase}\n'
                '（Android 模拟器会自动用 10.0.2.2；真机需要改成电脑的局域网 IP）',
                style: const TextStyle(fontSize: 10, color: muted, height: 1.6),
              ),
            ],
          ),
        );
      },
    );
  }
}
