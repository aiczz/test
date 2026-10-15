import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mealmind/pages/shopping.dart';
import 'package:mealmind/widgets/menu_actions.dart';
import 'package:mealmind/services/api_config.dart';
import 'package:mealmind/state/today_menu.dart';

void main() {
  testWidgets('shopping page distinguishes known and unknown amounts', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ShoppingPage(
          initial: {
            'title': '今日菜单 · 购物清单',
            'warnings': ['未按人数缩放'],
            'total_items': 2,
            'categories': [
              {
                'category': '蔬菜',
                'items': [
                  {
                    'id': 1,
                    'name': '莲藕',
                    'amount': 400.0,
                    'unit': '克',
                    'needs_confirmation': false,
                    'checked': false,
                  },
                  {
                    'id': 2,
                    'name': '盐',
                    'amount': 0.0,
                    'unit': '适量',
                    'needs_confirmation': true,
                    'checked': false,
                  },
                ],
              },
            ],
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('400.0 克'), findsOneWidget);
    expect(find.text('用量待确认 · 适量'), findsOneWidget);
    expect(find.text('0.0 适量'), findsNothing);
  });
  testWidgets('offline menu actions do not claim cloud save succeeded', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    BackendStatus.instance.setOfflineForTesting();
    TodayMenuStore.instance.clear();
    await TodayMenuStore.instance.flush();
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: MenuActions())),
      ),
    );
    await tester.tap(find.text('保存到云端'));
    await tester.pumpAndSettle();
    expect(find.textContaining('连接后端并登录'), findsOneWidget);
  });
}
