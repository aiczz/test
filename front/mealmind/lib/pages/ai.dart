import 'package:flutter/material.dart';

import '../data/mock.dart';
import '../models/content.dart';
import '../services/recommender.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// =====================================================================
/// AI 助手页 · 小食
///
/// 这一页有两个层次：
///   1. 表面：一个对话界面（队友原型里的 aiPage）
///   2. 里子：★ 多智能体协作轨迹 ★
///
/// 第 2 点是整个项目"多智能体"唯一看得见的地方。
/// 答辩时点一下快捷提问，让评委亲眼看到 7 个 Agent 依次工作、
/// Critic 行使一票否决 —— 比说十句"我们用了多智能体"都有用。
/// =====================================================================

enum _Kind { user, ai, trace }

class _Item {
  final _Kind kind;
  final String text;
  final List<AgentStep> steps;
  final bool running;
  final String? recipeId; // AI 回复附带的推荐菜谱 id

  _Item.user(this.text)
      : kind = _Kind.user,
        steps = const <AgentStep>[],
        running = false,
        recipeId = null;

  _Item.ai(this.text, {this.recipeId})
      : kind = _Kind.ai,
        steps = const <AgentStep>[],
        running = false;

  _Item.trace(this.steps, this.running)
      : kind = _Kind.trace,
        text = '',
        recipeId = null;
}

class AiPage extends StatefulWidget {
  final String? initialPrompt;
  final int requestToken;

  const AiPage({
    super.key,
    this.initialPrompt,
    this.requestToken = 0,
  });

  @override
  State<AiPage> createState() => _AiPageState();
}

class _AiPageState extends State<AiPage> {
  final List<_Item> _items = <_Item>[];
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _items.add(_Item.ai(mockAiGreeting));
  }

  @override
  void didUpdateWidget(covariant AiPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.requestToken != oldWidget.requestToken &&
        widget.initialPrompt != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _send(widget.initialPrompt!);
      });
    }
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOut,
        );
      }
    });
  }

  /// 模拟一次完整的"多智能体协作 → 出推荐"
  Future<void> _send(String raw) async {
    final text = raw.trim();
    if (text.isEmpty || _busy) return;

    _input.clear();
    setState(() {
      _items.add(_Item.user(text));
      _busy = true;
    });
    _scrollToBottom();

    // ---- 协作轨迹逐步浮现 ----
    final growing = <AgentStep>[];
    setState(() => _items.add(_Item.trace(growing, true)));

    // ★ 轨迹用【真实家庭档案】生成：改了人数/预算/限钠，
    //   第一步读到的东西、以及 Critic 会不会否决，都会跟着变。
    for (final step in agentTraceFor(AppState.instance.profile)) {
      await Future<void>.delayed(const Duration(milliseconds: 380));
      if (!mounted) return;
      setState(() {
        growing.add(step);
        _items[_items.length - 1] =
            _Item.trace(List<AgentStep>.from(growing), true);
      });
      _scrollToBottom();
    }

    await Future<void>.delayed(const Duration(milliseconds: 420));
    if (!mounted) return;

    // ---- 轨迹定格，出推荐 ----
    setState(() {
      _items[_items.length - 1] =
          _Item.trace(List<AgentStep>.from(growing), false);
      _items.add(
        _Item.ai(
          text.contains('食材') ? mockAiReplyByFood : mockAiReplyDefault,
          recipeId: 'soup',
        ),
      );
      _busy = false;
    });
    _scrollToBottom();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Expanded(
              child: ListView(
                controller: _scroll,
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                children: [
                  _Header(onPrompt: _send),
                  const SizedBox(height: 18),
                  for (final item in _items) ...[
                    _ItemView(item: item),
                    const SizedBox(height: 12),
                  ],
                ],
              ),
            ),
            _InputBar(
              controller: _input,
              busy: _busy,
              onSend: () => _send(_input.text),
            ),
          ],
        ),
      ),
    );
  }
}

// =====================================================================
// 顶部：绿色渐变头 + 快捷提问
// =====================================================================

class _Header extends StatelessWidget {
  final ValueChanged<String> onPrompt;

  const _Header({required this.onPrompt});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [green700, green900],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(rBlock),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: Colors.white.withAlpha(46),
                  borderRadius: BorderRadius.circular(13),
                ),
                child: const Icon(Icons.auto_awesome,
                    color: Colors.white, size: 19),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '小食 AI 助手',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w900,
                        color: Colors.white,
                      ),
                    ),
                    SizedBox(height: 3),
                    Text(
                      '我会结合时令、人数和家中食材给你建议',
                      style: TextStyle(fontSize: 11.5, color: Color(0xCCFFFFFF)),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final p in mockAiQuickPrompts)
                GestureDetector(
                  onTap: () => onPrompt(p),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color: Colors.white.withAlpha(31),
                      border: Border.all(color: Colors.white.withAlpha(89)),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text(
                      p,
                      style: const TextStyle(
                        fontSize: 12,
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// 消息项
// =====================================================================

class _ItemView extends StatelessWidget {
  final _Item item;

  const _ItemView({required this.item});

  @override
  Widget build(BuildContext context) {
    switch (item.kind) {
      case _Kind.user:
        return Align(
          alignment: Alignment.centerRight,
          child: Container(
            constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width * 0.78,
            ),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
            decoration: BoxDecoration(
              color: green700,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Text(
              item.text,
              style: const TextStyle(
                fontSize: 14,
                color: Colors.white,
                height: 1.6,
              ),
            ),
          ),
        );

      case _Kind.ai:
        return Align(
          alignment: Alignment.centerLeft,
          child: Container(
            constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width * 0.86,
            ),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white,
              border: Border.all(color: line),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.text,
                  style: const TextStyle(
                    fontSize: 14,
                    color: ink,
                    height: 1.7,
                  ),
                ),
                if (item.recipeId != null) ...[
                  const SizedBox(height: 12),
                  _MiniRecipeCard(recipeId: item.recipeId!),
                ],
              ],
            ),
          ),
        );

      case _Kind.trace:
        return _TraceCard(steps: item.steps, running: item.running);
    }
  }
}

// =====================================================================
// 推荐卡片（AI 回复里附带的）
// =====================================================================

class _MiniRecipeCard extends StatelessWidget {
  final String recipeId;

  const _MiniRecipeCard({required this.recipeId});

  @override
  Widget build(BuildContext context) {
    Recipe? recipe;
    for (final r in mockRecipes) {
      if (r.id == recipeId) recipe = r;
    }
    if (recipe == null) return const SizedBox.shrink();

    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        border: Border.all(color: line),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: 110,
            width: double.infinity,
            child: Image.asset(recipe.image, fit: BoxFit.cover, filterQuality: FilterQuality.high),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  recipe.name,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    color: ink,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '${recipe.desc} · ${recipe.time} · ${recipe.people}',
                  style: const TextStyle(fontSize: 11.5, color: muted),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('已把「${recipe!.name}」加入今日菜单'),
                          duration: const Duration(milliseconds: 1400),
                          behavior: SnackBarBehavior.floating,
                          backgroundColor: const Color(0xFF163A26),
                          shape: const StadiumBorder(),
                        ),
                      );
                    },
                    style: FilledButton.styleFrom(
                      backgroundColor: orange,
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      shape: const StadiumBorder(),
                    ),
                    child: const Text(
                      '加入今日菜单',
                      style: TextStyle(
                        fontSize: 12.5,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// ★ 多智能体协作轨迹
// =====================================================================

class _TraceCard extends StatelessWidget {
  final List<AgentStep> steps;
  final bool running;

  const _TraceCard({required this.steps, required this.running});

  int get _totalMs =>
      steps.fold<int>(0, (sum, s) => sum + s.ms);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: green50,
        border: Border.all(color: green100),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ---- 标题栏 ----
          Row(
            children: [
              Icon(
                running ? Icons.sync : Icons.account_tree_outlined,
                size: 16,
                color: green700,
              ),
              const SizedBox(width: 7),
              Text(
                '多智能体协作',
                style: const TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w800,
                  color: green900,
                ),
              ),
              const Spacer(),
              Text(
                running
                    ? '协作中…'
                    : '${steps.length} 步 · ${(_totalMs / 1000).toStringAsFixed(2)} s',
                style: const TextStyle(fontSize: 10.5, color: green700),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // ---- 每一步 ----
          for (var i = 0; i < steps.length; i++)
            _TraceRow(
              step: steps[i],
              last: i == steps.length - 1 && !running,
            ),

          if (running)
            const Padding(
              padding: EdgeInsets.only(top: 6, left: 2),
              child: SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: green600,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _TraceRow extends StatelessWidget {
  final AgentStep step;
  final bool last;

  const _TraceRow({required this.step, required this.last});

  @override
  Widget build(BuildContext context) {
    final vetoed = step.status == 'veto';
    final info = step.status == 'info';

    final Color dotColor =
        vetoed ? orange : (info ? muted : green600);
    final IconData dotIcon = vetoed
        ? Icons.block
        : (info ? Icons.info_outline : Icons.check);

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 左侧：圆点 + 连接线
          Column(
            children: [
              Container(
                width: 18,
                height: 18,
                decoration: BoxDecoration(
                  color: vetoed ? orange100 : Colors.white,
                  border: Border.all(color: dotColor, width: 1.4),
                  shape: BoxShape.circle,
                ),
                child: Icon(dotIcon, size: 10, color: dotColor),
              ),
              if (!last)
                Expanded(
                  child: Container(width: 1.2, color: green100),
                ),
            ],
          ),
          const SizedBox(width: 10),
          // 右侧：内容
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: last ? 0 : 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          step.agent,
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w800,
                            color: vetoed ? orange : ink,
                          ),
                        ),
                      ),
                      Text(
                        '${step.ms} ms',
                        style: const TextStyle(
                            fontSize: 10, color: muted),
                      ),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Text(
                    step.summary,
                    style: const TextStyle(
                      fontSize: 11,
                      color: muted,
                      height: 1.55,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =====================================================================
// 输入栏
// =====================================================================

class _InputBar extends StatelessWidget {
  final TextEditingController controller;
  final bool busy;
  final VoidCallback onSend;

  const _InputBar({
    required this.controller,
    required this.busy,
    required this.onSend,
  });

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: line)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  onSubmitted: (_) => onSend(),
                  textInputAction: TextInputAction.send,
                  decoration: InputDecoration(
                    hintText: '问问今晚吃什么…',
                    hintStyle: const TextStyle(fontSize: 13.5, color: muted),
                    filled: true,
                    fillColor: const Color(0xFFF6F8F4),
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 12),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(999),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Material(
                color: busy ? muted : orange,
                shape: const CircleBorder(),
                child: InkWell(
                  customBorder: const CircleBorder(),
                  onTap: busy ? null : onSend,
                  child: const SizedBox(
                    width: 44,
                    height: 44,
                    child: Icon(Icons.send_rounded,
                        color: Colors.white, size: 19),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
