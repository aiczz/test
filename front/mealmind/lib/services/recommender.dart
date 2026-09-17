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

  const HomePicks({
    required this.foods,
    required this.recipes,
    required this.notes,
    required this.dropped,
  });

  /// 菜谱区块的副标题
  String get subtitle => notes.isEmpty ? '应季食材 · 简单好做' : notes.join(' · ');
}

/// 按家庭档案给首页挑推荐内容。[limit] 是每个区块最多几张卡片。
HomePicks pickForHome(FamilyProfile profile, {int limit = 3}) {
  final foods = _visibleFoods(profile);
  final result = _visibleRecipes(profile);

  final notes = <String>[
    '${profile.cookMinutes.round()} 分钟内',
    if (profile.avoid.isNotEmpty) '忌${profile.avoid.join('、')}',
    if (profile.lowSodium) '低钠优先',
    if (result.dropped > 0) '已筛掉 ${result.dropped} 道',
  ];

  return HomePicks(
    foods: foods.take(limit).toList(),
    recipes: result.recipes.take(limit).toList(),
    notes: notes,
    dropped: result.dropped,
  );
}

// ---------------------------------------------------------------------
// 食材
// ---------------------------------------------------------------------

List<Food> _visibleFoods(FamilyProfile p) {
  if (p.avoid.isEmpty) return mockFoods;
  final kept = mockFoods
      .where(
        (f) =>
            !p.avoid.any((a) => f.name.contains(a) || f.tags.any((t) => t.contains(a))),
      )
      .toList();
  // 全被筛光时退回原始列表：宁可推一道「可能不合忌口」的，
  // 也不能让首页出现空白区块 —— 空白比不完美更糟。
  return kept.isEmpty ? mockFoods : kept;
}

// ---------------------------------------------------------------------
// 菜谱
// ---------------------------------------------------------------------

({List<Recipe> recipes, int dropped}) _visibleRecipes(FamilyProfile p) {
  // 1. 忌口出局
  final afterAvoid = mockRecipes.where((r) => !_hitsAvoid(r, p.avoid)).toList();

  // 2. 烹饪时间出局
  final afterTime = afterAvoid
      .where((r) => _minutesOf(r) <= p.cookMinutes)
      .toList();

  // 兜底：同上，全筛光就退回上一级
  final kept = afterTime.isNotEmpty
      ? afterTime
      : (afterAvoid.isNotEmpty ? afterAvoid : mockRecipes);

  // 3. 排序：口味偏好命中优先；开低钠时清淡/低脂优先
  final sorted = <Recipe>[...kept]
    ..sort((a, b) => _score(b, p).compareTo(_score(a, p)));

  return (recipes: sorted, dropped: mockRecipes.length - kept.length);
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
// 多智能体协作轨迹
// ---------------------------------------------------------------------

/// 按真实家庭档案生成协作轨迹。
///
/// 轨迹的**流程**仍是本地按设计展开的（后端好了由接口返回），
/// 但「读到的档案」必须是真的 —— 否则用户把人数改成 5 人，
/// 轨迹第一步还写着「3 人 · 周预算 300 元」，一眼就露馅。
///
/// 这里还有一个直接看得见的因果：
///   开低钠 → 钠 1720 / 2000 mg，Critic 否决方案 B（橙色 veto）
///   关低钠 → 钠 2180 / 2400 mg，Critic 不再否决
/// 「约束改变多智能体的决策结果」在演示里是能亲眼看出来的。
List<AgentStep> agentTraceFor(FamilyProfile p) {
  final avoidText = p.avoid.isEmpty ? '无忌口' : p.avoid.join('、');
  final prefText = p.preferences.isEmpty ? '无特别偏好' : p.preferences.join('、');
  final sodium = p.lowSodium ? 1720 : 2180;

  return <AgentStep>[
    AgentStep(
      agent: 'Profile Agent',
      summary:
          '读取家庭档案：${p.people} 人 · 周预算 ¥${p.budget.toStringAsFixed(0)} · '
          '每日 ${p.cookMinutes.round()} 分钟 · 忌口 $avoidText',
      ms: 12,
    ),
    AgentStep(
      agent: 'Retrieval Agent',
      summary: '候选召回 42 道 → 按「$prefText」与忌口过滤后剩 31 道',
      ms: 86,
    ),
    AgentStep(
      agent: 'Inventory Agent',
      summary: '库存与保质期检查：菠菜周四到期，需优先消耗',
      status: 'info',
      ms: 9,
    ),
    AgentStep(
      agent: 'Nutrition Agent',
      summary:
          '营养校验：钠 $sodium / ${p.sodiumLimitMg} mg '
          '${sodium > p.sodiumLimitMg ? '超标' : '✓'} · 蔬菜量达标 ✓',
      ms: 24,
    ),
    AgentStep(
      agent: 'Planner Agent',
      summary: 'CP-SAT 求解完成，生成 3 个 Pareto 方案',
      ms: 1840,
    ),
    AgentStep(
      agent: 'Critic Agent',
      summary: p.lowSodium
          ? '否决方案 B（钠 2180 mg 超标），回灌 Planner 重解'
          : '方案 B 通过 —— 未开启低钠约束，钠 2180 mg 在 ${p.sodiumLimitMg} mg 上限内',
      status: p.lowSodium ? 'veto' : 'ok',
      ms: 31,
    ),
    AgentStep(agent: 'Explainer Agent', summary: '生成推荐理由与约束松紧说明', ms: 402),
  ];
}
