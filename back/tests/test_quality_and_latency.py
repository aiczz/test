import pytest

from app.ai import client as ai_client
from app.core.config import settings
from app.services.explanation_guard import checked_text, grounded_numbers_of
from app.utils.recipe_duration import duration_from_text


@pytest.mark.parametrize(('text', 'minutes'), [
    ('泡半个小时', 30), ('炖一个半小时', 90), ('煮一小时半', 90),
    ('炖1小时20分钟', 80), ('蒸十五分钟', 15), ('焖两小时', 120),
    ('20～30分钟', 30), ('腌制12小时', 720), ('烤十到十五分钟', 15),
    ('等待一刻钟', 15), ('焖0.5小时', 30), ('烧5分即可', 5),
    ('切成十分之一，十分鲜嫩', None), ('炒熟后出锅', None),
    ('炖一百二十分钟', 120), ('一百零五分钟', 105),
])
def test_explicit_duration_evidence(text, minutes):
    assert duration_from_text(text) == minutes


@pytest.mark.parametrize('text', [
    '保证20分钟做好整餐', '增强免疫力，能治好失眠',
    '你手头的食材都齐了', '原料200克，热量仅300千卡',
])
def test_unverified_model_claims_fall_back(text):
    result, rejected = checked_text(text, '按已核对条件推荐，请查看菜谱。')
    assert rejected
    assert result == '按已核对条件推荐，请查看菜谱。'


def test_low_sodium_claim_no_longer_nukes_answer():
    """食养词（低钠/补血/润肺）不再整段否决——守卫改成逐句修复后，
    模型按提示词引用候选数据的自然回答必须能原样通过。"""
    result, rejected = checked_text('适合2人，已经低钠', '')
    assert not rejected
    assert result == '适合2人，已经低钠'


def test_sentence_level_salvage_keeps_good_sentences():
    """硬承诺只丢那一句，其余保留——不再因为一句话毁掉整段回答。"""
    grounded = grounded_numbers_of('1 | 糖水马蹄 | 时长25分钟 | 钠12mg')
    result, rejected = checked_text(
        '这道汤能治好嗓子疼。糖水马蹄25分钟就好，生津润燥，喝着舒服。',
        '', grounded_numbers=grounded,
    )
    assert rejected
    assert '能治好' not in result
    assert '生津润燥' in result and '25分钟' in result


def test_invented_quantity_sentence_dropped_but_rest_kept():
    """编造的数字丢句；引用候选行里真实数字的句子放行。"""
    grounded = grounded_numbers_of('1 | 糖水马蹄 | 时长25分钟 | 钠12mg')
    result, rejected = checked_text(
        '糖水马蹄只用5分钟就能做好；马蹄生津润燥。', '',
        grounded_numbers=grounded,
    )
    assert rejected
    assert '5分钟' not in result
    assert '生津润燥' in result


def test_safe_nonquantified_explanation_kept():
    assert checked_text('可以先试试这份家常菜。', '') == ('可以先试试这份家常菜。', False)


def test_cache_keys_cover_inputs_provider_and_credentials(monkeypatch):
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only-one')
    monkeypatch.setattr(settings, 'ai_response_cache_seconds', 300)
    calls = []
    def network(messages, **kwargs):
        calls.append((messages, kwargs))
        return ai_client.AiResult(ok=True, data={'answer': '家常菜建议'}, model='fake')
    monkeypatch.setattr(ai_client, '_network_complete_json', network)
    messages = [{'role': 'user', 'content': '条件一'}]
    first = ai_client.complete_json(messages)
    first.data['answer'] = '外部修改'
    hit = ai_client.complete_json(messages)
    assert hit.cached and not hit.called
    assert hit.data['answer'] == '家常菜建议'
    assert len(calls) == 1
    ai_client.complete_json([{'role': 'user', 'content': '条件二'}])
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only-two')
    ai_client.complete_json(messages)
    assert len(calls) == 3


def test_preview_and_expired_budget_do_not_call_model(monkeypatch):
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    def forbidden(*args, **kwargs):
        raise AssertionError('preview/expired budget must not call model')
    monkeypatch.setattr(ai_client, '_network_complete_json', forbidden)
    with ai_client.request_options(enabled=False):
        assert not ai_client.complete_json([]).called
    with ai_client.request_options(budget=-1):
        assert not ai_client.complete_json([]).called


def test_algorithm_preview_endpoint_skips_model(client, monkeypatch):
    monkeypatch.setattr(settings, 'ai_enabled', True)
    monkeypatch.setattr(settings, 'ai_api_key', 'test-only')
    def forbidden(*args, **kwargs):
        raise AssertionError('preview must not call model')
    monkeypatch.setattr(ai_client, '_network_complete_json', forbidden)
    response = client.post('/api/ai/chat', json={
        'message': '今晚吃什么', 'cook_minutes': 240, 'use_ai': False,
    })
    assert response.status_code == 200, response.text
    assert response.json()['source'] == 'algorithm'
    assert response.json()['ai_available']
