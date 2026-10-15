import json
from pathlib import Path

import pytest

from app.ai import client as ai_client
from app.core.config import settings
from app.schemas.ai import AiChatRequest
from app.services import ai_service


@pytest.mark.parametrize('case', json.loads(
    (Path(__file__).resolve().parents[1] / 'evaluation/chat_intents.json').read_text(encoding='utf-8')
))
def test_curated_intent_cases(case):
    route = ai_service._route_smart(session=None, message=case['message'], payload=AiChatRequest(
        message=case['message'], last_intent=case.get('last_intent')))
    assert route.intent == case['intent']
    assert bool(route.clarification) == case.get('clarify', False)


def test_ambiguous_request_asks_without_calling_model(client, monkeypatch):
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    def forbidden(*args, **kwargs):
        pytest.fail('An ambiguous target should be clarified before model calls')
    monkeypatch.setattr(ai_client, '_network_complete_json', forbidden)
    body = client.post('/api/ai/chat', json={'message': '推荐一下'}).json()
    assert body['needs_clarification']
    assert '食材' in body['answer'] and '菜谱' in body['answer']
    assert not body['recipes'] and not body['foods']


def test_knowledge_question_does_not_change_conditions(client):
    body = client.post('/api/ai/chat', json={
        'message': '低钠是什么意思', 'conversation_state': {'low_sodium': False},
    }).json()
    assert body['conversation_state']['low_sodium'] is False


def test_explicit_request_uses_only_one_model_call(client, monkeypatch):
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    calls = []
    def network(messages, **kwargs):
        calls.append(messages)
        return ai_client.AiResult(ok=True, data={'answer': '按已核对条件选择。'}, model='fake')
    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    body = client.post('/api/ai/chat', json={'message': '今晚吃什么', 'cook_minutes': 240}).json()
    assert body['recipes']
    assert len(calls) == 1


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
