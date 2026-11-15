import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealmind/services/api_config.dart';
import 'package:mealmind/widgets/lazy_photo.dart';

void main() {
  setUp(() => BackendStatus.instance.setOfflineForTesting());

  testWidgets(
    'offscreen image creates no Image; scrolling loads local fallback',
    (tester) async {
      final scroll = ScrollController();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              controller: scroll,
              child: const Column(
                children: [
                  SizedBox(height: 900),
                  SizedBox(
                    width: 180,
                    height: 100,
                    child: LazyPhoto(
                      kind: 'food',
                      name: '番茄',
                      fallback: 'assets/images/ingredient_tomato.jpg',
                    ),
                  ),
                  SizedBox(height: 900),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(Image), findsNothing);
      scroll.jumpTo(850);
      await tester.pump();
      await tester.pump();
      expect(find.byType(Image), findsOneWidget);
      final image = tester.widget<Image>(find.byType(Image));
      expect(image.image, isA<AssetImage>());
      await tester.pumpWidget(const SizedBox());
      scroll.dispose();
    },
  );

  testWidgets('empty or broken source renders a stable placeholder', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: SizedBox(
          width: 100,
          height: 100,
          child: LazyPhoto(kind: 'recipe', name: '缺图菜谱'),
        ),
      ),
    );
    await tester.pump();
    expect(find.byIcon(Icons.restaurant_outlined), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('bottom sheet loads visible photo after its entrance animation', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showModalBottomSheet<void>(
                context: context,
                builder: (_) => const SizedBox(
                  height: 300,
                  child: Align(
                    alignment: Alignment.topCenter,
                    child: SizedBox(
                      width: 180,
                      height: 100,
                      child: LazyPhoto(
                        kind: 'food',
                        name: '圣女果',
                        fallback: 'assets/images/food-0039-cherry-tomato.jpg',
                      ),
                    ),
                  ),
                ),
              ),
              child: const Text('Open detail'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open detail'));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsOneWidget);
    expect(tester.widget<Image>(find.byType(Image)).image, isA<AssetImage>());
    expect(tester.takeException(), isNull);
  });
}
