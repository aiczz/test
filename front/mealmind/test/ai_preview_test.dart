import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mealmind/pages/ai.dart';
import 'package:mealmind/services/backend_api.dart';
import 'package:mealmind/services/api_config.dart';
import 'package:mealmind/models/content.dart';

void main() {
  for (final cancel in [false, true]) {
    testWidgets(
      'waits for ingredient answer without premature recipes; cancel=$cancel',
      (tester) async {
        SharedPreferences.setMockInitialValues({});
        BackendStatus.instance.setOfflineForTesting();
        final finalResult = Completer<AiChatResult?>();
        final phases = <bool>[];
        await tester.pumpWidget(
          MaterialApp(
            home: AiPage(
              request: (message, useAi) {
                phases.add(useAi);
                if (useAi) return finalResult.future;
                return Future.value(
                  const AiChatResult(
                    answer: '初选已就绪',
                    intent: 'meal_recommendation',
                    aiAvailable: true,
                  ),
                );
              },
            ),
          ),
        );
        await tester.pumpAndSettle();
        await tester.enterText(find.byType(TextField).last, '推荐一些食材');
        await tester.testTextInput.receiveAction(TextInputAction.send);
        await tester.pump(const Duration(milliseconds: 100));
        await tester.pump(const Duration(milliseconds: 100));
        expect(phases, [true]);
        expect(find.textContaining('初选已就绪'), findsNothing);
        expect(find.text('加入今日菜单'), findsNothing);
        if (cancel) {
          await tester.tap(find.text('停止等待'));
          await tester.pumpAndSettle();
        }
        finalResult.complete(
          const AiChatResult(
            answer: '最终结果已就绪',
            intent: 'recommend_foods',
            source: 'ai',
            foods: [
              Food(
                id: '1',
                name: '莲藕',
                image: 'assets/images/lotus-clean.jpg',
                category: '蔬菜',
                tags: [],
              ),
            ],
            recipes: [
              Recipe(
                id: '9',
                name: '不该展示的菜谱',
                image: '',
                desc: '',
                time: '',
                people: '',
                tags: [],
              ),
            ],
          ),
        );
        await tester.pumpAndSettle();
        expect(
          find.textContaining('最终结果已就绪'),
          cancel ? findsNothing : findsOneWidget,
        );
        expect(find.text('停止等待'), findsNothing);
        expect(find.text('不该展示的菜谱'), findsNothing);
        expect(find.text('加入今日菜单'), findsNothing);
        expect(find.text('莲藕'), cancel ? findsNothing : findsOneWidget);
      },
    );
  }
}
