import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mealmind/main.dart';
import 'package:mealmind/pages/login.dart';
import 'package:mealmind/services/api_config.dart';
import 'package:mealmind/pages/admin.dart';
import 'package:mealmind/pages/shopping.dart';
import 'package:mealmind/widgets/city_picker.dart';
import 'package:mealmind/widgets/ai_compose_sheet.dart';
import 'package:mealmind/widgets/menu_actions.dart';
import 'package:mealmind/state/today_menu.dart';
import 'package:mealmind/data/mock.dart';

void main() {
  for (final width in [320.0, 375.0, 430.0]) {
    testWidgets('secondary pages and city picker fit $width with large text', (
      tester,
    ) async {
      SharedPreferences.setMockInitialValues({});
      BackendStatus.instance.setOfflineForTesting();
      tester.view.physicalSize = Size(width, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      Widget frame(Widget page) => MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(1.5)),
          child: child!,
        ),
        home: page,
      );
      await tester.pumpWidget(frame(const AdminPage()));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'admin $width');
      await tester.drag(find.byType(Scrollable).first, const Offset(0, -600));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'admin scrolled $width');
      await tester.pumpWidget(
        frame(
          const ShoppingPage(
            initial: {
              'title': '今日菜单购物清单',
              'total_items': 1,
              'warnings': ['数量不明确的食材请按照实际菜谱核对后再购买'],
              'categories': [
                {
                  'category': '蔬菜',
                  'items': [
                    {
                      'id': 1,
                      'name': '需要核对的较长食材名称',
                      'amount': 400,
                      'unit': '克',
                      'needs_confirmation': false,
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
      expect(tester.takeException(), isNull, reason: 'shopping $width');
      await tester.pumpWidget(
        frame(
          Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () => showCityPicker(context),
                child: const Text('选择城市'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('选择城市'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'city picker $width');
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      await tester.pumpWidget(
        frame(
          Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () => showAiComposeSheet(context),
                child: const Text('配菜面板'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('配菜面板'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'compose sheet $width');
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      TodayMenuStore.instance.setItems(mockRecipes.take(3).toList());
      await tester.pumpAndSettle();
      await tester.pumpWidget(
        frame(
          const Scaffold(
            bottomNavigationBar: Padding(
              padding: EdgeInsets.all(16),
              child: MenuActions(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'menu toolbar $width');
      await tester.tap(find.text('更多'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: 'menu options $width');
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
    });
    for (final scale in [1.0, 1.3, 1.5]) {
      testWidgets('main pages fit width $width and text scale $scale', (
        tester,
      ) async {
        SharedPreferences.setMockInitialValues({});
        BackendStatus.instance.setOfflineForTesting();
        tester.view.physicalSize = Size(width, 900);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        await tester.pumpWidget(
          MediaQuery(
            data: MediaQueryData(textScaler: TextScaler.linear(scale)),
            child: const ShishiApp(),
          ),
        );
        await tester.pumpAndSettle();
        for (final tab in ['首页', '食材', '菜谱', 'AI', '我的']) {
          await tester.tap(
            find.descendant(
              of: find.byType(NavigationBar),
              matching: find.text(tab),
            ),
          );
          await tester.pumpAndSettle();
          expect(
            tester.takeException(),
            isNull,
            reason: '$tab at $width / $scale',
          );
          if (find.byType(Scrollable).evaluate().isNotEmpty) {
            for (var scroll = 0; scroll < 3; scroll++) {
              await tester.drag(
                find.byType(Scrollable).first,
                const Offset(0, -550),
              );
              await tester.pumpAndSettle();
              expect(
                tester.takeException(),
                isNull,
                reason: '$tab scrolled at $width / $scale',
              );
            }
          }
        }
      });
    }
    testWidgets('login fits width $width', (tester) async {
      SharedPreferences.setMockInitialValues({});
      BackendStatus.instance.setOfflineForTesting();
      tester.view.physicalSize = Size(width, 700);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(const MaterialApp(home: LoginPage()));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
}
