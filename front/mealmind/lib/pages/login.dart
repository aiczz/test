// 登录 / 注册页。
//
// 对应说明书的认证接口：POST /api/auth/login → {access_token, token_type}
//
// 「演示账号一键登录」是专门为答辩准备的 ——
// 评委不该被注册流程挡在门外，一步就要能进去看。

import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_config.dart';
import '../services/auth_store.dart';
import '../theme.dart';

class LoginPage extends StatefulWidget {
  final bool gateMode;
  final VoidCallback? onAuthenticated;

  const LoginPage({super.key, this.gateMode = false, this.onAuthenticated});

  /// 打开登录页；返回 true 表示登录成功。
  static Future<bool> open(BuildContext context) async {
    final ok = await Navigator.of(context)
        .push<bool>(MaterialPageRoute<bool>(builder: (_) => const LoginPage()));
    return ok ?? false;
  }

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final TextEditingController _username = TextEditingController();
  final TextEditingController _password = TextEditingController();
  final TextEditingController _phone = TextEditingController();
  final TextEditingController _code = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  bool _phoneMode = true;
  bool _registerMode = false;
  bool _busy = false;
  bool _obscure = true;
  bool _codeSent = false;
  int _countdown = 0;
  Timer? _timer;
  String? _error;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    _phone.dispose();
    _code.dispose();
    _timer?.cancel();
    super.dispose();
  }

  void _finishLogin() {
    _timer?.cancel();
    widget.onAuthenticated?.call();
    if (widget.gateMode) return;
    Navigator.of(context).pop(true);
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
      } else if (_phoneMode) {
        await AuthStore.instance.loginWithPhone(
          _phone.text.trim(),
          _code.text.trim(),
        );
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
      _finishLogin();
    } on AuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _busy = false;
      });
    }
  }

  void _switchLoginMode(bool phoneMode) {
    if (_busy || _phoneMode == phoneMode) return;
    setState(() {
      _phoneMode = phoneMode;
      _registerMode = false;
      _error = null;
    });
  }

  void _sendCode() {
    if (_busy || _countdown > 0) return;
    final phone = _phone.text.trim();
    if (!RegExp(r'^1\d{10}$').hasMatch(phone)) {
      setState(() => _error = '请输入正确的 11 位手机号');
      return;
    }

    _timer?.cancel();
    setState(() {
      _codeSent = true;
      _countdown = 60;
      _error = null;
    });
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || _countdown <= 1) {
        timer.cancel();
        if (mounted) setState(() => _countdown = 0);
        return;
      }
      setState(() => _countdown--);
    });

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('演示验证码已发送：123456'),
        behavior: SnackBarBehavior.floating,
        backgroundColor: green900,
      ),
    );
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
      appBar: widget.gateMode
          ? null
          : AppBar(
              backgroundColor: page,
              elevation: 0,
              leading: IconButton(
                icon: const Icon(Icons.close, color: ink),
                tooltip: '关闭',
                onPressed: () => Navigator.of(context).maybePop(),
              ),
            ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 430),
            child: ListView(
              padding: EdgeInsets.fromLTRB(
                22,
                widget.gateMode ? 34 : 0,
                22,
                28,
              ),
              children: [
                const _Brand(),
                const SizedBox(height: 24),
                _formCard(),
                if (!widget.gateMode) ...[
                  const SizedBox(height: 16),
                  const _BackendHint(),
                ] else ...[
                  const SizedBox(height: 18),
                  const Text(
                    '登录即表示你同意仅将账号用于保存饮食偏好与食材记录',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 10.5, color: muted),
                  ),
                ],
              ],
            ),
          ),
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
              _phoneMode ? '欢迎回来' : (_registerMode ? '注册新账号' : '账号登录'),
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w900,
                color: ink,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              _phoneMode
                  ? '使用手机号快速进入，保存你的食材与偏好'
                  : (_registerMode ? '注册后直接登录，不用再输一遍' : '登录后可以同步家庭档案、收藏和购物清单'),
              style: const TextStyle(fontSize: 11.5, color: muted),
            ),
            const SizedBox(height: 16),

            _loginModeTabs(),
            const SizedBox(height: 18),

            if (_phoneMode) ...[
              _phoneFields(),
            ] else ...[
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
            ],

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
                      _phoneMode ? '验证码登录' : (_registerMode ? '注册并登录' : '登录'),
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 14,
                      ),
                    ),
            ),

            if (!_phoneMode) ...[
              const SizedBox(height: 6),
              TextButton(
                onPressed: _busy ? null : _switchMode,
                child: Text(
                  _registerMode ? '已有账号？去登录' : '还没有账号？去注册',
                  style: const TextStyle(fontSize: 12, color: green700),
                ),
              ),
            ],

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

  Widget _loginModeTabs() {
    return Container(
      height: 44,
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: green50,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: line),
      ),
      child: Row(
        children: [
          Expanded(
            child: _LoginModeButton(
              selected: _phoneMode,
              icon: Icons.phone_android_rounded,
              label: '手机验证码',
              onTap: () => _switchLoginMode(true),
            ),
          ),
          const SizedBox(width: 4),
          Expanded(
            child: _LoginModeButton(
              selected: !_phoneMode,
              icon: Icons.person_outline_rounded,
              label: '账号密码',
              onTap: () => _switchLoginMode(false),
            ),
          ),
        ],
      ),
    );
  }

  Widget _phoneFields() {
    return Column(
      children: [
        _field(
          controller: _phone,
          label: '手机号',
          icon: Icons.phone_android_rounded,
          keyboardType: TextInputType.phone,
          maxLength: 11,
          validator: (value) {
            final text = (value ?? '').trim();
            if (text.isEmpty) return '请输入手机号';
            if (!RegExp(r'^1\d{10}$').hasMatch(text)) return '请输入正确的 11 位手机号';
            return null;
          },
        ),
        const SizedBox(height: 12),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: _field(
                controller: _code,
                label: '验证码',
                icon: Icons.shield_outlined,
                keyboardType: TextInputType.number,
                maxLength: 6,
                validator: (value) {
                  final text = (value ?? '').trim();
                  if (!_codeSent) return '请先获取验证码';
                  if (text.length != 6) return '请输入 6 位验证码';
                  return null;
                },
              ),
            ),
            const SizedBox(width: 10),
            SizedBox(
              width: 108,
              height: 52,
              child: OutlinedButton(
                onPressed: _countdown > 0 ? null : _sendCode,
                style: OutlinedButton.styleFrom(
                  foregroundColor: green700,
                  side: const BorderSide(color: green700),
                  padding: EdgeInsets.zero,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
                child: Text(
                  _countdown > 0 ? '${_countdown}s 后重发' : '获取验证码',
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        const Row(
          children: [
            Icon(Icons.info_outline_rounded, size: 14, color: muted),
            SizedBox(width: 5),
            Expanded(
              child: Text(
                '当前为演示短信通道，验证码固定为 123456',
                style: TextStyle(fontSize: 10.5, color: muted),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _field({
    required TextEditingController controller,
    required String label,
    required IconData icon,
    required String? Function(String?) validator,
    bool obscure = false,
    Widget? suffix,
    TextInputType? keyboardType,
    int? maxLength,
  }) {
    return TextFormField(
      controller: controller,
      obscureText: obscure,
      validator: validator,
      enabled: !_busy,
      keyboardType: keyboardType,
      maxLength: maxLength,
      style: const TextStyle(fontSize: 14, color: ink),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(fontSize: 13, color: muted),
        prefixIcon: Icon(icon, size: 18, color: green700),
        suffixIcon: suffix,
        counterText: '',
        filled: true,
        fillColor: green50,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 14,
        ),
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

class _LoginModeButton extends StatelessWidget {
  final bool selected;
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _LoginModeButton({
    required this.selected,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? Colors.white : Colors.transparent,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 16, color: selected ? green700 : muted),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                color: selected ? green700 : muted,
                fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
              ),
            ),
          ],
        ),
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
                const Icon(
                  Icons.check_circle_outline,
                  size: 15,
                  color: green700,
                ),
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
