"""单一语义理解入口、失败止损和结构化合同测试。"""
from __future__ import annotations

import pytest

from app.ai import client as ai_client
from app.schemas.ai import (
    AiChatRequest,
    AiConversationState,
    AiReference,
    AiUnderstanding,
    AiUnderstandingSlots,
)
from app.services import ai_service, need_service


def understanding(**changes):
    values = {
        'intent': 'meal_recommendation',
        'operation': 'new',
        'confidence': 0.96,
        'slots': AiUnderstandingSlots(),
    }
    values.update(changes)
    return AiUnderstanding(**values)


def test_semantic_router_unavailable_stops_without_keyword_fallback(session, monkeypatch):
    monkeypatch.setattr(ai_service.client, 'is_configured', lambda: False)
    monkeypatch.setattr(ai_service, '_route', lambda **kwargs: pytest.fail('主链路不得退回关键词猜测'))
    route = ai_service._route_smart(session=session, message='推荐点食材', payload=None)
    assert route.intent == 'unknown'
    assert route.source == 'unavailable'
    assert route.understanding is None
    assert '没有执行推荐' in route.clarification


def test_semantic_router_uses_the_structured_model_result(session, monkeypatch):
    expected = understanding(
        intent='recommend_foods',
        slots=AiUnderstandingSlots(dish_count=5, health_goal='健身增肌'),
    )
    monkeypatch.setattr(ai_service.client, 'is_configured', lambda: True)
    monkeypatch.setattr(ai_service.client, 'complete_json', lambda *args, **kwargs:
                        ai_client.AiResult(ok=True, data=expected.model_dump(mode='json')))
    route = ai_service._route_semantic(session=session, message='任意表达', payload=None)
    assert route.intent == 'recommend_foods'
    assert route.dish_count == 5
    assert route.understanding == expected
    assert route.source == 'ai'


@pytest.mark.parametrize('result', [
    ai_client.AiResult(ok=False, error='超时'),
    ai_client.AiResult(ok=True, data={}),
    ai_client.AiResult(ok=True, data={'intent': 'not-an-intent'}),
])
def test_semantic_failure_or_invalid_contract_is_not_guessed(session, monkeypatch, result):
    monkeypatch.setattr(ai_service.client, 'is_configured', lambda: True)
    monkeypatch.setattr(ai_service.client, 'complete_json', lambda *args, **kwargs: result)
    route = ai_service._route_semantic(session=session, message='随便说', payload=None)
    assert route.intent == 'unknown'
    assert route.understanding is None
    assert route.clarification


def test_low_confidence_returns_clarification_without_execution(client, monkeypatch):
    prior = AiConversationState(people=4, recommendation_count=5, avoid_added=['花生'])
    monkeypatch.setattr(ai_service.client, 'is_configured', lambda: True)
    monkeypatch.setattr(ai_service.client, 'complete_json', lambda *args, **kwargs:
                        ai_client.AiResult(ok=True, data=understanding(
                            intent='recommend_foods', confidence=0.4,
                            clarification='你想买食材，还是想做菜？',
                        ).model_dump(mode='json')))
    monkeypatch.setattr(ai_service.scoring_service, 'score_foods', lambda *args, **kwargs:
                        pytest.fail('低置信不能进入检索'))
    body = client.post('/api/ai/chat', json={
        'message': '随便来点', 'conversation_state': prior.model_dump(mode='json'),
    }).json()
    assert body['intent'] == 'unknown'
    assert body['needs_clarification']
    assert not body['foods'] and not body['recipes']
    assert body['conversation_state']['people'] == 4
    assert body['conversation_state']['recommendation_count'] == 5
    assert body['conversation_state']['avoid_added'] == ['花生']


def test_unknown_understanding_drops_unexecutable_detail_metadata():
    cleaned = ai_service._validate_understanding(understanding(
        intent='unknown', confidence=0.4, operation='detail',
        detail_kind='steps', reference=AiReference(kind='recipe', ordinal=1),
        clarification='你想看哪道菜的做法？',
    ))
    assert cleaned.intent == 'unknown'
    assert cleaned.operation == 'new'
    assert cleaned.detail_kind is None
    assert cleaned.reference is None
    assert cleaned.clarification == '你想看哪道菜的做法？'


def test_invalid_detail_card_type_is_rejected():
    with pytest.raises(ValueError, match='意图不一致'):
        ai_service._validate_understanding(understanding(
            intent='recommend_foods', operation='detail', detail_kind='ingredients',
            reference=AiReference(kind='recipe', ordinal=1),
        ))


def test_replace_requires_a_recipe_and_one_item():
    with pytest.raises(ValueError, match='单菜替换'):
        ai_service._validate_understanding(understanding(
            operation='replace', slots=AiUnderstandingSlots(dish_count=2),
        ))
    with pytest.raises(ValueError, match='引用菜谱'):
        ai_service._validate_understanding(understanding(
            operation='replace', reference=AiReference(kind='food', ordinal=1),
        ))


def test_reference_cannot_mix_selectors():
    with pytest.raises(ValueError, match='不能同时混用'):
        ai_service._validate_understanding(understanding(
            operation='replace',
            reference=AiReference(kind='recipe', name='清蒸鱼', ordinal=1),
        ))


def test_classify_prompt_contains_state_pending_and_all_labels():
    state = AiConversationState(people=4, last_intent='recommend_foods')
    prompt = ai_service._classify_prompt('家里有健身的', 'recommend_foods', state)
    for intent in ('meal_recommendation', 'recommend_foods',
                   'cook_with_my_foods', 'general', 'unknown'):
        assert intent in prompt
    for goal in need_service.all_goals():
        assert goal.name in prompt
    assert '家里有健身的' in prompt
    assert '"people": 4' in prompt
    assert 'pending' in prompt
    assert '只理解，不推荐菜' in prompt
    assert '必须是字符串数组' in prompt
    assert '是否登录、库存是否为空由代码核查' in prompt
    assert '必须继承上一轮 intent 并使用 refine' in prompt
    assert '硬菜' in prompt
    assert '不要用 unknown 反问' in prompt


def test_classify_prompt_without_context_is_explicit():
    prompt = ai_service._classify_prompt('你好', None)
    assert '【上一轮意图】无' in prompt
    assert '你好' in prompt


def test_food_prompt_is_buildable(session):
    from app.services.ai_service import _constraints, _weather_for
    from app.services.scoring_service import HardConstraints, ScoredItem

    payload = AiChatRequest(message='想补点钙', city='杭州')
    constraints = HardConstraints(people=3, cook_minutes=45)
    candidates = [ScoredItem(
        raw=None, item_id=1, name='牛奶', score=1.0, reason='',
        factors={'season': 80.0}, insight=None, highlights=[], quality=1.0, band=80.0,
    )]
    prompt = ai_service._food_prompt(
        session=session, payload=payload, constraints=constraints,
        weather=_weather_for(payload, 10), month=10, candidates=candidates,
        health_goal=need_service.extract_goal('想补钙'), count=3,
    )
    assert '候选食材' in prompt
    assert '牛奶' in prompt
    assert '只能从这里挑' in prompt
    assert '核心诉求' in prompt
    assert _constraints is not None


def test_food_candidate_lines_format():
    from app.services.scoring_service import ScoredItem
    item = ScoredItem(
        raw=None, item_id=42, name='鸡胸肉', score=1.0, reason='',
        factors={'season': 70.0}, insight=None, highlights=[], quality=1.0, band=70.0,
    )
    lines = ai_service._food_candidate_lines(None, [item])
    assert len(lines) == 1
    assert lines[0].startswith('42 | 鸡胸肉')
