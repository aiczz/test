import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:mealmind/main.dart';

void main() {
  testWidgets('五个主入口可用，食材可添加到我的库存', (tester) async {
    // 每个用例使用独立的根节点，避免复用上一个用例停留的 tab 和滚动位置。
    await tester.pumpWidget(ShishiApp(key: UniqueKey()));

    expect(find.text('今天吃什么'), findsOneWidget);
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('首页'), findsOneWidget);
    expect(find.text('食材'), findsOneWidget);
    expect(find.text('菜谱'), findsOneWidget);
    expect(find.text('AI助手'), findsOneWidget);
    expect(find.text('我的'), findsOneWidget);

    final homeCarousel = find.byType(PageView).first;
    await tester.drag(homeCarousel, const Offset(-360, 0));
    await tester.pumpAndSettle();
    expect(find.text('看看家里\n有什么'), findsOneWidget);
    expect(find.text('管理我的食材'), findsOneWidget);

    await tester.drag(homeCarousel, const Offset(-360, 0));
    await tester.pumpAndSettle();
    expect(find.text('不知道吃什么？\n问问 AI'), findsOneWidget);
    expect(find.text('打开 AI 助手'), findsOneWidget);

    await tester.tap(find.text('食材'));
    await tester.pumpAndSettle();

    expect(find.text('时令食材'), findsOneWidget);
    expect(find.text('秋季时令食材'), findsOneWidget);
    expect(find.text('全部'), findsOneWidget);
    expect(find.text('蔬菜'), findsOneWidget);
    expect(find.text('肉蛋'), findsOneWidget);
    expect(find.text('水产'), findsOneWidget);
    expect(find.text('豆制品'), findsOneWidget);

    expect(find.text('我的 0'), findsOneWidget);
    final addButton = find.byTooltip('添加到我的食材').first;
    await tester.ensureVisible(addButton);
    await tester.pumpAndSettle();
    await tester.tap(addButton);
    await tester.pumpAndSettle();

    final removeButton = find.byTooltip('从我的食材中移除').first;
    expect(removeButton, findsOneWidget);
    await tester.tap(removeButton);
    await tester.pumpAndSettle();

    // 卡片滚入视口后页头已经被 ListView 回收，这里验证按钮确实恢复为“+”。
    expect(find.byTooltip('添加到我的食材'), findsWidgets);

    final addAgainButton = find.byTooltip('添加到我的食材').first;
    await tester.tap(addAgainButton);
    await tester.pumpAndSettle();
    expect(find.byTooltip('从我的食材中移除'), findsOneWidget);
    await tester.drag(find.byType(ListView).first, const Offset(0, 800));
    await tester.pumpAndSettle();
    expect(find.text('我的 1'), findsOneWidget);
    await tester.tap(find.text('我的 1'));
    await tester.pumpAndSettle();

    expect(find.text('莲藕'), findsOneWidget);
    expect(find.text('1'), findsOneWidget);
    expect(find.textContaining('节'), findsNothing);
    expect(find.byTooltip('删除莲藕'), findsOneWidget);
  });

  testWidgets('个人页统计卡可进入库存并编辑口味', (tester) async {
    await tester.pumpWidget(ShishiApp(key: UniqueKey()));

    await tester.tap(find.text('我的'));
    await tester.pumpAndSettle();

    final preferencesCard = find.text('口味偏好').first;
    await tester.scrollUntilVisible(
      preferencesCard,
      180,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(preferencesCard);
    await tester.pumpAndSettle();
    expect(find.text('编辑口味偏好'), findsOneWidget);
    expect(find.text('保存设置'), findsOneWidget);

    await tester.tap(find.text('保存设置'));
    await tester.pumpAndSettle();

    final pantryCard = find.text('我的食材').first;
    await tester.scrollUntilVisible(
      pantryCard,
      -120,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(pantryCard);
    await tester.pumpAndSettle();
    expect(find.text('我家的食材'), findsWidgets);
  });

  testWidgets('首页快速选一餐打开轻量推荐面板', (tester) async {
    await tester.pumpWidget(ShishiApp(key: UniqueKey()));

    final quickMeal = find.text('快速选一餐');
    await tester.scrollUntilVisible(
      quickMeal,
      260,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(quickMeal);
    await tester.pumpAndSettle();

    expect(find.text('今日一餐灵感'), findsOneWidget);
    expect(find.text('换一个'), findsOneWidget);
    expect(find.text('查看做法'), findsOneWidget);
    expect(find.text('让 AI 帮我搭配'), findsOneWidget);
  });
}
