// 登录 / 注册页。
//
// 对应说明书的认证接口：POST /api/auth/login → {access_token, token_type}

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

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
  final TextEditingController _confirmPassword = TextEditingController();
  final TextEditingController _email = TextEditingController();
  final TextEditingController _code = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  bool _registerMode = true;
  bool _busy = false;
  bool _obscure = true;
  bool _obscureConfirm = true;
  bool _codeSent = false;
  int _countdown = 0;
  Timer? _timer;
  String? _error;

  @override
  void initState() {
    super.initState();
    // 上一段会话是被后端踢掉的（token 过期，或者账号被封禁）——
    // 登录门禁会把用户送回这里。原因必须显示出来，
    // 否则用户只会看到「莫名回到登录页」，不知道发生了什么。
    final notice = AuthStore.instance.notice;
    if (notice != null) {
      _error = notice;
      AuthStore.instance.clearNotice();
    }
  }

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    _confirmPassword.dispose();
    _email.dispose();
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

  Future<void> _submit() async {
    if (_busy) return;

    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      // 一条路走到底：注册 = 手机号 + 验证码 + 设个数字密码，注册成功后
      // 直接登录（不用再切回登录页）；登录 = 用户名 + 密码。
      if (_registerMode) {
        // 注册 = 邮箱 + 验证码 + 设个数字密码。
        final email = _email.text.trim();
        final code = _code.text.trim();
        await AuthStore.instance.registerEmail(email, code, _password.text);
        // ⚠️ 注册那一步已经把这条验证码消费掉了（一次性，防重放），
        //    所以不能拿它再登录。后端把 username 设成了邮箱，直接走密码登录。
        await AuthStore.instance.login(email, _password.text);
        if (!mounted) return;
        _finishLogin();
        return;
      } else {
        final name = _username.text.trim();
        final password = _password.text;
        await AuthStore.instance.login(name, password);
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

  Future<void> _sendCode() async {
    if (_busy || _countdown > 0) return;

    final email = _email.text.trim();
    if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)) {
      setState(() => _error = '请输入正确的邮箱地址');
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });

    String channel;
    try {
      channel = await AuthStore.instance.sendEmailCode(
        email,
        purpose: _registerMode ? 'register' : 'login',
      );
    } on AuthException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _busy = false;
      });
      return;
    }

    if (!mounted) return;
    setState(() {
      _codeSent = true;
      _countdown = 60;
      _busy = false;
    });

    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || _countdown <= 1) {
        timer.cancel();
        if (mounted) setState(() => _countdown = 0);
        return;
      }
      setState(() => _countdown--);
    });

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          channel == 'smtp'
              ? '验证码已发到 $email，请查收（含垃圾箱）'
              : '后端没配邮件通道，验证码打在了服务日志里',
        ),
        behavior: SnackBarBehavior.floating,
        backgroundColor: orange900,
      ),
    );
  }

  void _switchMode() {
    _timer?.cancel();
    _code.clear();
    _password.clear();
    _confirmPassword.clear();
    setState(() {
      _registerMode = !_registerMode;
      _codeSent = false;
      _countdown = 0;
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
              _registerMode ? '创建你的账号' : '欢迎回来',
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w900,
                color: ink,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              _registerMode ? '验证邮箱并设置数字密码，注册后即可登录' : '使用用户名和密码登录，继续你的饮食计划',
              style: const TextStyle(fontSize: 11.5, color: muted),
            ),
            const SizedBox(height: 18),

            // 注册用邮箱验证码（后端随机生成、5 分钟有效、有限流和防重放），
            // 登录用账号密码 —— 两条路各自独立，不需要「验证码 / 账号密码」
            // 那种切换 tab（widget_test 里也断言了页面上不该出现那两个字样）。
            if (_registerMode) ...[
              _emailFields(),
              const SizedBox(height: 12),
              _registrationPasswordFields(),
            ] else ...[
              _field(
                controller: _username,
                label: '用户名',
                icon: Icons.account_circle_outlined,
                validator: (value) {
                  final text = (value ?? '').trim();
                  if (text.isEmpty) return '请输入用户名';
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
                backgroundColor: orange700,
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
                      _registerMode ? '完成注册' : '登录',
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
                _registerMode ? '已有账号？去登录' : '还没有账号？先注册',
                style: const TextStyle(fontSize: 12, color: orange700),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _emailFields() {
    return Column(
      children: [
        _field(
          controller: _email,
          label: '邮箱',
          icon: Icons.alternate_email_rounded,
          keyboardType: TextInputType.emailAddress,
          validator: (value) {
            final text = (value ?? '').trim();
            if (text.isEmpty) return '请输入邮箱';
            if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(text)) {
              return '请输入正确的邮箱地址';
            }
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
                inputFormatters: <TextInputFormatter>[
                  FilteringTextInputFormatter.digitsOnly,
                ],
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
                  foregroundColor: orange700,
                  side: const BorderSide(color: orange700),
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
      ],
    );
  }

  Widget _registrationPasswordFields() {
    return Column(
      children: [
        _field(
          controller: _password,
          label: '设置密码（至少 6 位数字）',
          icon: Icons.lock_outline_rounded,
          obscure: _obscure,
          keyboardType: TextInputType.number,
          inputFormatters: <TextInputFormatter>[
            FilteringTextInputFormatter.digitsOnly,
          ],
          validator: _validateNumericPassword,
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
        const SizedBox(height: 12),
        _confirmPasswordField(),
      ],
    );
  }

  String? _validateNumericPassword(String? value) {
    final text = value ?? '';
    if (text.isEmpty) return '请设置密码';
    if (!RegExp(r'^\d{6,}$').hasMatch(text)) {
      return '密码须为不少于 6 位的数字';
    }
    return null;
  }

  Widget _confirmPasswordField() {
    return _field(
      controller: _confirmPassword,
      label: '确认密码',
      icon: Icons.verified_user_outlined,
      obscure: _obscureConfirm,
      keyboardType: TextInputType.number,
      inputFormatters: <TextInputFormatter>[
        FilteringTextInputFormatter.digitsOnly,
      ],
      validator: (value) {
        final text = value ?? '';
        if (text.isEmpty) return '请再次输入密码';
        if (text != _password.text) return '两次输入的密码不一致';
        return null;
      },
      suffix: IconButton(
        icon: Icon(
          _obscureConfirm ? Icons.visibility_off : Icons.visibility,
          size: 18,
          color: muted,
        ),
        tooltip: _obscureConfirm ? '显示确认密码' : '隐藏确认密码',
        onPressed: () => setState(() => _obscureConfirm = !_obscureConfirm),
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
    TextInputType? keyboardType,
    int? maxLength,
    List<TextInputFormatter>? inputFormatters,
  }) {
    return TextFormField(
      controller: controller,
      obscureText: obscure,
      validator: validator,
      enabled: !_busy,
      keyboardType: keyboardType,
      inputFormatters: inputFormatters,
      maxLength: maxLength,
      style: const TextStyle(fontSize: 14, color: ink),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(fontSize: 13, color: muted),
        prefixIcon: Icon(icon, size: 18, color: orange700),
        suffixIcon: suffix,
        counterText: '',
        filled: true,
        fillColor: orange50,
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
          borderSide: const BorderSide(color: orange700, width: 1.4),
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
            color: orange700,
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
            color: orange900,
            letterSpacing: -1.2,
            height: 1,
          ),
        ),
        const SizedBox(height: 6),
        const Text(
          '顺应时令 · 智慧饮食',
          style: TextStyle(
            fontSize: 10.5,
            color: orange700,
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
              color: orange100,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.check_circle_outline,
                  size: 15,
                  color: orange700,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '已连接后端 ${status.apiBase}',
                    style: const TextStyle(fontSize: 11, color: orange700),
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
                  color: orange50,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text(
                  'python -m uvicorn app.main:app --port 8000',
                  style: TextStyle(
                    fontSize: 10.5,
                    color: orange900,
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
