import json
from pathlib import Path

import pytest

from app.ai import client as ai_client
from app.core.config import settings
from app.schemas.ai import AiUnderstanding, AiUnderstandingSlots
from app.services import ai_service


CURATED_CASES = json.loads(
    (Path(__file__).resolve().parents[1] / 'evaluation/chat_intents.json').read_text(encoding='utf-8')
)


def understood(intent='meal_recommendation', operation='new', **slots):
    return AiUnderstanding(
        intent=intent, operation=operation, confidence=0.97,
        slots=AiUnderstandingSlots(**slots),
    )


def test_curated_semantic_evaluation_dataset_is_well_formed():
    """人工语料用于真实模型验收；离线套件不把预期答案伪造成模型输出。"""
    assert len(CURATED_CASES) >= 50
    assert {case['intent'] for case in CURATED_CASES} == {
        'meal_recommendation', 'recommend_foods', 'cook_with_my_foods', 'general', 'unknown',
    }
    assert sum(bool(case.get('clarify')) for case in CURATED_CASES) >= 3
    assert all(case['intent'] == 'unknown' for case in CURATED_CASES if case.get('clarify'))
    assert all(case['message'].strip() for case in CURATED_CASES)
    assert all(
        alternative['intent'] in {'meal_recommendation', 'recommend_foods', 'cook_with_my_foods', 'general', 'unknown'}
        for case in CURATED_CASES for alternative in case.get('alternatives', [])
    )


def test_ambiguous_request_uses_understanding_once_and_never_generates(client, monkeypatch):
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    calls = []

    def network(messages, **kwargs):
        calls.append(messages)
        return ai_client.AiResult(ok=True, data={
            'intent': 'unknown', 'operation': 'new', 'confidence': 0.98,
            'slots': {}, 'reset': [],
            'clarification': '你想让我推荐食材，还是推荐菜谱？',
            'why': '目标对象不明确',
        })

    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    body = client.post('/api/ai/chat', json={'message': '推荐一下'}).json()
    assert body['needs_clarification']
    assert '食材' in body['answer'] and '菜谱' in body['answer']
    assert not body['recipes'] and not body['foods']
    assert len(calls) == 1


def test_knowledge_question_does_not_change_conditions(client, stub_chat_understanding):
    stub_chat_understanding(understood(intent='general', operation='answer'))
    body = client.post('/api/ai/chat', json={
        'message': '低钠是什么意思', 'conversation_state': {'low_sodium': False},
    }).json()
    assert body['conversation_state']['low_sodium'] is False


def test_recipe_request_uses_one_understanding_and_at_most_one_generation_call(client, monkeypatch):
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    calls = []

    def network(messages, **kwargs):
        calls.append(messages)
        if '严格的结构化语义理解器' in messages[0]['content']:
            return ai_client.AiResult(ok=True, data={
                'intent': 'meal_recommendation', 'operation': 'new', 'confidence': 0.98,
                'slots': {'dish_count': 3}, 'reset': [], 'why': '明确的菜谱请求',
            }, model='fake-understanding')
        return ai_client.AiResult(ok=True, data={'answer': '按已核对条件选择。', 'picks': []}, model='fake-generation')

    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    body = client.post('/api/ai/chat', json={'message': '今晚吃什么', 'cook_minutes': 240}).json()
    assert body['recipes']
    assert len(calls) == 2
    assert sum('严格的结构化语义理解器' in call[0]['content'] for call in calls) == 1
    assert sum('严格的结构化语义理解器' not in call[0]['content'] for call in calls) == 1


def test_provider_failure_cools_down_then_recovers(monkeypatch):
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    monkeypatch.setattr(settings, 'ai_response_cache_seconds', 0)
    monkeypatch.setattr(settings, 'ai_failure_cooldown_seconds', 30)
    clock, calls = [100.0], []
    monkeypatch.setattr(ai_client.time, 'monotonic', lambda: clock[0])

    def network(messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            return ai_client.AiResult(ok=False, error='HTTP 503')
        return ai_client.AiResult(ok=True, data={'answer': '恢复'})

    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    assert not ai_client.complete_json([{'role': 'user', 'content': '问题一'}]).ok
    blocked = ai_client.complete_json([{'role': 'user', 'content': '不同的问题'}])
    assert not blocked.called and '冷却' in blocked.error
    assert len(calls) == 1
    clock[0] += 31
    assert ai_client.complete_json([{'role': 'user', 'content': '重新提问'}]).ok
    assert len(calls) == 2


def test_cooldown_is_scoped_to_provider_credentials(monkeypatch):
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only-one')
    calls = []

    def network(*args, **kwargs):
        calls.append(1)
        return ai_client.AiResult(ok=False, error='超时')

    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    ai_client.complete_json([])
    assert not ai_client.complete_json([]).called
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only-two')
    assert ai_client.complete_json([]).called
    assert len(calls) == 2
