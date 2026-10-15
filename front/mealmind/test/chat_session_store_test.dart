import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mealmind/services/chat_session_store.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('restores explicit edits and shown ids after reload', () async {
    final state = <String, dynamic>{
      'state': <String, dynamic>{
        'cook_minutes': 15,
        'avoid_added': ['花生'],
        'excluded_categories': ['汤羹'],
      },
      'intent': 'meal_recommendation',
      'recipes': [1, 2],
    };
    await ChatSessionStore.save('server:user1', state);
    expect(await ChatSessionStore.load('server:user1'), state);
  });

  test('account and backend scopes do not share conditions', () async {
    await ChatSessionStore.save('server:user1', {
      'state': {'people': 2},
    });
    expect(await ChatSessionStore.load('server:user2'), isNull);
    expect(await ChatSessionStore.load('other:user1'), isNull);
    await ChatSessionStore.clear('server:user1');
    expect(await ChatSessionStore.load('server:user1'), isNull);
  });

  test('invalid persisted state does not prevent starting a chat', () async {
    SharedPreferences.setMockInitialValues({
      ChatSessionStore.storageKey('test'): 'bad json',
    });
    expect(await ChatSessionStore.load('test'), isNull);
  });
}
