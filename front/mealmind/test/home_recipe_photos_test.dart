import 'package:flutter_test/flutter_test.dart';
import 'package:mealmind/models/ai_feed.dart';
import 'package:mealmind/models/content.dart';
import 'package:mealmind/services/recommender.dart';
import 'package:mealmind/state/app_state.dart';

Recipe recipe(String id, String image, {String time = '15分钟'}) => Recipe(
  id: id,
  name: id,
  image: image,
  desc: '原始简介',
  time: time,
  people: '',
  tags: const [],
);

HomeFeed feed(List<Recipe> recipes) => HomeFeed(
  seasonName: '秋季',
  month: 10,
  foods: const [],
  recipes: [for (final item in recipes) HomePick(item: item, reason: '推荐理由')],
  aiTipTitle: '',
  aiTip: '',
  source: 'algorithm',
  date: '2026-10-10',
  region: '杭州',
);

void main() {
  test('首页排除空图及缺失资源，补齐有图菜谱且不重复、不突破忌口时间', () {
    final a = recipe('A', 'a.jpg');
    final b = recipe('B', 'b.jpg');
    final c = recipe('C', 'c.jpg');
    final picks = HomePicks.fromFeed(
      feed([a, recipe('空图', ''), recipe('坏图', 'missing.jpg')]),
      const FamilyProfile(avoid: {'花生'}),
      recipePool: [
        a,
        recipe('花生', 'peanut.jpg'),
        recipe('超时', 'slow.jpg', time: '90分钟'),
        b,
        c,
      ],
    );
    expect(picks.recipes.map((r) => r.id), ['A', 'B', 'C']);
    expect(picks.recipes.first.desc, '推荐理由');
    expect(picks.recipes[1].desc, '原始简介');
    expect(picks.recipeReasons.keys, ['A']);
  });

  test('没有可用配图时不恢复无图推荐', () {
    final picks = HomePicks.fromFeed(
      feed([recipe('空图', '')]),
      const FamilyProfile(),
      recipePool: [],
    );
    expect(picks.recipes, isEmpty);
  });
}
