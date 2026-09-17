"""业务接口测试：现有食材 / 收藏 / 菜单 / 购物清单 / AI / 个人偏好。

覆盖说明书 §13 / §14 / §15 / §16 / §17 / §19 / §20，
以及两个安全重点：**跨用户越权** 和 **写接口幂等**。
"""

from app.data.seed import DEMO_PASSWORD, DEMO_USERNAME


def _auth(client, username=DEMO_USERNAME, password=DEMO_PASSWORD) -> dict:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _register(client, username: str) -> dict:
    resp = client.post(
        "/api/auth/register", json={"username": username, "password": "pw123456"}
    )
    assert resp.status_code == 201, resp.text
    return _auth(client, username, "pw123456")


# ---------------------------------------------------------------- §13 我的食材


def test_my_foods_requires_login(client):
    assert client.get("/api/my-foods").status_code == 401


def test_my_foods_crud(client):
    header = _auth(client)
    assert client.get("/api/my-foods", headers=header).json() == []

    resp = client.post(
        "/api/my-foods",
        json={"food_id": 1, "amount": 2, "unit": "节"},
        headers=header,
    )
    assert resp.status_code == 201, resp.text
    item = resp.json()
    assert item["name"] == "莲藕"
    assert item["amount"] == 2

    # 同一种食材重复添加应当累加，而不是多出一行
    again = client.post(
        "/api/my-foods",
        json={"food_id": 1, "amount": 3, "unit": "节"},
        headers=header,
    )
    assert again.json()["amount"] == 5
    assert len(client.get("/api/my-foods", headers=header).json()) == 1

    updated = client.put(
        f"/api/my-foods/{item['id']}", json={"amount": 9}, headers=header
    )
    assert updated.json()["amount"] == 9

    assert (
        client.delete(f"/api/my-foods/{item['id']}", headers=header).status_code
        == 204
    )
    assert client.get("/api/my-foods", headers=header).json() == []


def test_my_foods_accepts_custom_name(client):
    header = _auth(client)
    resp = client.post(
        "/api/my-foods",
        json={"custom_name": "外婆做的酱", "amount": 1, "unit": "罐"},
        headers=header,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "外婆做的酱"
    assert resp.json()["food_id"] is None


def test_my_foods_needs_food_id_or_name(client):
    header = _auth(client)
    resp = client.post("/api/my-foods", json={"amount": 1}, headers=header)
    assert resp.status_code == 422


def test_my_foods_cross_user_isolation(client):
    """★ 越权测试：别人不能看/改/删我的库存。"""
    mine = _auth(client)
    item = client.post(
        "/api/my-foods", json={"food_id": 1, "amount": 1}, headers=mine
    ).json()

    other = _register(client, "intruder")
    assert client.get("/api/my-foods", headers=other).json() == []
    # 别人的记录返回 404（而不是 403）—— 不泄露"这条记录存在"
    assert (
        client.put(
            f"/api/my-foods/{item['id']}", json={"amount": 99}, headers=other
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/my-foods/{item['id']}", headers=other).status_code
        == 404
    )
    # 原数据没被动过
    assert client.get("/api/my-foods", headers=mine).json()[0]["amount"] == 1


# ---------------------------------------------------------------- §14 按食材推荐


def test_recommend_by_foods(client):
    header = _auth(client)
    # 莲藕(food_id=1) + 鸡蛋(food_id=6)
    resp = client.post(
        "/api/recipes/recommend-by-foods",
        json={"food_ids": [1, 6], "people": 3},
    )
    assert resp.status_code == 200, resp.text
    names = [r["name"] for r in resp.json()["recommended_recipes"]]
    assert names, "至少应该推荐出菜谱"
    assert "莲藕排骨汤" in names


def test_recommend_by_foods_uses_my_inventory(client):
    """不传 food_ids 时应当自动用当前用户的库存。"""
    header = _auth(client)
    client.post("/api/my-foods", json={"food_id": 1}, headers=header)

    body = client.post(
        "/api/recipes/recommend-by-foods", json={"people": 3}, headers=header
    ).json()
    assert any(r["name"] == "莲藕排骨汤" for r in body["recommended_recipes"])
    # 做莲藕排骨汤还缺排骨之类的
    assert body["missing_ingredients"]


# ---------------------------------------------------------------- §15 收藏


def test_favorites_flow(client):
    header = _auth(client)
    assert client.get("/api/favorites", headers=header).json()["total"] == 0

    assert (
        client.post("/api/favorites/1", headers=header).json()["is_favorite"]
        is True
    )
    # 重复收藏不产生重复记录
    client.post("/api/favorites/1", headers=header)
    client.post("/api/favorites/1", headers=header)
    assert client.get("/api/favorites", headers=header).json()["total"] == 1

    # 菜谱详情里 is_favorite 跟着变
    assert client.get("/api/recipes/1", headers=header).json()["is_favorite"] is True

    # 取消收藏，重复取消也不报错
    assert (
        client.delete("/api/favorites/1", headers=header).json()["is_favorite"]
        is False
    )
    assert client.delete("/api/favorites/1", headers=header).status_code == 200
    assert client.get("/api/favorites", headers=header).json()["total"] == 0


def test_favorite_unknown_recipe_is_404(client):
    header = _auth(client)
    assert client.post("/api/favorites/9999", headers=header).status_code == 404


def test_favorites_are_per_user(client):
    mine = _auth(client)
    client.post("/api/favorites/1", headers=mine)
    other = _register(client, "collector")
    assert client.get("/api/favorites", headers=other).json()["total"] == 0


# ---------------------------------------------------------------- §16/§17 菜单


def test_menu_today_requires_login(client):
    assert client.get("/api/menu/today").status_code == 401


def test_menu_today_generate_then_get(client):
    header = _auth(client)
    assert client.get("/api/menu/today", headers=header).status_code == 404

    resp = client.post(
        "/api/menu/today/generate",
        json={
            "people": 3,
            "meal_types": ["breakfast", "lunch", "dinner"],
            "preferences": ["家常", "清淡"],
        },
        headers=header,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "今日菜单"
    assert body["people"] == 3
    for meal in ("breakfast", "lunch", "dinner"):
        assert body["meals"][meal], f"{meal} 不该是空的"

    # ★ 早餐必须是快手的
    assert all(
        r["duration_minutes"] <= 15 for r in body["meals"]["breakfast"]
    )

    again = client.get("/api/menu/today", headers=header)
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]


def test_menu_plan_multi_day(client):
    header = _auth(client)
    resp = client.post(
        "/api/menu/plan",
        json={"days": 3, "people": 4, "preferences": ["家常"]},
        headers=header,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["days"]) == 3
    assert body["days"][0]["day_index"] == 1
    assert body["days"][0]["label"] == "周一"
    assert body["days"][0]["recipes"]
    assert body["people"] == 4


def test_menu_is_per_user(client):
    mine = _auth(client)
    client.post("/api/menu/today/generate", json={"people": 3}, headers=mine)
    other = _register(client, "hungry")
    assert client.get("/api/menu/today", headers=other).status_code == 404


# ---------------------------------------------------------------- §19 购物清单


def test_shopping_generate_and_group(client):
    header = _auth(client)
    plan = client.post(
        "/api/menu/today/generate", json={"people": 3}, headers=header
    ).json()

    resp = client.post(
        "/api/shopping-list/generate",
        json={"menu_plan_id": plan["id"]},
        headers=header,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_items"] > 0
    assert body["categories"]
    # 每条都归在自己那一组下
    for group in body["categories"]:
        for item in group["items"]:
            assert item["category"] == group["category"]


def test_shopping_merges_same_ingredient(client):
    """★ 说明书 §19 的核心步骤：合并相同食材。"""
    header = _auth(client)
    plan = client.post(
        "/api/menu/today/generate", json={"people": 3}, headers=header
    ).json()
    body = client.post(
        "/api/shopping-list/generate",
        json={"menu_plan_id": plan["id"]},
        headers=header,
    ).json()

    names = [i["name"] for g in body["categories"] for i in g["items"]]
    # 名字重复就说明没合并
    assert len(names) == len(set(names))


def test_shopping_item_check_persists(client):
    header = _auth(client)
    plan = client.post(
        "/api/menu/today/generate", json={"people": 3}, headers=header
    ).json()
    body = client.post(
        "/api/shopping-list/generate",
        json={"menu_plan_id": plan["id"]},
        headers=header,
    ).json()
    item_id = body["categories"][0]["items"][0]["id"]

    resp = client.put(
        f"/api/shopping-list/items/{item_id}", json={"checked": True}, headers=header
    )
    assert resp.status_code == 200
    assert resp.json()["checked"] is True

    latest = client.get("/api/shopping-list", headers=header).json()
    flat = [i for g in latest["categories"] for i in g["items"]]
    assert any(i["id"] == item_id and i["checked"] for i in flat)


def test_shopping_cannot_use_others_menu(client):
    """★ 越权：不能拿别人的菜单生成购物清单。"""
    mine = _auth(client)
    plan = client.post(
        "/api/menu/today/generate", json={"people": 3}, headers=mine
    ).json()

    other = _register(client, "thief")
    resp = client.post(
        "/api/shopping-list/generate",
        json={"menu_plan_id": plan["id"]},
        headers=other,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------- §20 AI 助手


def test_ai_chat_meal_recommendation(client):
    resp = client.post("/api/ai/chat", json={"message": "三个人今晚吃什么？"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["intent"] == "meal_recommendation"
    assert len(body["recipes"]) == 3
    assert "season_search" in body["tools_used"]
    assert body["menu"] is not None
    assert "3" in body["menu"]["summary"]


def test_ai_chat_parses_chinese_number(client):
    body = client.post("/api/ai/chat", json={"message": "两个人晚饭推荐"}).json()
    assert "2" in body["menu"]["summary"]


def test_ai_chat_without_login_prompts_login(client):
    body = client.post("/api/ai/chat", json={"message": "用我的食材做菜"}).json()
    assert body["intent"] == "cook_with_my_foods"
    assert "登录" in body["answer"]


def test_ai_chat_with_my_inventory(client):
    header = _auth(client)
    client.post("/api/my-foods", json={"food_id": 1}, headers=header)  # 莲藕
    body = client.post(
        "/api/ai/chat", json={"message": "用我的食材做什么"}, headers=header
    ).json()
    assert body["intent"] == "cook_with_my_foods"
    assert any(r["name"] == "莲藕排骨汤" for r in body["recipes"])


def test_ai_chat_general(client):
    body = client.post("/api/ai/chat", json={"message": "你好"}).json()
    assert body["intent"] == "general"
    assert body["recipes"] == []


# ---------------------------------------------------------------- 个人偏好


def test_profile_requires_login(client):
    assert client.get("/api/profile").status_code == 401


def test_profile_get_and_partial_update(client):
    header = _auth(client)
    body = client.get("/api/profile", headers=header).json()
    assert body["family_size"] == 3
    assert body["avoid_foods"] == ["辛辣"]  # 种子数据
    assert body["taste"] == "清淡"

    resp = client.put(
        "/api/profile",
        json={"family_size": 5, "avoid_foods": ["辛辣", "海鲜"]},
        headers=header,
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["family_size"] == 5
    assert updated["avoid_foods"] == ["辛辣", "海鲜"]
    # 没传的字段保持原值，不能被 PUT 清空
    assert updated["taste"] == "清淡"
