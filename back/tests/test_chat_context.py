"""Regression cases for spoken constraints and round-trip conversation state."""
import pytest
from app.ai import client as ai_client
from app.schemas.ai import AiConversationState, AiUnderstanding, AiUnderstandingSlots
from app.services import ai_service, chat_context


def understood(operation='new', intent='meal_recommendation', clarification=None, **slots):
    return AiUnderstanding(
        intent=intent, operation=operation, confidence=0.97,
        slots=AiUnderstandingSlots(**slots), clarification=clarification,
    )


@pytest.mark.parametrize("text,minutes,people", [
    ("三个人今晚吃什么，15分钟以内", 15, 3),
    ("今天改成两个人，一刻钟搞定", 15, 2),
    ("晚餐半小时以内", 30, None),
    ("半个小时做晚饭", 30, None),
    ("十一个人晚餐，四十五分钟", 45, 11),
    ("晚餐一个半小时", 90, None),
    ("晚餐两小时", 120, None),
])
def test_spoken_numbers(text, minutes, people):
    state = chat_context.edits(text, AiConversationState(), [])
    assert state.cook_minutes == minutes
    assert state.people == people


@pytest.mark.parametrize("text,field,value", [
    ("晚餐3分钟", "cook_minutes", 3), ("晚餐300分钟", "cook_minutes", 300),
    ("21个人", "people", 21), ("0个人", "people", 0),
])
def test_unsupported_bounds_reject_the_model_contract(client, monkeypatch, text, field, value):
    monkeypatch.setattr(ai_service.client, 'is_configured', lambda: True)
    monkeypatch.setattr(ai_service.client, 'complete_json', lambda *args, **kwargs:
                        ai_client.AiResult(ok=True, data={
                            'intent': 'meal_recommendation', 'operation': 'new',
                            'confidence': 0.98, 'slots': {field: value},
                        }))
    body = client.post("/api/ai/chat", json={"message": text}).json()
    assert body["recipes"] == []
    assert body['needs_clarification']
    assert "不完整或不合法" in body["answer"]


def test_chat_passes_resolved_constraints_to_filter(client, monkeypatch, stub_chat_understanding):
    stub_chat_understanding(understood(
        people=2, cook_minutes=15, avoid_added=['花生'], excluded_categories=['汤羹'],
    ))
    calls = []
    def score(*args, **kwargs):
        calls.append(kwargs["constraints"])
        return []
    monkeypatch.setattr(ai_service.scoring_service, "score_dishes", score)
    body = client.post("/api/ai/chat", json={
        "message": "两个人晚餐，15分钟以内，不吃花生，不要汤", "cook_minutes": 45,
    }).json()
    assert body["effective_context"]["cook_minutes"] == 15
    assert body["effective_context"]["people"] == 2
    assert body["excluded_categories"] == ["汤羹"]
    assert len(calls) == 1  # No silent relaxation or repeat fallback.
    assert calls[0].cook_minutes == 15
    assert calls[0].require_known_time
    assert "花生" in calls[0].avoid
    assert calls[0].excluded_categories == ("汤羹",)


def test_three_turns_preserve_then_revoke_conditions(client, stub_chat_understanding):
    stub_chat_understanding({
        '两个人晚餐，十五分钟，不吃花生，不喝汤': understood(
            people=2, cook_minutes=15, avoid_added=['花生'], excluded_categories=['汤羹'],
        ),
        '再换一组，其他条件不变': understood(operation='repeat'),
        '取消不喝汤，取消花生忌口，时间放宽到半小时，改成三个人，其他不变': understood(
            operation='refine', people=3, cook_minutes=30, avoid_removed=['花生'],
        ).model_copy(update={'reset': ['excluded_categories']}),
        '再换一组': understood(operation='repeat'),
    })
    first = client.post("/api/ai/chat", json={
        "message": "两个人晚餐，十五分钟，不吃花生，不喝汤", "avoid": ["海鲜"],
    }).json()
    second = client.post("/api/ai/chat", json={
        "message": "再换一组，其他条件不变", "avoid": ["海鲜"],
        "conversation_state": first["conversation_state"], "last_intent": first["intent"],
        "recent_recipe_ids": [r["id"] for r in first["recipes"]],
    }).json()
    assert second["effective_context"] == first["effective_context"]
    assert second["excluded_categories"] == ["汤羹"]
    third = client.post("/api/ai/chat", json={
        "message": "取消不喝汤，取消花生忌口，时间放宽到半小时，改成三个人，其他不变",
        "avoid": ["海鲜", "花生"], "conversation_state": second["conversation_state"],
        "last_intent": second["intent"],
    }).json()
    assert third["effective_context"]["cook_minutes"] == 30
    assert third["effective_context"]["people"] == 3
    assert third["effective_context"]["avoid"] == ["海鲜"]
    assert third["excluded_categories"] == []
    fourth = client.post("/api/ai/chat", json={
        "message": "再换一组", "avoid": ["海鲜", "花生"],
        "conversation_state": third["conversation_state"], "last_intent": third["intent"],
    }).json()
    assert fourth["effective_context"]["avoid"] == ["海鲜"]


def test_negation_does_not_exclude_positive_foods():
    assert ai_service._declared_avoid("不吃花生，但是家里有鸡蛋", ["花生", "鸡蛋"]) == ["花生"]


def test_low_sodium_and_preference_can_be_revoked():
    state = chat_context.edits("少盐，清淡", AiConversationState(), [])
    assert state.low_sodium is True
    assert state.preferences == ["清淡"]
    state = chat_context.edits("取消低钠，取消清淡", state, [])
    assert state.low_sodium is False
    assert state.preferences == []


def test_actual_recommendations_respect_known_time(client, stub_chat_understanding):
    stub_chat_understanding(understood(cook_minutes=15))
    body = client.post("/api/ai/chat", json={"message": "晚餐15分钟以内"}).json()
    for recipe in body["recipes"]:
        assert recipe["duration_minutes"] <= 15
        assert not recipe.get("duration_estimated", False)


def test_real_route_source_is_returned(client, stub_chat_understanding):
    stub_chat_understanding(understood())
    body = client.post("/api/ai/chat", json={"message": "今晚吃什么"}).json()
    assert body["intent_source"] == "ai"


def test_no_soup_category_is_filtered_and_stays_filtered(client, stub_chat_understanding):
    stub_chat_understanding({
        '今晚不喝汤': understood(excluded_categories=['汤羹']),
        '再换一组，其他条件不变': understood(operation='repeat'),
    })
    first = client.post("/api/ai/chat", json={
        "message": "今晚不喝汤", "cook_minutes": 240,
    }).json()
    assert first["recipes"]
    assert all("汤" not in r["name"] for r in first["recipes"])
    second = client.post("/api/ai/chat", json={
        "message": "再换一组，其他条件不变", "cook_minutes": 240,
        "last_intent": first["intent"], "conversation_state": first["conversation_state"],
    }).json()
    assert second["excluded_categories"] == ["汤羹"]
    assert all("汤" not in r["name"] for r in second["recipes"])


def test_empty_profile_avoid_does_not_restore_cancelled_database_avoid(session, stub_chat_understanding):
    stub_chat_understanding(understood(operation='refine', avoid_removed=['花生']))
    from app.schemas.ai import AiChatRequest
    # Cancellation is resolved to an explicit empty list, which must stay empty.
    from app.repositories import user_repository
    from app.models.user import User
    user = User(username="context_test", password_hash="test")
    session.add(user)
    session.commit()
    pref = user_repository.ensure_preference(session, user.id)
    pref.avoid_foods = ["花生"]
    session.add(pref)
    session.commit()
    result = ai_service.chat(session, user.id, AiChatRequest(message="取消花生忌口"))
    assert result.effective_context.avoid == []
    assert pref.avoid_foods == ["花生"]  # Conversation edits do not rewrite the profile.


def test_pending_answer_resumes_original_recommendation_end_to_end(client, stub_chat_understanding):
    stub_chat_understanding({
        '帮我安排两个人的一餐': understood(people=2, clarification='这一餐想要几道？'),
        '三道': understood(operation='answer', dish_count=3),
    })
    first = client.post('/api/ai/chat', json={
        'message': '帮我安排两个人的一餐', 'cook_minutes': 240,
    }).json()
    assert first['needs_clarification']
    assert not first['recipes']
    assert first['conversation_state']['pending']['question'] == '这一餐想要几道？'
    assert first['conversation_state']['pending']['slots']['people'] == 2

    result = client.post('/api/ai/chat', json={
        'message': '三道', 'cook_minutes': 240,
        'conversation_state': first['conversation_state'], 'last_intent': first['intent'],
    }).json()
    assert not result['needs_clarification']
    assert len(result['recipes']) == 3
    assert result['requested_count'] == result['returned_count'] == 3
    assert result['effective_context']['people'] == 2
    assert result['conversation_state']['recommendation_count'] == 3
    assert result['conversation_state']['pending'] is None


def test_structured_reducer_preserves_unmentioned_conditions():
    prior = AiConversationState(
        people=4, recommendation_count=5, required_foods=['鱼'],
        avoid_added=['花生'], cook_minutes=30,
    )
    result = chat_context.apply_understanding(prior, AiUnderstanding(
        intent='meal_recommendation', operation='refine', confidence=0.96,
        slots=AiUnderstandingSlots(dish_count=2),
    ))
    assert result.recommendation_count == 2
    assert result.people == 4
    assert result.cook_minutes == 30
    assert result.required_foods == ['鱼']
    assert result.avoid_added == ['花生']


def test_structured_reducer_separates_add_new_and_detail():
    prior = AiConversationState(recommendation_count=5, avoid_added=['花生'])
    added = chat_context.apply_understanding(prior, AiUnderstanding(
        intent='meal_recommendation', operation='add', confidence=0.98,
        slots=AiUnderstandingSlots(dish_count=1),
    ))
    assert added.recommendation_count == 5
    assert added.incremental_count == 1

    fresh = chat_context.apply_understanding(added, AiUnderstanding(
        intent='meal_recommendation', operation='new', confidence=0.95,
    ))
    assert fresh.recommendation_count is None
    assert fresh.incremental_count is None
    assert fresh.avoid_added == ['花生']

    detail = chat_context.apply_understanding(added, AiUnderstanding(
        intent='general', operation='detail', confidence=0.99,
        slots=AiUnderstandingSlots(dish_count=1), detail_kind='steps',
    ))
    assert detail.recommendation_count == 5
    assert detail.incremental_count is None


def test_structured_reducer_reset_and_pending_are_explicit():
    prior = AiConversationState(required_foods=['鱼'], avoid_added=['花生'])
    result = chat_context.apply_understanding(prior, AiUnderstanding(
        intent='meal_recommendation', operation='refine', confidence=0.9,
        slots=AiUnderstandingSlots(avoid_removed=['花生']),
        reset=['required_foods'], clarification='还想要几道？',
    ))
    assert result.required_foods is None
    assert result.avoid_added == []
    assert result.avoid_removed == ['花生']
    assert result.pending is not None
    assert result.pending.question == '还想要几道？'
