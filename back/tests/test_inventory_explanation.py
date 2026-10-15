"""Inventory facts must survive contradictory or fabricated model explanations."""
from types import SimpleNamespace

from app.ai.client import AiResult
from app.services import ai_service
from app.services.scoring_service import HardConstraints


def test_inventory_chat_replaces_model_claims(client, monkeypatch):
    token = client.post("/api/auth/login", json={
        "username": "demo", "password": "shishi2026",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/my-foods", headers=headers, json={
        "food_id": 1, "amount": 2, "unit": "节",
    })
    prompts = []
    monkeypatch.setattr(ai_service, "_route_semantic", lambda **kwargs: None)
    monkeypatch.setattr(ai_service.client, "is_configured", lambda: True)

    def fake_model(messages):
        prompts.append(messages[-1]["content"])
        return AiResult(ok=True, model="fake", data={
            "answer": "我看不到你的冰箱，但你有龙虾，保证低钠润肺。",
            "picks": [{"id": 1, "reason": "你有龙虾，保证低钠"}],
        })

    monkeypatch.setattr(ai_service.client, "complete_json", fake_model)
    response = client.post("/api/ai/chat", headers=headers, json={
        "message": "用我的食材做菜", "cook_minutes": 240, "low_sodium": False,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recipes"]
    assert "莲藕（2节）" in body["answer"]
    assert "逐菜库存核对" in prompts[-1]
    assert "实际登记的库存" in prompts[-1]
    assert "龙虾" not in body["answer"]
    assert "看不到" not in body["answer"]
    assert "数量足够" in body["answer"]
    assert all("龙虾" not in (r.get("description") or "") for r in body["recipes"])
    assert any(t["agent"] == "库存核对" for t in body["trace"])


def test_inventory_facts_all_dishes_exact_names_and_positive_quantity(monkeypatch):
    rows = [SimpleNamespace(food_id=1, custom_name=None, amount=1, unit="份"),
            SimpleNamespace(food_id=2, custom_name=None, amount=0, unit="份")]
    monkeypatch.setattr(ai_service.my_food_repository, "list_for_user", lambda *args: rows)
    monkeypatch.setattr(ai_service, "food_insights", lambda *args: {1: SimpleNamespace(name="鸡")})
    monkeypatch.setattr(ai_service, "dish_insights", lambda *args: {
        11: SimpleNamespace(ingredient_ids=[1], main_ingredients=["鸡", "土豆"]),
        12: SimpleNamespace(ingredient_ids=[3], main_ingredients=["鸡蛋", "番茄"]),
    })
    candidates = [SimpleNamespace(item_id=11, name="土豆鸡"),
                  SimpleNamespace(item_id=12, name="番茄炒蛋")]
    inventory, details = ai_service._inventory_facts(None, 7, candidates)
    assert inventory == "鸡（1份）"
    assert "土豆" in details[0]
    assert "鸡蛋、番茄" in details[1]
    assert "暂无可确认项" in details[1]
    assert ai_service._my_food_ids(None, 7) == [1]
    answer = ai_service._inventory_answer(None, 7, candidates, HardConstraints(low_sodium=True))
    assert "不能据此保证成品钠含量" in answer
