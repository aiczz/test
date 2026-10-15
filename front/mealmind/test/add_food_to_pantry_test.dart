import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mealmind/widgets/add_food_to_pantry.dart';
import 'package:mealmind/models/content.dart';
import 'package:mealmind/services/auth_store.dart';

void main() {
  testWidgets('adding requires login and does not claim success', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    await AuthStore.instance.logout();
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: AddFoodToPantryButton(
            food: Food(
              id: '1',
              name: '莲藕',
              image: '',
              category: '蔬菜',
              tags: [],
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('加入我的食材'));
    await tester.pumpAndSettle();
    expect(find.text('请先登录，再加入我的食材'), findsOneWidget);
    expect(find.text('已加入我的食材'), findsNothing);
  });
}
