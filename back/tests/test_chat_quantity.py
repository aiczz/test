import pytest

from app.services.chat_context import requested_count


@pytest.fixture(autouse=True)
def sufficient_test_catalogue(session):
    from app.models.recipe import Recipe
    session.add(Recipe(name='清蒸南瓜', duration_minutes=15, category='素菜'))
    session.add(Recipe(name='清炒西葫芦', duration_minutes=15, category='素菜'))
    session.commit()


@pytest.mark.parametrize('message,count', [
    ('给我推荐5到菜谱', 5), ('给我推荐5道菜谱', 5), ('推荐五道菜', 5),
    ('三个人，30分钟，推荐五道菜', 5), ('推荐2人份菜谱', None),
    ('推荐五种食材', 5), ('给我推荐4个菜谱', 4), ('改成两道', 2),
    ('只要两个', 2), ('不要五道，改成三道', 3), ('推荐10道菜', 10),
    ('推荐五道菜，其中一道汤', 5), ('再来五个', 5),
])
def test_quantity_is_separate_from_people_and_time(message, count):
    assert requested_count(message) == count


@pytest.mark.parametrize('message', ['推荐0道菜', '推荐11道菜', '推荐一百道菜', '推荐2.5道菜'])
def test_invalid_quantity_is_explained(client, message):
    body = client.post('/api/ai/chat', json={'message': message, 'use_ai': False}).json()
    assert not body['recipes']
    assert '1至10' in body['answer']


@pytest.mark.parametrize('message', ['给我推荐5到菜谱', '给我推荐5道菜谱', '推荐五道菜'])
def test_five_recipes_are_returned(client, message):
    body = client.post('/api/ai/chat', json={
        'message': message, 'cook_minutes': 240, 'use_ai': False,
    }).json()
    assert body['requested_count'] == 5
    assert len(body['recipes']) == body['returned_count'] == 5
    assert body['effective_context']['people'] == 3
    assert body['conversation_state']['recommendation_count'] == 5


def test_quantity_persists_and_can_be_changed(client):
    first = client.post('/api/ai/chat', json={
        'message': '推荐五道菜', 'use_ai': False, 'cook_minutes': 240,
    }).json()
    second = client.post('/api/ai/chat', json={
        'message': '换一批', 'last_intent': first['intent'],
        'conversation_state': first['conversation_state'], 'use_ai': False, 'cook_minutes': 240,
    }).json()
    assert second['requested_count'] == 5 and len(second['recipes']) == 5
    third = client.post('/api/ai/chat', json={
        'message': '改成两道', 'last_intent': second['intent'],
        'conversation_state': second['conversation_state'], 'use_ai': False, 'cook_minutes': 240,
    }).json()
    assert third['requested_count'] == 2 and len(third['recipes']) == 2


def test_food_quantity_is_respected(client):
    body = client.post('/api/ai/chat', json={'message': '推荐五种食材', 'use_ai': False}).json()
    assert body['intent'] == 'recommend_foods'
    assert body['requested_count'] == 5 and len(body['foods']) == 5


def test_model_path_cannot_reduce_five_requested_to_three(client, monkeypatch):
    from app.ai import client as ai_client
    from app.core.config import settings
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    prompts = []
    def network(messages, **kwargs):
        prompts.append(messages[-1]['content'])
        return ai_client.AiResult(ok=True, data={'answer': '按条件挑好了这些菜。', 'picks': []})
    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    body = client.post('/api/ai/chat', json={'message': '推荐五道菜', 'cook_minutes': 240}).json()
    assert len(body['recipes']) == 5
    assert len(prompts) == 1 and 'picks 选 5 个' in prompts[0]


def test_shortage_does_not_silently_relax_constraints(client):
    body = client.post('/api/ai/chat', json={
        'message': '推荐十道菜，五分钟内', 'use_ai': False,
    }).json()
    assert body['requested_count'] == 10
    assert len(body['recipes']) < 10
    assert '只找到' in body['answer'] or '没有可核验' in body['answer']
