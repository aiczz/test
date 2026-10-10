import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealmind/pages/recipes.dart';
import 'package:mealmind/services/content_store.dart';
import 'package:mealmind/state/today_menu.dart';

void main() {
  testWidgets('卡片按钮直接添加及删除今日菜单，不打开详情、不删除菜谱', (tester) async {
    TodayMenuStore.instance.clear();
    addTearDown(TodayMenuStore.instance.clear);
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final recipe = ContentStore.instance.recipes.first;
    final originalCount = ContentStore.instance.recipes.length;
    await tester.pumpWidget(const MaterialApp(home: RecipesPage()));
    await tester.pumpAndSettle();

    Future<void> press(String tooltip) async {
      final button = find.byTooltip(tooltip);
      await tester.ensureVisible(button);
      await tester.pumpAndSettle();
      await tester.tap(button);
      await tester.pumpAndSettle();
    }

    await press('将${recipe.name}加入今日菜单');
    expect(TodayMenuStore.instance.contains(recipe.id), isTrue);
    expect(find.text('加入今日菜单'), findsNothing);
    expect(find.byTooltip('从今日菜单移除${recipe.name}'), findsOneWidget);
    await press('从今日菜单移除${recipe.name}');
    expect(TodayMenuStore.instance.isEmpty, isTrue);

    await press('将${recipe.name}加入今日菜单');
    final tab = find.text('今日菜单 1');
    await tester.scrollUntilVisible(
      tab,
      -300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(tab);
    await tester.pumpAndSettle();
    await press('从今日菜单移除${recipe.name}');
    expect(TodayMenuStore.instance.isEmpty, isTrue);
    expect(find.textContaining('今日菜单还是空的'), findsOneWidget);
    expect(ContentStore.instance.recipes.length, originalCount);
    expect(tester.takeException(), isNull);
  });
}
