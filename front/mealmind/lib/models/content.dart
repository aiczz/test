// 内容模型：食材 / 菜谱
//
// 字段对应队友 `front指南.txt` 第 25 节约定的接口：
//   GET /api/foods        → List<Food>
//   GET /api/recipes      → List<Recipe>
//   GET /api/recipes/{id} → Recipe（含 ingredients / steps）

List<String> _strList(dynamic value) =>
    ((value as List?) ?? const <dynamic>[]).map((e) => e.toString()).toList();

/// 当前季节的单字（春 / 夏 / 秋 / 冬）。
///
/// 按月切分的口径和后端 `home_service.season_name_of` 保持一致
/// （3-5 春、6-8 夏、9-11 秋、12-2 冬），
/// 免得前端说「秋季」、后端说「秋」，两边对不上。
String get currentSeasonChar {
  final month = DateTime.now().month;
  if (month >= 3 && month <= 5) return '春';
  if (month >= 6 && month <= 8) return '夏';
  if (month >= 9 && month <= 11) return '秋';
  return '冬';
}

class Food {
  final String id;
  final String name;
  final String image; // 资源路径，如 assets/images/lotus.jpg
  final String category; // 蔬菜 / 肉蛋 / 水产 / 豆制品
  final List<String> tags;

  /// 时令季节，如「秋季」「秋冬季」「全年」。
  ///
  /// ⚠️ 后端 `/api/foods` 的 FoodBrief 只返回 season_score、不返回季节名，
  ///    所以接后端时这里是 null。在线的「时令」判定不靠这个字段，
  ///    而是走 ContentStore.isSeasonal()（用 /api/foods/seasonal 的当月结果）。
  ///    留着它是为了线上 PWA —— 那边没有后端、走本地假数据，
  ///    没有这个标注「时令」分类就会是空的。
  final String? season;

  /// 后端算出来的应季指数（0~100）。
  ///
  /// ⚠️ 以前详情弹层里写死了一句 `应季指数 92` —— 不管打开的是哪个食材、
  ///    是不是当季，都是 92。那是编的。现在用后端给的真实分值，
  ///    拿不到（离线 / 本地假数据）就**不显示这个标签**。
  final int? seasonScore;

  const Food({
    required this.id,
    required this.name,
    required this.image,
    required this.category,
    required this.tags,
    this.season,
    this.seasonScore,
  });

  factory Food.fromJson(Map<String, dynamic> j) => Food(
    id: j['id'] as String? ?? '',
    name: j['name'] as String? ?? '',
    image: j['image'] as String? ?? '',
    category: j['category'] as String? ?? '',
    tags: _strList(j['tags']),
    season: j['season'] as String?,
    seasonScore: (j['season_score'] as num?)?.toInt(),
  );

  /// 在【当前季节】是不是时令。
  ///
  /// 判断刻意保守：「全年」供应的小白菜、鸡蛋不算时令 ——
  /// 时令的意思是「当季特有」，把全年货也算进来，这个分类就没有区分度了。
  bool get isSeasonalNow {
    final s = season;
    if (s == null || s.isEmpty) return false;
    return s.contains(currentSeasonChar);
  }
}

class Recipe {
  final String id;
  final String name;
  final String image;
  final String desc;
  final String time; // 如「60分钟」
  final String people; // 如「2-3人」
  final List<String> tags;

  // ---- 详情页字段（列表接口可能不返回，所以给了默认值）----
  final List<String> ingredients; // 所需食材，含用量文案，如「莲藕 1节」
  final List<String> steps; // 做法步骤
  final String difficulty; // 简单 / 中等

  const Recipe({
    required this.id,
    required this.name,
    required this.image,
    required this.desc,
    required this.time,
    required this.people,
    required this.tags,
    this.ingredients = const <String>[],
    this.steps = const <String>[],
    this.difficulty = '简单',
  });

  factory Recipe.fromJson(Map<String, dynamic> j) => Recipe(
    id: j['id'] as String? ?? '',
    name: j['name'] as String? ?? '',
    image: j['image'] as String? ?? '',
    desc: j['desc'] as String? ?? '',
    time: j['time'] as String? ?? '',
    people: j['people'] as String? ?? '',
    tags: _strList(j['tags']),
    ingredients: _strList(j['ingredients']),
    steps: _strList(j['steps']),
    difficulty: j['difficulty'] as String? ?? '简单',
  );
}

/// 菜谱分类筛选区里的一个分类。
///
/// `count` 是这个分类下的菜品数，由后端 `/api/recipes/tags` 给。
/// 界面上直接显示出来 —— 用户点之前就知道这个分类里有没有菜，
/// 不会再出现「点进去是空的」。
class RecipeTag {
  final String name;
  final int count;

  const RecipeTag({required this.name, required this.count});

  factory RecipeTag.fromJson(Map<String, dynamic> j) => RecipeTag(
    name: j['name'] as String? ?? '',
    count: (j['count'] as num?)?.toInt() ?? 0,
  );
}

/// 分类的一个分组（「做法」「主要食材」…）。
///
/// 分组名和顺序都由后端定（`app/data/dish_tags.py` 的 TAG_GROUPS），
/// 前端不自己编分类 —— 否则又会出现「前端写死的分类和库里的标签对不上」。
class RecipeTagGroup {
  final String group;
  final List<RecipeTag> tags;

  const RecipeTagGroup({required this.group, required this.tags});

  factory RecipeTagGroup.fromJson(Map<String, dynamic> j) => RecipeTagGroup(
    group: j['group'] as String? ?? '',
    tags: ((j['tags'] as List?) ?? const <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(RecipeTag.fromJson)
        .toList(),
  );
}

/// 首页 AI 建议条
class AiTip {
  final String title;
  final String body;

  const AiTip({required this.title, required this.body});
}

/// =====================================================================
/// 多智能体协作轨迹的一步
///
/// 这是本项目"多智能体"唯一能被【看见】的地方 ——
/// 答辩时把这张轨迹展开，比说十句"我们用了多智能体"都有用。
/// =====================================================================
class AgentStep {
  final String agent; // 角色名，如 Profile Agent
  final String summary; // 这一步做了什么

  /// ok   = 正常完成
  /// veto = 否决（Critic 的一票否决，是整个架构的灵魂）
  /// info = 只读信息
  final String status;

  final int ms; // 耗时（毫秒）

  const AgentStep({
    required this.agent,
    required this.summary,
    this.status = 'ok',
    this.ms = 0,
  });
}
