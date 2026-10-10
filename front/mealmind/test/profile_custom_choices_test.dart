import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mealmind/pages/profile.dart';
import 'package:mealmind/state/app_state.dart';

void main() {
  testWidgets('移除厨具板块，自定义偏好和忌口可添加、取消并保存', (tester) async {
    tester.view.physicalSize = const Size(800, 2600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues({});
    AppState.instance.debugResetMemory();
    await tester.pumpWidget(
      MaterialApp(
        home: ProfilePage(onOpenRecipes: () {}, onOpenPantry: () {}),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('可用厨具'), findsNothing);
    expect(find.widgetWithText(ActionChip, '自定义'), findsNWidgets(2));

    Future<void> addCustom(int index, String value) async {
      final button = find.widgetWithText(ActionChip, '自定义').at(index);
      await tester.ensureVisible(button);
      await tester.pumpAndSettle();
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(find.textContaining('例如'), findsNothing);
      await tester.enterText(find.byType(TextFormField), value);
      await tester.tap(find.widgetWithText(FilledButton, '添加'));
      await tester.pumpAndSettle();
    }

    await addCustom(0, '  酸甜  ');
    final preference = find.widgetWithText(FilterChip, '酸甜');
    expect(tester.widget<FilterChip>(preference).selected, isTrue);
    await tester.tap(preference);
    await tester.pumpAndSettle();
    expect(tester.widget<FilterChip>(preference).selected, isFalse);
    await addCustom(0, '酸甜');
    expect(preference, findsOneWidget);
    expect(tester.widget<FilterChip>(preference).selected, isTrue);

    await addCustom(1, '芝麻');
    expect(
      tester.widget<FilterChip>(find.widgetWithText(FilterChip, '芝麻')).selected,
      isTrue,
    );
    final save = find.text('保存家庭档案');
    await tester.ensureVisible(save);
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(AppState.instance.profile.preferences, contains('酸甜'));
    expect(AppState.instance.profile.avoid, contains('芝麻'));
    final prefs = await SharedPreferences.getInstance();
    final cached =
        jsonDecode(prefs.getString('family_profile')!) as Map<String, dynamic>;
    expect(cached['preferences'], contains('酸甜'));
    expect(cached['avoid'], contains('芝麻'));
    expect(
      AppState.instance.profile.toServerJson()['preferences'],
      contains('酸甜'),
    );
    expect(
      AppState.instance.profile.toServerJson()['avoid_foods'],
      contains('芝麻'),
    );

    expect(
      tester
          .widget<FilterChip>(find.widgetWithText(FilterChip, '家常'))
          .onDeleted,
      isNull,
    );
    await tester.tap(find.byTooltip('删除酸甜'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(FilterChip, '酸甜'), findsNothing);

    // 快捷编辑弹层也能删除，删除后保存且主页面同步移除。
    await tester.ensureVisible(find.text('忌口').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('忌口').first);
    await tester.pumpAndSettle();
    expect(find.text('编辑忌口与过敏'), findsOneWidget);
    await tester.tap(find.byTooltip('删除芝麻').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('保存设置'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(FilterChip, '芝麻'), findsNothing);
    expect(AppState.instance.profile.preferences, isNot(contains('酸甜')));
    expect(AppState.instance.profile.avoid, isNot(contains('芝麻')));
    final afterDelete =
        jsonDecode(prefs.getString('family_profile')!) as Map<String, dynamic>;
    expect(afterDelete['preferences'], isNot(contains('酸甜')));
    expect(afterDelete['avoid'], isNot(contains('芝麻')));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(
      MaterialApp(
        home: ProfilePage(onOpenRecipes: () {}, onOpenPantry: () {}),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.widgetWithText(FilterChip, '酸甜'), findsNothing);
    expect(find.widgetWithText(FilterChip, '芝麻'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
