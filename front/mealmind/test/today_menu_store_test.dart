import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mealmind/models/content.dart';
import 'package:mealmind/state/today_menu.dart';

Recipe dish(String id, {String image = 'assets/images/tomato-egg.jpg'}) =>
    Recipe(
      id: id,
      name: '菜$id',
      image: image,
      desc: '',
      time: '15分钟',
      people: '',
      tags: const [],
    );
void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));
  test(
    'unillustrated recipes cannot enter or replace a visible menu',
    () async {
      final store = TodayMenuStore(scopeProvider: () => 'image-filter');
      await store.load();
      expect(store.add(dish('1', image: '')), isFalse);
      store.setItems([dish('1', image: ''), dish('2')]);
      expect(store.items.map((r) => r.id), ['2']);
      store.replace('2', dish('3', image: ''));
      expect(store.items.map((r) => r.id), ['2']);
      await store.flush();
      await store.load();
      expect(store.items.map((r) => r.id), ['2']);
    },
  );
  test(
    'menu edits survive restart and replacement preserves other dishes',
    () async {
      final first = TodayMenuStore(
        scopeProvider: () => 'u1',
        clock: () => DateTime(2026, 10, 14),
      );
      await first.load();
      first.add(dish('1'));
      first.add(dish('2'));
      first.replace('1', dish('3'));
      await first.flush();
      final restored = TodayMenuStore(
        scopeProvider: () => 'u1',
        clock: () => DateTime(2026, 10, 14),
      );
      await restored.load();
      expect(restored.items.map((r) => r.id), ['3', '2']);
      restored.replace('3', dish('2'));
      expect(restored.count, 2);
      restored.remove('3');
      await restored.flush();
      await first.load();
      expect(first.items.map((r) => r.id), ['2']);
      first.dispose();
      restored.dispose();
    },
  );
  test(
    'dates and accounts remain independent and retain historical menus',
    () async {
      var scope = 'u1';
      var date = DateTime(2026, 10, 14);
      final store = TodayMenuStore(
        scopeProvider: () => scope,
        clock: () => date,
      );
      await store.load();
      store.add(dish('1'));
      await store.flush();
      scope = 'u2';
      await store.load();
      expect(store.isEmpty, true);
      store.add(dish('2'));
      await store.flush();
      scope = 'u1';
      date = DateTime(2026, 10, 15);
      await store.load();
      expect(store.isEmpty, true);
      date = DateTime(2026, 10, 14);
      await store.load();
      expect(store.items.single.id, '1');
      store.clear();
      await store.flush();
      await store.load();
      expect(store.isEmpty, true);
      store.dispose();
    },
  );
}
