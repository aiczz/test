from app.ai import client as ai_client
from app.core.config import settings


def test_recommended_foods_can_be_used_without_pantry(client):
    first = client.post('/api/ai/chat', json={
        'message': '推荐一些食材', 'use_ai': False, 'cook_minutes': 240,
    }).json()
    ids = [food['id'] for food in first['foods']]
    assert ids == first['conversation_state']['last_recommended_food_ids']
    second = client.post('/api/ai/chat', json={
        'message': '用这些食材推荐菜谱', 'use_ai': False, 'cook_minutes': 240,
        'last_intent': first['intent'], 'conversation_state': first['conversation_state'],
    }).json()
    assert second['intent'] == 'meal_recommendation'
    assert second['recipes']
    assert '库存' not in second['tools_used']
    assert '现在还是空的' not in second['answer']
    third = client.post('/api/ai/chat', json={
        'message': '用上面的', 'use_ai': False, 'cook_minutes': 240,
        'last_intent': second['intent'], 'conversation_state': second['conversation_state'],
    }).json()
    assert third['intent'] == 'meal_recommendation'
    assert third['recipes']


def test_missing_reference_asks_instead_of_using_pantry(client):
    body = client.post('/api/ai/chat', json={'message': '用上面的', 'use_ai': False}).json()
    assert body['needs_clarification']
    assert not body['recipes']
    assert '可引用的食材' in body['answer']


def test_visible_food_reference_supports_existing_conversation(client):
    first = client.post('/api/ai/chat', json={'message': '推荐一些食材', 'use_ai': False}).json()
    body = client.post('/api/ai/chat', json={
        'message': '用这些食材推荐菜谱', 'use_ai': False, 'cook_minutes': 240,
        'context_food_ids': [food['id'] for food in first['foods']],
    }).json()
    assert body['intent'] == 'meal_recommendation' and body['recipes']


def test_general_question_receives_bounded_history(client, monkeypatch):
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
