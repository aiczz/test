import pytest

from app.services import ai_service
from app.schemas.ai import AiChatRequest


@pytest.mark.parametrize("message", [
    "为什么炒饭会粘锅", "莲藕怎么保存", "低钠是什么意思",
    "给我推荐一本小说", "帮我安排明天的会议", "账号怎么改成手机号",
])
def test_questions_do_not_return_recipes(client, message):
    response = client.post("/api/ai/chat", json={
        "message": message, "use_ai": False,
        "last_intent": "meal_recommendation",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "general"
    assert body["recipes"] == []
    assert body["foods"] == []


def test_question_bypasses_semantic_recommendation(monkeypatch):
    def unexpected(**kwargs):
        pytest.fail("An explicit question should not be reclassified as a recommendation")
    monkeypatch.setattr(ai_service, "_route_semantic", unexpected)
    assert ai_service._route_smart(session=None, message="为什么炒饭会粘锅").intent == "general"


def test_follow_up_after_general_does_not_resume_old_recipes():
    payload = AiChatRequest(message="还有吗", last_intent="general")
    assert ai_service._route(session=None, message=payload.message, payload=payload).intent == "general"


@pytest.mark.parametrize("message", ["换一批呢", "再来三道菜", "推荐几道清淡的菜", "今晚吃什么"])
def test_recipe_requests_still_recommend(message):
    assert ai_service._route(session=None, message=message).intent == "meal_recommendation"


@pytest.mark.parametrize("message", [
    "推荐一些食材", "推荐一下食材", "推荐几种当季食材", "给我推荐适合秋天的食材",
    "推荐一些蔬菜", "帮我挑几种水果", "为晚餐推荐一些食材", "从我的食材中挑选几种食材",
])
@pytest.mark.parametrize("use_ai", [False, True])
def test_explicit_food_requests_never_return_recipes(client, monkeypatch, message, use_ai):
    def unexpected(**kwargs):
        pytest.fail("Explicit ingredient request must not be overridden by the model")
    monkeypatch.setattr(ai_service, "_route_semantic", unexpected)
    body = client.post("/api/ai/chat", json={
        "message": message, "use_ai": use_ai, "last_intent": "meal_recommendation",
    }).json()
    assert body["intent"] == "recommend_foods"
    assert body["foods"]
    assert body["recipes"] == []


@pytest.mark.parametrize("message", ["用我的食材做菜", "用食材推荐几道菜", "推荐食材，再推荐几道菜"])
def test_recipe_target_is_not_confused_with_ingredients(message):
    assert ai_service._route(session=None, message=message).intent in {
        "cook_with_my_foods", "meal_recommendation",
    }


def test_general_question_reports_upstream_busy(client, monkeypatch):
    from app.ai.client import AiResult
    monkeypatch.setattr(ai_service.client, "is_configured", lambda: True)
    monkeypatch.setattr(ai_service.client, "complete_json", lambda *args, **kwargs:
                        AiResult(ok=False, error="HTTP 503", elapsed_ms=12))
    body = client.post("/api/ai/chat", json={"message": "低钠是什么意思"}).json()
    assert "繁忙" in body["answer"]
    assert "繁忙" in body["trace"][-1]["summary"]
    assert body["recipes"] == []
