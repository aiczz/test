// 内容模型：食材 / 菜谱
//
// 字段对应队友 `front指南.txt` 第 25 节约定的接口：
//   GET /api/foods        → List<Food>
//   GET /api/recipes      → List<Recipe>

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
        tags: ((j['tags'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
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

  const Recipe({
    required this.id,
    required this.name,
    required this.image,
    required this.desc,
    required this.time,
    required this.people,
    required this.tags,
  });

  factory Recipe.fromJson(Map<String, dynamic> j) => Recipe(
        id: j['id'] as String? ?? '',
        name: j['name'] as String? ?? '',
        image: j['image'] as String? ?? '',
        desc: j['desc'] as String? ?? '',
        time: j['time'] as String? ?? '',
        people: j['people'] as String? ?? '',
        tags: ((j['tags'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
      );
}

/// 首页 AI 建议条
class AiTip {
  final String title;
  final String body;

  const AiTip({required this.title, required this.body});
}
