// 首页推荐派生：把「家庭档案」变成真的会变的推荐结果。
//
// 为什么要有这个文件：
//   家庭档案是求解器的输入 —— 但之前只有菜单页读它，首页推荐是写死的
//   mockFoods.take(3) / mockRecipes.take(3)。结果是「改约束」在首页完全
//   看不出来，个性化只存在于一个页面里，首页看起来是个静态样板。
//
//   这里用确定性规则把约束落到首页可见的内容上：
//     · 烹饪时间 → 超过「每日可用烹饪时间」的菜谱直接筛掉
//     · 忌口     → 名称/描述/标签/食材命中忌口词的菜谱筛掉
//     · 低钠     → 清淡/低脂的菜谱排前面
//     · 口味偏好 → 命中的排前面
//
//   它不是 AI，也不假装是 —— 就是规则，和 local_estimator.dart 一个性质。

import '../data/mock.dart';
import '../models/ai_feed.dart';
import '../models/content.dart';
import '../state/app_state.dart';

/// 首页一次推荐的结果：内容 + 为什么是这些
class HomePicks {
  final List<Food> foods;
  final List<Recipe> recipes;

  /// 本次实际生效的约束，用于副标题展示。如 ['45 分钟内', '忌辛辣']
  final List<String> notes;

  /// 被约束筛掉的菜谱数（0 = 一道都没筛掉，说明当前条件下全都做得了）
  final int dropped;

  /// 被筛掉的菜名 —— 用来解释「为什么下方推荐里没有它」。
  /// 首页顶部的 Hero 是固定的时令推荐，下方是「按你的条件能做」，
  /// 不点名说明的话，两者看起来会自相矛盾。
  final List<String> droppedNames;

  // ---- 以下来自后端推荐流（后端离线时为 null / 空）----

  /// 这次推荐是谁算的：'ai' / 'cached' / 'algorithm' / null（本地规则）
  final String? source;

  /// 给用户看的来源说明，全部来自后端如实标注
  final String? sourceLabel;

  /// 后端返回的天气行（如「🍂 阴 19°C · 秋燥当令，润肺生津的食材优先」）
  final String? weatherLine;

  /// 菜名 → 推荐理由（后端算法/大模型给的）
  final Map<String, String> foodReasons;
  final Map<String, String> recipeReasons;

  /// 今天的 AI 建议（后端给的，比本地写死的更有依据）
  final String? aiTipTitle;
  final String? aiTipBody;

  /// 算法/AI 的执行轨迹 —— 答辩时展开给评委看
  final List<HomeAlgoStep> steps;
  final HomeWeather? weather;

  const HomePicks({
    required this.foods,
    required this.recipes,
    required this.notes,
    required this.dropped,
    required this.droppedNames,
    this.source,
    this.sourceLabel,
    this.weatherLine,
    this.foodReasons = const <String, String>{},
    this.recipeReasons = const <String, String>{},
    this.aiTipTitle,
    this.aiTipBody,
    this.steps = const <HomeAlgoStep>[],
    this.weather,
  });

  /// 菜谱区块的副标题
  String get subtitle => notes.isEmpty ? '应季食材 · 简单好做' : notes.join(' · ');

  /// 这一份推荐是不是后端算的
  bool get fromBackend => source != null;

  /// ★ 用后端「算法 + AI」的结果构造。
  ///
  /// 为什么菜谱的展示文案直接换成推荐理由：
  ///   卡片本来就有一行小字在显示 `recipe.desc`（菜谱简介）。
  ///   把理由放进这一行，**不用改任何布局**就能让用户看到
  ///   「为什么今天推这道菜」—— 而布局不动，就不会碰坏既有的交互测试。
  factory HomePicks.fromFeed(
    HomeFeed feed,
    FamilyProfile profile, {
    List<Recipe>? recipePool,
    int limit = 3,
  }) {
    final notes = <String>[
      '${profile.cookMinutes.round()} 分钟内',
      if (profile.avoid.isNotEmpty) '忌${profile.avoid.join('、')}',
      if (profile.lowSodium) '低钠优先',
      if (feed.weather != null) feed.weather!.emoji,
    ];

    // 内容库已验证配图资源；首页独立接口也必须使用同样的检查。
    final validImages = recipePool?.map((recipe) => recipe.image).toSet();
    bool hasImage(Recipe recipe) =>
        recipe.image.trim().isNotEmpty &&
        (validImages == null || validImages.contains(recipe.image));
    final visiblePicks = feed.recipes
        .where((pick) => hasImage(pick.item))
        .take(limit)
        .toList();
    final recipes = visiblePicks
        .map(
          (pick) => pick.reason.isEmpty
              ? pick.item
              : Recipe(
                  id: pick.item.id,
                  name: pick.item.name,
                  image: pick.item.image,
                  // 理由比原始简介有用得多，直接顶上去（布局不变）
                  desc: pick.reason,
                  time: pick.item.time,
                  people: pick.item.people,
                  tags: pick.item.tags,
                  ingredients: pick.item.ingredients,
                  steps: pick.item.steps,
                  difficulty: pick.item.difficulty,
                ),
        )
        .toList();

    // 缺图位置用有图菜谱补齐，不放宽忌口与烹饪时间约束。
    if (recipePool != null && recipes.length < limit) {
      final candidates =
          recipePool
              .where(
                (recipe) =>
                    hasImage(recipe) &&
                    !_hitsAvoid(recipe, profile.avoid) &&
                    _minutesOf(recipe) <= profile.cookMinutes,
              )
              .toList()
            ..sort((a, b) => _score(b, profile).compareTo(_score(a, profile)));
      final ids = recipes.map((recipe) => recipe.id).toSet();
      for (final recipe in candidates) {
        if (recipes.length >= limit) break;
        if (ids.add(recipe.id)) recipes.add(recipe);
      }
    }

    return HomePicks(
      foods: feed.foods.map((pick) => pick.item).toList(),
      recipes: recipes,
      notes: notes,
      // 硬约束是后端执行的，前端不再重复统计「筛掉几道」，
      // 免得两边口径不一致反而对不上。
      dropped: 0,
      droppedNames: const <String>[],
      source: feed.source,
      sourceLabel: feed.sourceLabel,
      weatherLine: feed.weatherLine.isEmpty ? null : feed.weatherLine,
      foodReasons: {for (final pick in feed.foods) pick.item.name: pick.reason},
      recipeReasons: {
        for (final pick in visiblePicks) pick.item.name: pick.reason,
      },
      aiTipTitle: feed.aiTipTitle.isEmpty ? null : feed.aiTipTitle,
      aiTipBody: feed.aiTip.isEmpty ? null : feed.aiTip,
      steps: feed.steps,
      weather: feed.weather,
    );
  }
}

/// 按家庭档案给首页挑推荐内容。[limit] 是每个区块最多几张卡片。
HomePicks pickForHome(
  FamilyProfile profile, {

  /// 内容数据源。不传就用本地假数据 —— 页面从 ContentStore 传真后端数据进来。
  List<Food>? foodPool,
  List<Recipe>? recipePool,
  int limit = 3,
}) {
  final foods = _visibleFoods(profile, foodPool ?? mockFoods);
  final result = _visibleRecipes(profile, recipePool ?? mockRecipes);

  final notes = <String>[
    '${profile.cookMinutes.round()} 分钟内',
    if (profile.avoid.isNotEmpty) '忌${profile.avoid.join('、')}',
    if (profile.lowSodium) '低钠优先',
    if (result.dropped.isNotEmpty) '已筛掉 ${result.dropped.length} 道',
  ];

  return HomePicks(
    foods: foods.take(limit).toList(),
    recipes: result.recipes.take(limit).toList(),
    notes: notes,
    dropped: result.dropped.length,
    droppedNames: result.dropped.map((r) => r.name).toList(),
  );
}

// ---------------------------------------------------------------------
// 食材
// ---------------------------------------------------------------------

List<Food> _visibleFoods(FamilyProfile p, List<Food> source) {
  if (p.avoid.isEmpty) return source;
  final kept = source
      .where(
        (f) => !p.avoid.any(
          (a) => f.name.contains(a) || f.tags.any((t) => t.contains(a)),
        ),
      )
      .toList();
  // 全被筛光时退回原始列表：宁可推一道「可能不合忌口」的，
  // 也不能让首页出现空白区块 —— 空白比不完美更糟。
  return kept.isEmpty ? source : kept;
}

// ---------------------------------------------------------------------
// 菜谱
// ---------------------------------------------------------------------

({List<Recipe> recipes, List<Recipe> dropped}) _visibleRecipes(
  FamilyProfile p,
  List<Recipe> source,
) {
  // 1. 忌口出局
  final afterAvoid = source.where((r) => !_hitsAvoid(r, p.avoid)).toList();

  // 2. 烹饪时间出局
  final afterTime = afterAvoid
      .where((r) => _minutesOf(r) <= p.cookMinutes)
      .toList();

  // 兜底：同上，全筛光就退回上一级
  final kept = afterTime.isNotEmpty
      ? afterTime
      : (afterAvoid.isNotEmpty ? afterAvoid : source);

  // 3. 排序：口味偏好命中优先；开低钠时清淡/低脂优先
  final sorted = <Recipe>[...kept]
    ..sort((a, b) => _score(b, p).compareTo(_score(a, p)));

  final keptIds = kept.map((r) => r.id).toSet();
  final dropped = source.where((r) => !keptIds.contains(r.id)).toList();

  return (recipes: sorted, dropped: dropped);
}

/// 命中忌口：名称、描述、标签、食材里出现忌口词就算命中
bool _hitsAvoid(Recipe r, Set<String> avoid) {
  if (avoid.isEmpty) return false;
  final haystack = <String>[r.name, r.desc, ...r.tags, ...r.ingredients];
  return haystack.any((v) => avoid.any(v.contains));
}

/// 从「60分钟」这类文案里取分钟数
int _minutesOf(Recipe r) {
  final m = _digits.firstMatch(r.time);
  // 取不到时间就当不占时间，不误伤
  return m == null ? 0 : (int.tryParse(m.group(1)!) ?? 0);
}

/// 分数越高越靠前
int _score(Recipe r, FamilyProfile p) {
  var s = 0;
  if (r.tags.any(p.preferences.contains)) s += 2;
  if (p.lowSodium && r.tags.any(_lightTags.contains)) s += 1;
  return s;
}

final _digits = RegExp(r'(\d+)');

const _lightTags = <String>{'清淡', '低脂', '少油', '低卡', '轻食'};

// ---------------------------------------------------------------------
// 处理流程（本地兜底版）
//
// ⚠️ 这里以前叫 agentTraceFor，输出的是「多智能体协作」轨迹 —— 内容是**编的**：
//      Planner Agent: 「CP-SAT 求解完成，生成 3 个 Pareto 方案」← CP-SAT 根本没做
//      Critic Agent:  「否决方案 B（钠 2180 mg 超标）」        ← 那几个数字是编的
//      Inventory Agent:「菠菜周四到期，需优先消耗」            ← 也是编的
//    这在比赛里是硬伤：把没有的东西说成有。项目里从来没有多智能体 ——
//    后端只是一串顺序执行的函数（外加一次大模型调用），不存在 agent 自主决策。
//
//    现在改成**如实描述本地规则到底做了什么**：只有三步，都是这个文件里
//    真实发生的确定性规则，没有 AI、也没有求解器。
//    后端在线时界面用的是后端返回的真实轨迹（见 BackendApi.chat 的 trace），
//    这一份只在后端离线、走本地演示数据时使用。
// ---------------------------------------------------------------------

/// 本地规则实际做的事（诚实版：没有 AI、没有求解器）
List<AgentStep> localTraceFor(FamilyProfile p) {
  final avoidText = p.avoid.isEmpty ? '无忌口' : p.avoid.join('、');
  final prefText = p.preferences.isEmpty ? '无特别偏好' : p.preferences.join('、');
  return <AgentStep>[
    AgentStep(
      agent: '读取家庭档案',
      summary:
          '${p.people} 人 · 每日 ${p.cookMinutes.round()} 分钟 · 忌口 $avoidText · '
          '${p.lowSodium ? '限钠' : '不限钠'}',
      status: 'info',
      ms: 1,
    ),
    AgentStep(
      agent: '本地规则筛选',
      summary: '按烹饪时间筛掉超时的菜，按忌口过滤命中项（口味偏好：$prefText）',
      ms: 2,
    ),
    AgentStep(
      agent: '本地规则排序',
      summary: p.lowSodium ? '口味偏好命中优先，低钠（清淡 / 低脂）加分' : '口味偏好命中优先',
      ms: 1,
    ),
  ];
}
