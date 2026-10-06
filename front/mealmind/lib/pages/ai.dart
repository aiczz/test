import 'package:flutter/material.dart';

import '../data/mock.dart';
import '../models/content.dart';
import '../services/api_config.dart';
import '../services/backend_api.dart';
import '../services/city.dart';
import '../services/recommender.dart';
import '../state/app_state.dart';
import '../state/today_menu.dart';
import '../theme.dart';
import '../widgets/ai_compose_sheet.dart';
import '../widgets/dish_photo.dart';

/// =====================================================================
/// AI 助手页 · 小食
///
/// 这一页有两个层次：
///   1. 表面：一个对话界面（队友原型里的 aiPage）
///   2. 里子：**推荐流程** —— 后端真实执行了哪几步、哪些菜被硬约束否决
///
/// ⚠️ 第 2 点以前叫「多智能体协作」，那是**不实的**：
///    项目里没有多智能体 —— 后端只是一串顺序执行的函数，外加**一次**
///    大模型调用；没有 agent 自主决策，也没有 agent 之间的通信。
///    现在按实际叫「推荐流程」，步骤名也改成「读取约束 / 需求解析 /
///    候选召回 / 硬约束否决 / 模型定稿」这种如实描述。
///
///    后端离线时退回本地规则，那份轨迹也重写成了如实描述本地做了什么
///    （见 `recommender.dart` 的 localTraceFor）—— 旧版本会写
///    「CP-SAT 求解完成，生成 3 个 Pareto 方案」，而 CP-SAT 根本没做。
/// =====================================================================

enum _Kind { user, ai, trace }

class _Item {
  final _Kind kind;
  final String text;
  final List<AgentStep> steps;
  final bool running;

  /// 这条回复是不是「因为后端请求失败而退回的本地文案」。
  ///
  /// ⚠️ 注意区分两种情况，之前混在一起导致了一个假警报：
  ///   · 开场问候语（mockAiGreeting）**本来就是本地写死的**，不是降级 ——
  ///     但它的 fromBackend 默认 false，于是界面在问候语下面写
  ///     「后端未连接，这是本地兜底回答」，哪怕后端完全正常。
  ///   · 真正的降级：这次提问请求失败（超时/断网/500），才该提示。
  /// 所以这里用单独的 `localFallback` 标记，只有真降级才为 true。
  final bool localFallback;

  /// 降级的具体原因（超时？连不上？后端 500？）—— 直接显示给用户，
  /// 比笼统的「后端未连接」有用得多。
  final String? fallbackReason;

  _Item.user(this.text)
    : kind = _Kind.user,
      steps = const <AgentStep>[],
      running = false,
      recipes = const <Recipe>[],
      localFallback = false,
      fallbackReason = null,
      fromBackend = true; // 用户自己的话无所谓降级

  /// 这条回复附带的推荐菜（后端会给，最多 3 道）。
  ///
  /// ⚠️ 以前只存了 `recipeId`，然后去 `ContentStore.recipes` 里查 ——
  ///    而 ContentStore 只保留「有配图」的菜，查不到就 `SizedBox.shrink()`，
  ///    于是**后端明明推荐了 3 道，界面上一个卡片都没有**（截图里就是这样）。
  ///    现在直接带上完整的 Recipe 对象，不再二次查询。
  final List<Recipe> recipes;

  _Item.ai(
    this.text, {
    this.recipes = const <Recipe>[],
    this.localFallback = false,
    this.fallbackReason,
  }) : kind = _Kind.ai,
       steps = const <AgentStep>[],
       running = false,
       fromBackend = true;

  _Item.trace(this.steps, this.running, {this.fromBackend = false})
    : kind = _Kind.trace,
      text = '',
      recipes = const <Recipe>[],
      localFallback = false,
      fallbackReason = null;

  /// 轨迹用：这份轨迹是不是后端返回的真实轨迹
  final bool fromBackend;
}

class AiPage extends StatefulWidget {
  final String? initialPrompt;
  final int requestToken;

  const AiPage({super.key, this.initialPrompt, this.requestToken = 0});

  @override
  State<AiPage> createState() => _AiPageState();
}

class _AiPageState extends State<AiPage> {
  final List<_Item> _items = <_Item>[];
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  bool _busy = false;

  /// 最近一次请求失败的原因（超时 / 连不上 / 后端 500 …），
  /// 显示在兜底回答下面，避免一律写成「后端未连接」误导排查。
  String? _lastChatError;

  /// 本次会话里【已经展示过】的菜品 id。
  ///
  /// 用途：用户说「换一批呢」时要避开这些 —— 否则后端每天的轮换因子是固定的，
  /// 重问一次还是那三道，用户会觉得「根本没换」。
  final Set<int> _shownRecipeIds = <int>{};

  /// 上一轮的意图。追问（「换一批」「还有别的吗」）本身不含推荐关键词，
  /// 带上它后端才知道该继续推荐，而不是当成闲聊。
  String? _lastIntent;

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

  /// 问一次 AI：先播协作轨迹，轨迹放完出结果。
  ///
  /// ★ 回答是**真的调后端** `/api/ai/chat` 拿的，不再是写死的字符串。
  ///   请求和轨迹动画**并行**开始 —— 动画是给人看的节奏，等它放完，
  ///   答案通常已经回来了，用户感觉不到在等网络。
  ///   后端离线（线上静态站的情形）时回落本地文案，界面照常能用。
  ///
  /// ★ 本次改动：后端现在会返回它**真实**做了什么的轨迹
  ///   （召回多少候选、哪些菜被忌口否决、模型耗时）。
  ///   拿到就用后端的覆盖掉本地那份「演示轨迹」——轨迹是给评委看的，
  ///   演的和真的必须能分清，所以界面上也会标注来源。
  Future<void> _send(String raw) async {
    final text = raw.trim();
    if (text.isEmpty || _busy) return;

    _input.clear();
    setState(() {
      _items.add(_Item.user(text));
      _busy = true;
    });
    _scrollToBottom();

    // 先把请求发出去，再放动画 —— 两者并行，谁也不等谁。
    final pending = _askBackend(text);

    // ---- 协作轨迹逐步浮现 ----
    final growing = <AgentStep>[];
    setState(() => _items.add(_Item.trace(growing, true)));

    // ★ 轨迹用【真实家庭档案】生成：改了人数/预算/限钠，
    //   第一步读到的东西、以及 Critic 会不会否决，都会跟着变。
    for (final step in localTraceFor(AppState.instance.profile)) {
      await Future<void>.delayed(const Duration(milliseconds: 380));
      if (!mounted) return;
      setState(() {
        growing.add(step);
        _items[_items.length - 1] = _Item.trace(
          List<AgentStep>.from(growing),
          true,
        );
      });
      _scrollToBottom();
    }

    await Future<void>.delayed(const Duration(milliseconds: 420));
    if (!mounted) return;

    final reply = await pending;
    if (!mounted) return;

    // 记住这一轮的意图 + 展示了哪些菜，供下一句追问使用
    if (reply != null) {
      if (reply.intent.isNotEmpty) _lastIntent = reply.intent;
      for (final recipe in reply.recipes) {
        final id = int.tryParse(recipe.id);
        if (id != null) _shownRecipeIds.add(id);
      }
    }

    // 后端给了真轨迹就用真的（它比本地这份「按档案展开」的信息量大得多）。
    // ⚠️ 这里必须写成 if/else：Dart 的类型提升只在当前作用域生效，
    //    先存一个 bool 再回头访问 `reply.trace` 会编译不过（reply 可能为 null）。
    final List<AgentStep> steps;
    final bool usedBackendTrace;
    if (reply != null && reply.hasBackendTrace) {
      steps = reply.trace;
      usedBackendTrace = true;
    } else {
      steps = List<AgentStep>.from(growing);
      usedBackendTrace = false;
    }

    // ---- 轨迹定格，出推荐 ----
    setState(() {
      _items[_items.length - 1] = _Item.trace(
        steps,
        false,
        fromBackend: usedBackendTrace,
      );
      _items.add(
        _Item.ai(
          (reply != null && reply.answer.isNotEmpty)
              ? reply.answer
              : _localAnswer(text),
          // ★ 直接把后端返回的菜带进气泡 —— 以前只留 id 再去本地内容库查，
          //   而本地内容库只保留「有配图」的菜，查不到就整块消失，
          //   于是后端推荐了 3 道、界面上一张卡片都没有。
          recipes: (reply != null && reply.recipes.isNotEmpty)
              ? reply.recipes
              : const <Recipe>[],
          localFallback: reply == null,
          fallbackReason: reply == null ? _lastChatError : null,
        ),
      );
      _busy = false;
    });
    _scrollToBottom();
  }

  /// 本地兜底文案（后端离线、或这一问失败时用）。
  String _localAnswer(String text) =>
      text.contains('食材') ? mockAiReplyByFood : mockAiReplyDefault;

  /// 问后端。任何失败都返回 null，交给调用方回落本地 ——
  /// 表现和后端离线时完全一致，界面不会弹错误。
  ///
  /// 本次把家庭硬约束一起带上：后端才能按忌口/限钠/可用时间真的筛候选，
  /// 而不是只在文案里提一嘴。
  ///
  /// ★ 同时把**失败原因**记到 `_lastChatError`：以前不管是超时、断网还是
  ///   后端 500，界面一律显示「后端未连接」—— 那句话经常是错的，
  ///   而且把排查方向带偏（明明连得上，只是模型这一问慢了点）。
  Future<AiChatResult?> _askBackend(String message) async {
    if (!BackendStatus.instance.online) {
      _lastChatError = '后端未连接（${BackendStatus.instance.apiBase}）';
      return null;
    }
    try {
      final profile = AppState.instance.profile;
      return await BackendApi.instance.chat(
        message,
        city: CityStore.instance.city.name,
        people: profile.people,
        cookMinutes: profile.cookMinutes,
        lowSodium: profile.lowSodium,
        preferences: profile.preferences.toList(),
        avoid: profile.avoid.toList(),
        // ★ 会话上下文：追问靠它才不会被当成闲聊
        lastIntent: _lastIntent,
        recentRecipeIds: _shownRecipeIds.toList(),
      );
    } catch (error) {
      // 注意：这里不 import dio —— 网络错误统一由 service 层翻译成人话，
      // 界面层不碰 DioException 类型。
      _lastChatError = describeNetworkError(error);
      return null;
    }
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
          colors: [orange700, orange900],
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
                child: const Icon(
                  Icons.auto_awesome,
                  color: Colors.white,
                  size: 19,
                ),
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
                      style: TextStyle(
                        fontSize: 11.5,
                        color: Color(0xCCFFFFFF),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // ★ 配菜入口：这是「导航栏 AI 模块接上 AI」的落点。
          //   它和下面的对话是两条不同的路径 ——
          //   对话是「你说一句、我答一句」，配菜是「把结构化条件交给我算」。
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () => showAiComposeSheet(context),
              icon: const Icon(Icons.ramen_dining_rounded, size: 17),
              label: const Text(
                '用我的食材配这一餐',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13),
              ),
              style: FilledButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: orange900,
                padding: const EdgeInsets.symmetric(vertical: 12),
                shape: const StadiumBorder(),
              ),
            ),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final p in mockAiQuickPrompts)
                GestureDetector(
                  onTap: () => onPrompt(p),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 8,
                    ),
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
              color: orange700,
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
                  style: const TextStyle(fontSize: 14, color: ink, height: 1.7),
                ),
                if (item.localFallback) ...[
                  const SizedBox(height: 6),
                  Text(
                    item.fallbackReason == null
                        ? '（后端未连接，这是本地兜底回答）'
                        : '（${item.fallbackReason}，这是本地兜底回答）',
                    style: const TextStyle(fontSize: 10.5, color: muted),
                  ),
                ],
                if (item.recipes.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  for (final recipe in item.recipes) ...[
                    _MiniRecipeCard(recipe: recipe),
                    const SizedBox(height: 10),
                  ],
                ],
              ],
            ),
          ),
        );

      case _Kind.trace:
        return _TraceCard(
          steps: item.steps,
          running: item.running,
          isBackend: item.fromBackend,
        );
    }
  }
}

// =====================================================================
// 推荐卡片（AI 回复里附带的）
// =====================================================================

class _MiniRecipeCard extends StatelessWidget {
  /// 直接接收后端返回的 Recipe —— 不再去 ContentStore 里按 id 反查。
  /// （反查会失败：ContentStore 只保留「有配图」的菜，查不到就整块消失。）
  final Recipe recipe;

  const _MiniRecipeCard({required this.recipe});

  @override
  Widget build(BuildContext context) {
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
            child: DishPhoto(asset: recipe.image),
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
                      // 真的写进今日菜单（菜谱页右侧那个 tab 能看到），
                      // 不再只是弹一句提示就没了。
                      final picked = recipe;
                      final added = TodayMenuStore.instance.add(picked);
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(
                            added
                                ? '已把「${picked.name}」加入今日菜单'
                                : '「${picked.name}」已经在今日菜单里了',
                          ),
                          duration: const Duration(milliseconds: 1400),
                          behavior: SnackBarBehavior.floating,
                          backgroundColor: orange900,
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

  /// 这份轨迹是后端真实执行的，还是前端按家庭档案「展开」的演示版。
  /// 两者都要给评委看，但不能混为一谈 —— 所以界面上必须写清是哪种。
  final bool isBackend;

  const _TraceCard({
    required this.steps,
    required this.running,
    this.isBackend = false,
  });

  int get _totalMs => steps.fold<int>(0, (sum, s) => sum + s.ms);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: orange50,
        border: Border.all(color: orange100),
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
                color: orange700,
              ),
              const SizedBox(width: 7),
              Text(
                // ⚠️ 这里以前写的是「多智能体协作」—— 那是**不实的**。
                //    项目里没有多智能体：后端只是一串顺序执行的函数
                //    （外加一次大模型调用），没有 agent 自主决策、没有 agent 间通信。
                //    如实写「推荐流程」，步骤名写清每步在干什么。
                running ? '正在处理' : '推荐流程',
                style: const TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w800,
                  color: orange900,
                ),
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  running ? '协作中…' : (isBackend ? '后端真实轨迹' : '本地演示轨迹'),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    color: isBackend && !running ? orange700 : muted,
                  ),
                ),
              ),
              const Spacer(),
              Text(
                running
                    ? ''
                    : '${steps.length} 步 · ${(_totalMs / 1000).toStringAsFixed(2)} s',
                style: const TextStyle(fontSize: 10.5, color: orange700),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // ---- 每一步 ----
          for (var i = 0; i < steps.length; i++)
            _TraceRow(step: steps[i], last: i == steps.length - 1 && !running),

          if (running)
            const Padding(
              padding: EdgeInsets.only(top: 6, left: 2),
              child: SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: orange700,
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

    final Color dotColor = vetoed ? orange : (info ? muted : orange700);
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
                Expanded(child: Container(width: 1.2, color: orange100)),
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
                        style: const TextStyle(fontSize: 10, color: muted),
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
                    fillColor: orange50,
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 12,
                    ),
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
                    child: Icon(
                      Icons.send_rounded,
                      color: Colors.white,
                      size: 19,
                    ),
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
