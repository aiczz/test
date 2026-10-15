import 'package:dio/dio.dart' show CancelToken;
import 'package:flutter/material.dart';

import '../data/mock.dart';
import '../models/content.dart';
import '../services/api_config.dart';
import '../services/backend_api.dart';
import '../services/city.dart';
import '../services/auth_store.dart';
import '../services/chat_session_store.dart';
import '../state/app_state.dart';
import '../state/today_menu.dart';
import '../theme.dart';
import '../widgets/ai_compose_sheet.dart';
import '../widgets/dish_photo.dart';
import '../widgets/food_photo.dart';
import '../widgets/add_food_to_pantry.dart';

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
      foods = const <Food>[],
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

  /// 这条回复附带的推荐**食材**（`intent == 'recommend_foods'` 时才有）。
  ///
  /// 和 `recipes` 是一样的道理：直接带上完整对象，不去 ContentStore 二次查询
  /// —— 那样会「后端明明推了 3 样，界面上一张卡都没有」。
  final List<Food> foods;

  _Item.ai(
    this.text, {
    this.recipes = const <Recipe>[],
    this.foods = const <Food>[],
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
      foods = const <Food>[],
      localFallback = false,
      fallbackReason = null;

  /// 轨迹用：这份轨迹是不是后端返回的真实轨迹
  final bool fromBackend;
}

class AiPage extends StatefulWidget {
  final String? initialPrompt;
  final int requestToken;
  final Future<AiChatResult?> Function(String message, bool useAi)? request;

  const AiPage({
    super.key,
    this.initialPrompt,
    this.requestToken = 0,
    this.request,
  });

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

  /// 本次会话里【已经展示过】的**食材** id（推荐食材那条链路用）。
  /// 和 _shownRecipeIds 分开：食材和菜品是两套 id 空间，混用会误排除。
  CancelToken? _chatCancel;
  int _requestGeneration = 0;

  void _stopWaiting() {
    _requestGeneration++;
    _chatCancel?.cancel('用户停止等待');
    setState(() {
      _busy = false;
      if (_items.isNotEmpty) {
        _items[_items.length - 1] = _Item.trace(const [], false);
      }
      _items.add(_Item.ai('已停止等待。你可以修改条件后重新提问。'));
    });
  }

  final Set<int> _shownFoodIds = <int>{};

  /// 上一轮的意图。追问（「换一批」「还有别的吗」）本身不含推荐关键词，
  /// 带上它后端才知道该继续推荐，而不是当成闲聊。
  String? _lastIntent;
  Map<String, dynamic>? _conversationState;
  Map<String, dynamic>? _effectiveContext;
  List<String> _excludedCategories = <String>[];
  String? _sessionScope;

  String get _currentScope =>
      '${BackendStatus.instance.apiBase}:${AuthStore.instance.user?.id ?? 'guest'}';

  Future<void> _restoreSession() async {
    final scope = _currentScope;
    if (_sessionScope == scope) return;
    Map<String, dynamic>? saved;
    try {
      saved = await ChatSessionStore.load(scope);
    } catch (_) {
      // Browsers can disable local storage; the in-tab session still works.
      saved = null;
    }
    if (!mounted || _currentScope != scope) return;
    _sessionScope = scope;
    _conversationState = saved?['state'] as Map<String, dynamic>?;
    _effectiveContext = saved?['effective'] as Map<String, dynamic>?;
    _lastIntent = saved?['intent'] as String?;
    _shownRecipeIds.clear();
    _shownFoodIds.clear();
    _shownRecipeIds.addAll(
      ((saved?['recipes'] as List?) ?? []).whereType<int>(),
    );
    _shownFoodIds.addAll(((saved?['foods'] as List?) ?? []).whereType<int>());
    _excludedCategories = ((saved?['categories'] as List?) ?? [])
        .whereType<String>()
        .toList();
    setState(() {});
  }

  void _accountChanged() {
    if (!mounted || _sessionScope == _currentScope) return;
    setState(() {
      _conversationState = null;
      _effectiveContext = null;
      _excludedCategories = <String>[];
      _lastIntent = null;
      _shownRecipeIds.clear();
      _shownFoodIds.clear();
      _items.clear();
      _items.add(_Item.ai(mockAiGreeting));
    });
    _restoreSession();
  }

  Future<void> _newConversation() async {
    if (_busy) return;
    try {
      await ChatSessionStore.clear(_currentScope);
    } catch (_) {
      // New conversations also work when the browser disables storage.
    }
    if (!mounted) return;
    setState(() {
      _sessionScope = _currentScope;
      _conversationState = null;
      _effectiveContext = null;
      _excludedCategories = <String>[];
      _lastIntent = null;
      _shownRecipeIds.clear();
      _shownFoodIds.clear();
      _items.clear();
      _items.add(_Item.ai(mockAiGreeting));
    });
  }

  Future<void> _editConditions() async {
    if (_busy) return;
    await _restoreSession();
    if (!mounted) return;
    final scope = _currentScope;
    final profile = AppState.instance.profile;
    final current =
        _effectiveContext ??
        <String, dynamic>{
          'people': profile.people,
          'cook_minutes': profile.cookMinutes,
          'avoid': profile.avoid.toList(),
          'preferences': profile.preferences.toList(),
          'low_sodium': profile.lowSodium,
        };
    final form = GlobalKey<FormState>();
    var people = (current['people'] as num).toInt();
    var minutes = (current['cook_minutes'] as num).toDouble();
    var avoidText = ((current['avoid'] as List?) ?? []).join('、');
    var tastesText = ((current['preferences'] as List?) ?? []).join('、');
    var lowSodium = current['low_sodium'] == true;
    var noSoup = _excludedCategories.contains('汤羹');
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: const Text('修改本次会话条件'),
          content: SingleChildScrollView(
            child: Form(
              key: form,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextFormField(
                    initialValue: '$people',
                    decoration: const InputDecoration(labelText: '用餐人数（1至20）'),
                    keyboardType: TextInputType.number,
                    validator: (v) {
                      final n = int.tryParse(v ?? '');
                      return n == null || n < 1 || n > 20 ? '请输入1至20的整数' : null;
                    },
                    onSaved: (v) => people = int.parse(v!),
                  ),
                  TextFormField(
                    initialValue: minutes.toStringAsFixed(0),
                    decoration: const InputDecoration(
                      labelText: '单菜时间上限（5至240分钟）',
                    ),
                    keyboardType: TextInputType.number,
                    validator: (v) {
                      final n = double.tryParse(v ?? '');
                      return n == null || !n.isFinite || n < 5 || n > 240
                          ? '请输入5至240的分钟数'
                          : null;
                    },
                    onSaved: (v) => minutes = double.parse(v!),
                  ),
                  TextFormField(
                    initialValue: avoidText,
                    decoration: const InputDecoration(
                      labelText: '忌口（用顿号或逗号分隔）',
                    ),
                    onSaved: (v) => avoidText = v ?? '',
                  ),
                  TextFormField(
                    initialValue: tastesText,
                    decoration: const InputDecoration(
                      labelText: '口味偏好（用顿号或逗号分隔）',
                    ),
                    onSaved: (v) => tastesText = v ?? '',
                  ),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('少盐偏好'),
                    value: lowSodium,
                    onChanged: (v) => update(() => lowSodium = v ?? false),
                  ),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('不喝汤'),
                    value: noSoup,
                    onChanged: (v) => update(() => noSoup = v ?? false),
                  ),
                  const Text('仅修改本次会话，不改家庭档案。时间按单菜已有记录筛选，不保证整餐总时长。'),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () {
                if (form.currentState!.validate()) {
                  form.currentState!.save();
                  Navigator.pop(dialogContext, true);
                }
              },
              child: const Text('保存并推荐'),
            ),
          ],
        ),
      ),
    );
    if (saved != true || !mounted || scope != _currentScope) return;
    List<String> split(String value) => value
        .split(RegExp(r'[、,，;；]'))
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toSet()
        .toList();
    final avoid = split(avoidText);
    final oldAvoid = ((current['avoid'] as List?) ?? []).whereType<String>();
    final removed = <String>{
      ...((_conversationState?['avoid_removed'] as List?) ?? [])
          .whereType<String>(),
      ...oldAvoid.where((a) => !avoid.contains(a)),
    }..removeAll(avoid);
    setState(() {
      _conversationState = <String, dynamic>{
        ...?_conversationState,
        'people': people,
        'cook_minutes': minutes,
        'low_sodium': lowSodium,
        'preferences': split(tastesText),
        'avoid_added': avoid,
        'avoid_removed': removed.toList(),
        'excluded_categories': noSoup ? ['汤羹'] : <String>[],
      };
      _effectiveContext = <String, dynamic>{
        ...current,
        'people': people,
        'cook_minutes': minutes,
        'low_sodium': lowSodium,
        'preferences': split(tastesText),
        'avoid': avoid,
      };
      _excludedCategories = noSoup ? ['汤羹'] : <String>[];
    });
    try {
      await ChatSessionStore.save(scope, <String, dynamic>{
        'state': _conversationState,
        'effective': _effectiveContext,
        'intent': _lastIntent,
        'recipes': _shownRecipeIds.toList(),
        'foods': _shownFoodIds.toList(),
        'categories': _excludedCategories,
      });
    } catch (_) {
      // Keep in-tab edits when storage is unavailable.
    }
    if (!mounted || scope != _currentScope) return;
    await _send('按修改后的条件重新推荐晚餐，其他条件不变');
  }

  String get _conditionLabel {
    final profile = AppState.instance.profile;
    final c =
        _effectiveContext ??
        <String, dynamic>{
          'people': profile.people,
          'cook_minutes': profile.cookMinutes,
          'avoid': profile.avoid.toList(),
          'preferences': profile.preferences.toList(),
          'low_sodium': profile.lowSodium,
        };
    final avoid = ((c['avoid'] as List?) ?? []).join('、');
    final tastes = ((c['preferences'] as List?) ?? []).join('、');
    return '本次条件：${c['people']}人 · ${c['cook_minutes']}分钟以内'
        '${c['low_sodium'] == true ? ' · 少盐' : ''}'
        '${tastes.isEmpty ? '' : ' · $tastes'}'
        '${avoid.isEmpty ? '' : ' · 忌口：$avoid'}'
        '${_excludedCategories.isEmpty ? '' : ' · 排除：${_excludedCategories.join('、')}'}';
  }

  @override
  void initState() {
    super.initState();
    _items.add(_Item.ai(mockAiGreeting));
    AuthStore.instance.addListener(_accountChanged);
    _restoreSession();
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
    _requestGeneration++;
    _chatCancel?.cancel('页面已关闭');
    AuthStore.instance.removeListener(_accountChanged);
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

  /// Show cards only after the backend has resolved this message's intent.
  Future<void> _send(String raw) async {
    final text = raw.trim();
    if (text.isEmpty || _busy) return;

    final requestScope = _currentScope;
    final generation = ++_requestGeneration;
    _chatCancel = CancelToken();
    _input.clear();
    setState(() {
      _items.add(_Item.user(text));
      _busy = true;
    });
    _scrollToBottom();

    final growing = <AgentStep>[];
    setState(
      () => _items.add(
        _Item.trace(const [
          AgentStep(agent: '处理中', summary: '正在理解问题并整理回答', ms: 0),
        ], true),
      ),
    );
    final reply = await _askBackend(text, useAi: true);
    if (!mounted ||
        generation != _requestGeneration ||
        _currentScope != requestScope) {
      return;
    }
    if (reply == null) {
      growing.add(
        AgentStep(agent: '连接状态', summary: _lastChatError ?? '请求失败', ms: 0),
      );
    }

    // 记住这一轮的意图 + 展示了哪些菜/食材，供下一句追问使用
    if (reply != null) {
      if (reply.intent.isNotEmpty) {
        _lastIntent = reply.intent;
      }
      _conversationState = reply.conversationState ?? _conversationState;
      _effectiveContext = reply.effectiveContext ?? _effectiveContext;
      _excludedCategories = reply.excludedCategories;
      for (final recipe in reply.recipes) {
        final id = int.tryParse(recipe.id);
        if (id != null) _shownRecipeIds.add(id);
      }
      for (final food in reply.foods) {
        final id = int.tryParse(food.id);
        if (id != null) _shownFoodIds.add(id);
      }
    }

    if (reply != null) {
      try {
        await ChatSessionStore.save(_currentScope, <String, dynamic>{
          'state': _conversationState,
          'effective': _effectiveContext,
          'intent': _lastIntent,
          'recipes': _shownRecipeIds.toList(),
          'foods': _shownFoodIds.toList(),
          'categories': _excludedCategories,
        });
      } catch (_) {
        // Storage unavailable: keep this tab's state and the successful reply.
      }
      if (!mounted ||
          generation != _requestGeneration ||
          _currentScope != requestScope) {
        return;
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
          recipes:
              (reply != null &&
                  const {
                    'meal_recommendation',
                    'cook_with_my_foods',
                  }.contains(reply.intent))
              ? reply.recipes
              : const <Recipe>[],
          // ★ 同理，推荐食材也直接带上完整对象（见 _Item.foods 的注释）。
          foods: (reply != null && reply.intent == 'recommend_foods')
              ? reply.foods
              : const <Food>[],
          localFallback: reply == null,
          fallbackReason: reply == null ? _lastChatError : null,
        ),
      );
      _busy = false;
    });
    _scrollToBottom();
  }

  /// 本地兜底文案（后端离线、或这一问失败时用）。
  String _localAnswer(String text) => '暂时无法连接问答服务，请稍后重试。';

  /// 问后端。任何失败都返回 null，交给调用方回落本地 ——
  /// 表现和后端离线时完全一致，界面不会弹错误。
  ///
  /// 本次把家庭硬约束一起带上：后端才能按忌口/限钠/可用时间真的筛候选，
  /// 而不是只在文案里提一嘴。
  ///
  /// ★ 同时把**失败原因**记到 `_lastChatError`：以前不管是超时、断网还是
  ///   后端 500，界面一律显示「后端未连接」—— 那句话经常是错的，
  ///   而且把排查方向带偏（明明连得上，只是模型这一问慢了点）。
  Future<AiChatResult?> _askBackend(String message, {bool useAi = true}) async {
    if (widget.request != null) return widget.request!(message, useAi);
    if (!BackendStatus.instance.online) {
      _lastChatError = '后端未连接（${BackendStatus.instance.apiBase}）';
      return null;
    }
    final scope = _currentScope;
    final cancel = _chatCancel;
    try {
      await _restoreSession();
      if (!mounted ||
          scope != _currentScope ||
          cancel != _chatCancel ||
          cancel?.isCancelled == true) {
        return null;
      }
      final profile = AppState.instance.profile;
      final foodReplies = _items.reversed.where(
        (item) => item.foods.isNotEmpty,
      );
      final recipeReplies = _items.reversed.where(
        (item) => item.recipes.isNotEmpty,
      );
      final turns = _items
          .where((item) => item.kind == _Kind.user || item.kind == _Kind.ai)
          .toList();
      // The current user message is sent separately; avoid duplicating it in history.
      if (turns.isNotEmpty && turns.last.kind == _Kind.user) turns.removeLast();
      final recentTurns = turns.length > 8
          ? turns.sublist(turns.length - 8)
          : turns;
      final result = await BackendApi.instance.chat(
        message,
        useAi: useAi,
        cancelToken: cancel,
        city: CityStore.instance.city.name,
        people: profile.people,
        cookMinutes: profile.cookMinutes,
        lowSodium: profile.lowSodium,
        preferences: profile.preferences.toList(),
        avoid: profile.avoid.toList(),
        // ★ 会话上下文：追问靠它才不会被当成闲聊
        conversationState: _conversationState,
        contextFoodIds: foodReplies.isEmpty
            ? const <int>[]
            : foodReplies.first.foods
                  .map((food) => int.tryParse(food.id))
                  .whereType<int>()
                  .toList(),
        contextRecipeIds: recipeReplies.isEmpty
            ? const <int>[]
            : recipeReplies.first.recipes
                  .map((recipe) => int.tryParse(recipe.id))
                  .whereType<int>()
                  .toList(),
        history: recentTurns.any((item) => item.kind == _Kind.user)
            ? recentTurns
                  .map(
                    (item) => <String, dynamic>{
                      'role': item.kind == _Kind.user ? 'user' : 'assistant',
                      'content': item.text.length > 1000
                          ? item.text.substring(0, 1000)
                          : item.text,
                    },
                  )
                  .toList()
            : const <Map<String, dynamic>>[],
        lastIntent: _lastIntent,
        recentRecipeIds: _shownRecipeIds.toList(),
        recentFoodIds: _shownFoodIds.toList(),
      );
      if (_currentScope != scope) return null;
      return result;
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
                  const SizedBox(height: 12),
                  Text(_conditionLabel),
                  Align(
                    alignment: Alignment.centerRight,
                    child: Wrap(
                      children: [
                        TextButton(
                          onPressed: _busy ? null : _editConditions,
                          child: const Text('编辑条件'),
                        ),
                        TextButton(
                          onPressed: _busy ? null : _newConversation,
                          child: const Text('开始新会话'),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  for (final item in _items) ...[
                    _ItemView(item: item),
                    const SizedBox(height: 12),
                  ],
                ],
              ),
            ),
            if (_busy)
              TextButton.icon(
                onPressed: _stopWaiting,
                icon: const Icon(Icons.stop_circle_outlined, size: 16),
                label: const Text('停止等待'),
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
          colors: [brand700, brand900],
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
                foregroundColor: brand900,
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
              color: brand700,
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
                // ★ 推荐食材的卡片 —— 和菜谱卡片是并列的两条链路
                if (item.foods.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  for (final food in item.foods) ...[
                    _MiniFoodCard(food: food),
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

/// 推荐**食材**的卡片。
///
/// 对应后端的 `recommend_foods` 意图 —— 用户不一定想「用家里的食材做菜」，
/// 也可能直接让 AI 按需求从食材库里挑对症的（「家里有健身的」→ 鸡胸肉）。
/// 视觉上刻意和菜谱卡片区分：食材是「买东西」的语境，用方图 + 标签，
/// 菜谱是「做饭」的语境，用横图 + 时长。
class _MiniFoodCard extends StatelessWidget {
  final Food food;

  const _MiniFoodCard({required this.food});

  @override
  Widget build(BuildContext context) {
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        border: Border.all(color: line),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 92, height: 92, child: FoodPhoto(asset: food.image)),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    food.name,
                    style: const TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Wrap(
                    spacing: 5,
                    runSpacing: 5,
                    children: [
                      for (final tag in food.tags.take(3))
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 7,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: brand50,
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(
                            tag,
                            style: const TextStyle(
                              fontSize: 10,
                              color: brand700,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                    ],
                  ),
                  AddFoodToPantryButton(food: food),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

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
                  recipe.metaLine,
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
                          backgroundColor: brand700,
                          shape: const StadiumBorder(),
                        ),
                      );
                    },
                    style: FilledButton.styleFrom(
                      backgroundColor: brand600,
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
  final bool isBackend;

  const _TraceCard({
    required this.steps,
    required this.running,
    this.isBackend = false,
  });

  int get _totalMs => steps.fold<int>(0, (sum, s) => sum + s.ms);

  @override
  Widget build(BuildContext context) {
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(14),
      side: const BorderSide(color: brand100),
    );
    return ExpansionTile(
      initiallyExpanded: false,
      dense: true,
      tilePadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
      shape: shape,
      collapsedShape: shape,
      backgroundColor: brand50,
      collapsedBackgroundColor: brand50,
      iconColor: brand700,
      collapsedIconColor: brand700,
      leading: running
          ? const SizedBox(
              width: 15,
              height: 15,
              child: CircularProgressIndicator(strokeWidth: 2, color: brand700),
            )
          : const Icon(Icons.account_tree_outlined, size: 16, color: brand700),
      title: Row(
        children: [
          Expanded(
            child: Text(
              running ? '正在处理' : '推荐流程',
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: brand900,
              ),
            ),
          ),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              running
                  ? '点击查看'
                  : '${steps.length}步 · ${(_totalMs / 1000).toStringAsFixed(2)}s',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 10.5, color: brand700),
            ),
          ),
        ],
      ),
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: Text(
            running ? '正在整理回答…' : (isBackend ? '后端执行记录' : '本地处理记录'),
            style: const TextStyle(fontSize: 10, color: muted),
          ),
        ),
        const SizedBox(height: 12),
        for (var i = 0; i < steps.length; i++)
          _TraceRow(step: steps[i], last: i == steps.length - 1),
      ],
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

    final Color dotColor = vetoed ? brand600 : (info ? muted : brand700);
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
                  color: vetoed ? brand100 : Colors.white,
                  border: Border.all(color: dotColor, width: 1.4),
                  shape: BoxShape.circle,
                ),
                child: Icon(dotIcon, size: 10, color: dotColor),
              ),
              if (!last)
                Expanded(child: Container(width: 1.2, color: brand100)),
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
                            color: vetoed ? brand600 : ink,
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
                    fillColor: brand50,
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
                color: busy ? muted : brand600,
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
