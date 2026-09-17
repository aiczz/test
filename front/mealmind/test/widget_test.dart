import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:mealmind/main.dart';

void main() {
  testWidgets('五个主入口可用，食材页能正常打开', (tester) async {
    await tester.pumpWidget(const ShishiApp());

    expect(find.text('今天吃什么'), findsOneWidget);
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('首页'), findsOneWidget);
    expect(find.text('食材'), findsOneWidget);
    expect(find.text('菜谱'), findsOneWidget);
    expect(find.text('AI助手'), findsOneWidget);
    expect(find.text('我的'), findsOneWidget);

    await tester.tap(find.text('食材'));
    await tester.pumpAndSettle();

    expect(find.text('时令食材'), findsOneWidget);
    expect(find.text('秋季时令食材'), findsOneWidget);
  });
}
