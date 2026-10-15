import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mealmind/pages/ai.dart';
import 'package:mealmind/services/api_config.dart';
import 'package:mealmind/services/auth_store.dart';
import 'package:mealmind/services/chat_session_store.dart';

void main() {
  testWidgets('restores visible conditions and new conversation clears them', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final scope =
        '${BackendStatus.instance.apiBase}:${AuthStore.instance.user?.id ?? 'guest'}';
    await ChatSessionStore.save(scope, {
      'state': {
        'people': 2,
        'cook_minutes': 15,
        'avoid_added': ['花生'],
      },
      'effective': {
        'people': 2,
        'cook_minutes': 15,
        'avoid': ['花生'],
        'preferences': [],
        'low_sodium': false,
      },
      'categories': ['汤羹'],
      'intent': 'meal_recommendation',
      'recipes': [1],
    });
    await tester.pumpWidget(const MaterialApp(home: AiPage()));
    await tester.pumpAndSettle();
    expect(find.textContaining('本次条件：2人'), findsOneWidget);
    expect(find.textContaining('忌口：花生'), findsOneWidget);
    await tester.tap(find.text('编辑条件'));
    await tester.pumpAndSettle();
    expect(find.text('修改本次会话条件'), findsOneWidget);
    expect(find.text('不喝汤'), findsOneWidget);
    await tester.tap(find.text('取消').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('开始新会话'));
    await tester.pumpAndSettle();
    expect(find.textContaining('本次条件：2人'), findsNothing);
    expect(await ChatSessionStore.load(scope), isNull);
  });
  testWidgets(
    'editor validates numbers and saves explicit conditions for reload',
    (tester) async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      BackendStatus.instance.setOfflineForTesting();
      final scope =
          '${BackendStatus.instance.apiBase}:${AuthStore.instance.user?.id ?? 'guest'}';
      await tester.pumpWidget(const MaterialApp(home: AiPage()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('编辑条件'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField).at(0), '21');
      await tester.tap(find.text('保存并推荐'));
      await tester.pump();
      expect(find.text('请输入1至20的整数'), findsOneWidget);
      await tester.enterText(find.byType(TextFormField).at(0), '2');
      await tester.enterText(find.byType(TextFormField).at(1), '15');
      await tester.enterText(find.byType(TextFormField).at(2), '花生');
      await tester.tap(find.text('保存并推荐'));
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 500));
      }
      await tester.pumpAndSettle();
      final saved = await ChatSessionStore.load(scope);
      expect((saved!['state'] as Map)['people'], 2);
      expect((saved['state'] as Map)['cook_minutes'], 15);
      expect((saved['state'] as Map)['avoid_added'], contains('花生'));
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpWidget(const MaterialApp(home: AiPage()));
      await tester.pumpAndSettle();
      expect(find.textContaining('本次条件：2人'), findsOneWidget);
    },
  );
}
