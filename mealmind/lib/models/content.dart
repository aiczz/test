// 内容模型：食材 / 菜谱
//
// 字段对应队友 `front指南.txt` 第 25 节约定的接口：
//   GET /api/foods        → List<Food>
//   GET /api/recipes      → List<Recipe>
//   GET /api/recipes/{id} → Recipe（含 ingredients / steps）

List<String> _strList(dynamic value) =>
    ((value as List?) ?? const <dynamic>[])
        .map((e) => e.toString())
        .toList();

class Food {
  final String id;
  final String name;
  final String image; // 资源路径，如 assets/images/lotus.jpg
  final String category; // 蔬菜 / 肉蛋 / 水产 / 豆制品
  final String qty; // 数量，如「1节」
  final List<String> tags;

  const Food({
    required this.id,
    required this.name,
    required this.image,
    required this.category,
    required this.qty,
    required this.tags,
  });

  factory Food.fromJson(Map<String, dynamic> j) => Food(
        id: j['id'] as String? ?? '',
        name: j['name'] as String? ?? '',
        image: j['image'] as String? ?? '',
        category: j['category'] as String? ?? '',
        qty: j['qty'] as String? ?? '',
        tags: _strList(j['tags']),
      );
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

