from app.ai import client as ai_client
from app.core.config import settings
from app.schemas.ai import AiReference, AiUnderstanding, AiUnderstandingSlots


def understood(intent='recommend_foods', operation='new', *, reference=None, detail_kind=None, **slots):
    return AiUnderstanding(
        intent=intent,
        operation=operation,
        confidence=0.97,
        slots=AiUnderstandingSlots(**slots),
        reference=reference,
        detail_kind=detail_kind,
    )


def foods_to_recipes():
    return understood(
        intent='meal_recommendation', operation='detail', detail_kind='food_recipes',
        reference=AiReference(kind='food', all=True),
    )


def test_recommended_foods_can_be_used_without_pantry(client, stub_chat_understanding):
    stub_chat_understanding({
        '推荐一些食材': understood(),
        '用这些食材推荐菜谱': foods_to_recipes(),
        '用上面的': foods_to_recipes(),
    })
    first = client.post('/api/ai/chat', json={
        'message': '推荐一些食材', 'cook_minutes': 240,
    }).json()
    ids = [food['id'] for food in first['foods']]
    assert ids == first['conversation_state']['last_recommended_food_ids']
    second = client.post('/api/ai/chat', json={
        'message': '用这些食材推荐菜谱', 'cook_minutes': 240,
        'last_intent': first['intent'], 'conversation_state': first['conversation_state'],
    }).json()
    assert second['intent'] == 'meal_recommendation'
    assert second['recipes']
    assert '库存' not in second['tools_used']
    assert '现在还是空的' not in second['answer']
    third = client.post('/api/ai/chat', json={
        'message': '用上面的', 'cook_minutes': 240,
        'last_intent': second['intent'], 'conversation_state': second['conversation_state'],
    }).json()
    assert third['intent'] == 'meal_recommendation'
    assert third['recipes']


def test_missing_reference_asks_instead_of_using_pantry(client, stub_chat_understanding):
    stub_chat_understanding(foods_to_recipes())
    body = client.post('/api/ai/chat', json={'message': '用上面的'}).json()
    assert body['needs_clarification']
    assert not body['recipes']
    assert '可引用的食材' in body['answer']


def test_visible_food_reference_supports_existing_conversation(client, stub_chat_understanding):
    stub_chat_understanding({
        '推荐一些食材': understood(),
        '用这些食材推荐菜谱': foods_to_recipes(),
    })
    first = client.post('/api/ai/chat', json={'message': '推荐一些食材'}).json()
    body = client.post('/api/ai/chat', json={
        'message': '用这些食材推荐菜谱', 'cook_minutes': 240,
        'context_food_ids': [food['id'] for food in first['foods']],
    }).json()
    assert body['intent'] == 'meal_recommendation' and body['recipes']


def test_general_question_receives_bounded_history(client, monkeypatch, stub_chat_understanding):
    stub_chat_understanding(understood(intent='general', operation='answer'))
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    captured = []

    def network(messages, **kwargs):
        captured.extend(messages)
        return ai_client.AiResult(ok=True, data={'answer': '可以继续说明莲藕。'})

    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    history = [{'role': 'user', 'content': '刚才说的食材是莲藕'},
               {'role': 'assistant', 'content': '已经记住莲藕。'}] * 4
    body = client.post('/api/ai/chat', json={
        'message': '上面的怎么保存', 'conversation_state': {'history': history},
    }).json()
    assert any(turn['content'] == '刚才说的食材是莲藕' for turn in captured)
    assert len(body['conversation_state']['history']) == 8
    assert body['conversation_state']['history'][-2]['content'] == '上面的怎么保存'
