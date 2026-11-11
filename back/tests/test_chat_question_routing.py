import pytest

from app.schemas.ai import AiUnderstanding, AiUnderstandingSlots
from app.services import ai_service


def understood(intent='general', operation='new', **slots):
    return AiUnderstanding(
        intent=intent,
        operation=operation,
        confidence=0.97,
        slots=AiUnderstandingSlots(**slots),
    )


@pytest.mark.parametrize('message', [
    '为什么炒饭会粘锅', '莲藕怎么保存', '低钠是什么意思',
    '给我推荐一本小说', '帮我安排明天的会议', '账号怎么改成手机号',
])
def test_questions_do_not_return_recipes(client, stub_chat_understanding, message):
    stub_chat_understanding(understood())
    response = client.post('/api/ai/chat', json={
        'message': message, 'last_intent': 'meal_recommendation',
    })
    assert response.status_code == 200
    body = response.json()
    assert body['intent'] == 'general'
    assert body['recipes'] == []
    assert body['foods'] == []


def test_smart_router_has_no_keyword_bypass(monkeypatch):
    expected = understood()
    monkeypatch.setattr(ai_service, '_route', lambda **kwargs: pytest.fail('主路由不得调用旧关键词判断'))
    monkeypatch.setattr(
        ai_service, '_route_semantic',
        lambda **kwargs: ai_service._route_from_understanding(None, expected),
    )
    assert ai_service._route_smart(session=None, message='为什么炒饭会粘锅').intent == 'general'


def test_follow_up_after_general_does_not_resume_old_recipes(client, stub_chat_understanding):
    stub_chat_understanding({
        '推荐三道菜': understood(intent='meal_recommendation', dish_count=3),
        '还有吗': understood(operation='answer'),
    })
    first = client.post('/api/ai/chat', json={'message': '推荐三道菜', 'cook_minutes': 240}).json()
    result = client.post('/api/ai/chat', json={
        'message': '还有吗', 'last_intent': first['intent'],
        'conversation_state': first['conversation_state'],
    }).json()
    assert result['intent'] == 'general'
    assert not result['recipes'] and not result['foods']
    assert result['conversation_state']['recommendation_count'] == 3
    assert result['conversation_state']['last_recommended_recipe_ids'] == first['conversation_state']['last_recommended_recipe_ids']


@pytest.mark.parametrize('message', ['换一批呢', '再来三道菜', '推荐几道清淡的菜', '今晚吃什么'])
def test_recipe_requests_still_recommend(client, stub_chat_understanding, message):
    stub_chat_understanding(understood(intent='meal_recommendation', dish_count=3))
    body = client.post('/api/ai/chat', json={'message': message, 'cook_minutes': 240}).json()
    assert body['intent'] == 'meal_recommendation'
    assert body['recipes'] and not body['foods']


@pytest.mark.parametrize('message', [
    '推荐一些食材', '推荐一下食材', '推荐几种当季食材', '给我推荐适合秋天的食材',
    '推荐一些蔬菜', '帮我挑几种水果', '为晚餐推荐一些食材', '从我的食材中挑选几种食材',
])
@pytest.mark.parametrize('use_ai', [False, True])
def test_explicit_food_requests_never_return_recipes(client, stub_chat_understanding, message, use_ai):
    stub_chat_understanding(understood(intent='recommend_foods'))
    body = client.post('/api/ai/chat', json={
        'message': message, 'use_ai': use_ai, 'last_intent': 'meal_recommendation',
    }).json()
    assert body['intent'] == 'recommend_foods'
    assert body['foods']
    assert body['recipes'] == []


@pytest.mark.parametrize('message,intent', [
    ('用我的食材做菜', 'cook_with_my_foods'),
    ('用食材推荐几道菜', 'meal_recommendation'),
    ('推荐食材，再推荐几道菜', 'meal_recommendation'),
])
def test_recipe_target_is_not_confused_with_ingredients(message, intent):
    route = ai_service._route_from_understanding(None, understood(intent=intent))
    assert route.intent == intent


def test_general_question_reports_upstream_busy(client, monkeypatch):
    from app.ai.client import AiResult
    monkeypatch.setattr(ai_service.client, 'is_configured', lambda: True)
    monkeypatch.setattr(ai_service.client, 'complete_json', lambda *args, **kwargs:
                        AiResult(ok=False, error='HTTP 503', elapsed_ms=12))
    body = client.post('/api/ai/chat', json={'message': '低钠是什么意思'}).json()
    assert '繁忙' in body['answer']
    assert '繁忙' in body['trace'][-1]['summary']
    assert body['recipes'] == []
