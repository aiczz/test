import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mealmind/services/recipe_feedback_store.dart';

void main() {
  test(
    'late feedback load from old account never leaks into new account',
    () async {
      var scope = 'a';
      final old = Completer<List<Map<String, dynamic>>>();
      final store = RecipeFeedbackStore(
        scope: () => scope,
        fetch: () => scope == 'a'
            ? old.future
            : Future.value([
                {'recipe_id': 2, 'value': 'dislike'},
              ]),
        save: (_, _, _) async {},
      );
      final waiting = store.load();
      scope = 'b';
      await store.load();
      old.complete([
        {'recipe_id': 1, 'value': 'like'},
      ]);
      await waiting;
      expect(store.value(1), 'neutral');
      expect(store.value(2), 'dislike');
      store.dispose();
    },
  );

  test(
    'failed write keeps saved preference; retry and revoke update it',
    () async {
      var shouldFail = true;
      final store = RecipeFeedbackStore(
        scope: () => 'a',
        fetch: () async => [
          {'recipe_id': 1, 'value': 'like'},
        ],
        save: (_, _, _) async {
          if (shouldFail) throw Exception('offline');
        },
      );
      await store.load();
      await expectLater(
        store.set(1, 'dislike', reason: '太费时'),
        throwsException,
      );
      expect(store.value(1), 'like');
      shouldFail = false;
      expect(await store.set(1, 'dislike', reason: '太费时'), isTrue);
      expect(store.value(1), 'dislike');
      await store.set(1, 'neutral');
      expect(store.value(1), 'neutral');
      store.dispose();
    },
  );
}
