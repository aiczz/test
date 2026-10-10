import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealmind/pages/foods.dart';
import 'package:mealmind/services/content_store.dart';

void main() {
  testWidgets('食材分类可多选，时令组合筛选，全部清空选择', (tester) async {
    await tester.pumpWidget(MaterialApp(home: FoodsPage(onAskAi: (_) {})));
    await tester.pumpAndSettle();

    Finder chip(String label) => find.widgetWithText(FilterChip, label);
    bool selected(String label) =>
        tester.widget<FilterChip>(chip(label)).selected;
    Future<void> toggle(String label) async {
      await tester.ensureVisible(chip(label));
      await tester.tap(chip(label));
      await tester.pumpAndSettle();
    }

    expect(chip('主食'), findsNothing);
    expect(chip('其他'), findsNothing);
    expect(selected('全部'), isTrue);

    await toggle('蔬菜');
    await toggle('水果');
    expect(selected('蔬菜'), isTrue);
    expect(selected('水果'), isTrue);
    expect(selected('全部'), isFalse);
    final foods = ContentStore.instance.foods;
    final combined = foods.where(
      (food) => food.category == '蔬菜' || food.category == '水果',
    );
    expect(find.text('${combined.length} 项'), findsOneWidget);

    await toggle('时令');
    expect(selected('蔬菜'), isTrue);
    expect(selected('水果'), isTrue);
    final seasonal = combined.where(ContentStore.instance.isSeasonal);
    expect(find.text('${seasonal.length} 项'), findsOneWidget);

    await toggle('蔬菜');
    expect(selected('蔬菜'), isFalse);
    expect(selected('水果'), isTrue);
    final fruit = foods.where(
      (food) => food.category == '水果' && ContentStore.instance.isSeasonal(food),
    );
    expect(find.text('${fruit.length} 项'), findsOneWidget);

    await toggle('全部');
    expect(selected('全部'), isTrue);
    expect(selected('时令'), isFalse);
    expect(selected('水果'), isFalse);
    expect(find.text('${foods.length} 项'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('窄屏全选条件后标题与数量保持单行居中', (tester) async {
    tester.view.physicalSize = const Size(360, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(home: FoodsPage(onAskAi: (_) {})));
    await tester.pumpAndSettle();

    for (final label in ['时令', '蔬菜', '水果', '肉蛋', '水产', '豆制品']) {
      final chip = find.widgetWithText(FilterChip, label);
      await tester.ensureVisible(chip);
      await tester.tap(chip);
      await tester.pumpAndSettle();
      expect(tester.widget<FilterChip>(chip).selected, isTrue);
    }
    final title = find.text('筛选结果');
    await tester.ensureVisible(title);
    await tester.pumpAndSettle();
    expect(title, findsOneWidget);
    expect(tester.widget<Text>(title).maxLines, 1);
    final count = find.textContaining(RegExp(r'^\d+ 项$'));
    expect(count, findsOneWidget);
    expect(tester.getCenter(title).dy, closeTo(tester.getCenter(count).dy, 1));
    expect(tester.takeException(), isNull);
  });
}
