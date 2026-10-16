import re

import pytest

from app.ai import client as ai_client
from app.core.config import settings
from app.models.recipe import Recipe
from app.schemas.ai import AiChatRequest, AiConversationState, AiRecommendRequest
from app.services import ai_service, chat_context


@pytest.fixture
def catalogue(session):
    for i in range(8):
        session.add(Recipe(name=f'清蒸蔬菜{i}', duration_minutes=12, category='素菜', tags=['蒸', '素菜']))
    session.commit()


def call(session, mode):
    if mode == 'chat':
        return ai_service.chat(session, None, AiChatRequest(message='推荐三道菜，少洗几个锅', cook_minutes=240))
    return ai_service.recommend_recipes(session, None, AiRecommendRequest(message='少洗几个锅', cook_minutes=240))


def ids(result):
    return [r.id for r in result.recipes] if hasattr(result, 'recipes') else [r.recipe.id for r in result.recommendations]


@pytest.mark.parametrize('mode', ['chat', 'compose'])
def test_ai_selects_from_a_real_pool_not_a_preselected_menu(session, catalogue, monkeypatch, mode):
    baseline = ids(call(session, mode))
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    chosen = []
    def network(messages, **kwargs):
        prompt = messages[-1]['content']
        candidates = list(map(int, re.findall(r'^(\d+) \|', prompt, re.M)))
        assert 3 < len(candidates) <= 24
        assert all(s in prompt for s in ('必须满足', '尽量满足', '少洗锅', '完整配料记录', '时长来源', '未确认已有的主料'))
        chosen.extend([i for i in candidates if i != baseline[0]][-3:])
        return ai_client.AiResult(ok=True, data={'answer': '按条件选好了。', 'picks': [{'id': i} for i in chosen]})
    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    result = call(session, mode)
    assert len(ids(result)) == 3
    assert all(i > 0 for i in ids(result))
    assert result.source == 'ai'
    assert any(t.agent == '结果校验' for t in result.trace)
    assert any(t.agent == '整餐复核' for t in result.trace)


@pytest.mark.parametrize('mode', ['chat', 'compose'])
def test_invalid_or_incomplete_model_selection_uses_whole_rule_menu(session, catalogue, monkeypatch, mode):
    baseline = ids(call(session, mode))
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    def network(messages, **kwargs):
        candidate = int(re.findall(r'^(\d+) \|', messages[-1]['content'], re.M)[-1])
        return ai_client.AiResult(ok=True, data={'answer': '不完整选择的说明不应显示', 'picks': [{'id': candidate}, {'id': candidate}, {'id': -999}]})
    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    result = call(session, mode)
    assert ids(result) == baseline
    assert result.source == 'algorithm'
    assert '不完整选择' not in result.answer


def test_soft_preferences_survive_followup_and_can_be_cancelled():
    state = chat_context.edits('少洗几个锅，不吃花生', AiConversationState(), ['花生'])
    assert state.selection_preferences == ['少洗锅']
    assert state.avoid_added == ['花生']
    state = chat_context.edits('换一批', state, ['花生'])
    assert state.selection_preferences == ['少洗锅']
    assert state.avoid_added == ['花生']
    state = chat_context.edits('取消少洗锅', state, ['花生'])
    assert not state.selection_preferences
    assert state.avoid_added == ['花生']


def test_compose_free_text_time_is_a_real_filter(session, catalogue):
    result = ai_service.recommend_recipes(session, None, AiRecommendRequest(message='只有五分钟，不吃花生', cook_minutes=240))
    assert not result.recommendations
