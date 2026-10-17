import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mealmind/pages/ai.dart';
import 'package:mealmind/models/content.dart';
import 'package:mealmind/services/api_config.dart';
import 'package:mealmind/services/backend_api.dart';
import 'package:mealmind/services/auth_store.dart';
import 'package:mealmind/services/chat_session_store.dart';

const dish = Recipe(
  id: '2',
  name: '番茄炒蛋',
  image: 'assets/images/tomato-egg.jpg',
  desc: '',
  time: '15分钟',
  people: '',
  tags: [],
);

Future<void> submit(WidgetTester tester, String message) async {
  await tester.enterText(find.byType(TextField).last, message);
  await tester.testTextInput.receiveAction(TextInputAction.send);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    BackendStatus.instance.setOfflineForTesting();
  });

  testWidgets(
    'failed request can retry without duplicating user messages; successful cards survive page recreation',
    (tester) async {
      var calls = 0;
      Future<AiChatResult?> request(String message, bool useAi) async {
        calls++;
        if (calls == 1) throw Exception('network failure');
        return const AiChatResult(
          answer: '重试完成',
          intent: 'meal_recommendation',
          recipes: [dish],
        );
      }

      await tester.pumpWidget(MaterialApp(home: AiPage(request: request)));
      await tester.pumpAndSettle();
      await submit(tester, '推荐一道菜');
      await tester.pumpAndSettle();
      expect(calls, 1);
      expect(find.text('重试'), findsOneWidget);
      await tester.ensureVisible(find.text('重试'));
      await tester.tap(find.text('重试'));
      await tester.pumpAndSettle();
      expect(find.text('重试完成'), findsOneWidget);
      final scope =
          '${BackendStatus.instance.apiBase}:${AuthStore.instance.user?.id ?? 'guest'}';
      final saved = await ChatSessionStore.load(scope);
      final users = (saved!['messages'] as List).where(
        (m) => m['kind'] == 'user' && m['text'] == '推荐一道菜',
      );
      expect(users.length, 1);
      expect(find.text('整组加入今日菜单'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(MaterialApp(home: AiPage(request: request)));
      await tester.pumpAndSettle();
      expect(find.text('重试完成'), findsOneWidget);
      expect(find.text('番茄炒蛋'), findsOneWidget);
      expect(calls, 2);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'switching to rules ignores a late model response and keeps one user turn',
    (tester) async {
      final delayed = Completer<AiChatResult?>();
      final modes = <bool>[];
      await tester.pumpWidget(
        MaterialApp(
          home: AiPage(
            request: (message, useAi) {
              modes.add(useAi);
              return useAi
                  ? delayed.future
                  : Future.value(
                      const AiChatResult(
                        answer: '规则结果',
                        intent: 'meal_recommendation',
                        recipes: [dish],
                      ),
                    );
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      await submit(tester, '推荐一道菜');
      await tester.tap(find.text('改用规则处理'));
      await tester.pumpAndSettle();
      delayed.complete(
        const AiChatResult(answer: '过期的模型回答', intent: 'meal_recommendation'),
      );
      await tester.pumpAndSettle();
      expect(modes, [true, false]);
      expect(find.text('规则结果'), findsOneWidget);
      expect(find.text('过期的模型回答'), findsNothing);
      expect(find.text('推荐一道菜'), findsOneWidget);
      expect(find.text('停止等待'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}
