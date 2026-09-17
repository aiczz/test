"""首页 / 食材 / 菜谱接口测试（说明书 §9 / §10 / §11）。"""


# ---------------------------------------------------------------- 首页


def test_home_aggregate(client):
    resp = client.get("/api/home?region=杭州&month=9")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["season"] == {"name": "秋季", "month": 9, "region": "杭州"}
    assert body["hero"]["title"] == "今日推荐"
    assert len(body["recommended_foods"]) > 0
    assert len(body["recommended_menus"]) > 0
    assert body["ai_tip"]


def test_home_does_not_return_price(client):
    """★ 说明书 §9 明确要求：首页不返回价格字段。"""
    resp = client.get("/api/home?month=9")
    assert "price" not in resp.text.lower()
    assert "价格" not in resp.text
    assert "¥" not in resp.text


def test_home_foods_are_sorted_by_season_score(client):
    """9 月的时令食材应按应季程度降序，莲藕（95 分）排第一。"""
    body = client.get("/api/home?month=9").json()
    names = [f["name"] for f in body["recommended_foods"]]
    assert "莲藕" in names
    assert names[0] == "莲藕"


def test_home_season_name_by_month(client):
    assert client.get("/api/home?month=1").json()["season"]["name"] == "冬季"
    assert client.get("/api/home?month=4").json()["season"]["name"] == "春季"
    assert client.get("/api/home?month=7").json()["season"]["name"] == "夏季"
    assert client.get("/api/home?month=10").json()["season"]["name"] == "秋季"


# ---------------------------------------------------------------- 食材


def test_foods_list_pagination(client):
    body = client.get("/api/foods?page=1&page_size=2").json()
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
    assert body["total"] == 6


def test_foods_second_page(client):
    body = client.get("/api/foods?page=2&page_size=2").json()
    assert len(body["items"]) == 2
    assert body["items"][0]["name"] != "莲藕"


def test_foods_category_filter(client):
    body = client.get("/api/foods?category=meat_egg").json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "鸡蛋"


def test_foods_keyword_filter(client):
    body = client.get("/api/foods?keyword=莲").json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "莲藕"


def test_seasonal_route_not_swallowed_by_id_route(client):
    """★ 回归测试：/foods/seasonal 不能被 /foods/{food_id} 当成 id 吃掉。

    路由声明顺序写反的话，这里会返回 422（"seasonal" 不是整数）。
    """
    resp = client.get("/api/foods/seasonal?month=9&limit=10")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert isinstance(payload, list)
    assert "莲藕" in [f["name"] for f in payload]


def test_food_detail(client):
    resp = client.get("/api/foods/1")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["name"] == "莲藕"
    assert body["season"]["name"] == "秋季"
    assert body["season"]["score"] == 95
    assert body["tags"] == ["润燥养胃", "秋季适宜"]
    assert body["features"]["texture"] == "脆嫩"
    # 莲藕能做莲藕排骨汤 —— 食材详情的 recommended_recipes
    assert any(r["name"] == "莲藕排骨汤" for r in body["recommended_recipes"])


def test_food_detail_404(client):
    assert client.get("/api/foods/9999").status_code == 404


# ---------------------------------------------------------------- 菜谱


def test_recipes_list(client):
    body = client.get("/api/recipes").json()
    assert body["total"] == 4


def test_recipes_max_duration_filter(client):
    """★ 前端首页「按你的条件能做」依赖这个参数。

    默认 45 分钟可用时间下，60 分钟的莲藕排骨汤必须被筛掉 ——
    这正是首页上「已筛掉 1 道」那句话的后端依据。
    """
    body = client.get("/api/recipes?max_duration=45").json()
    names = [r["name"] for r in body["items"]]
    assert "莲藕排骨汤" not in names
    assert "番茄炒蛋" in names
    assert body["total"] == 3


def test_recipes_difficulty_filter(client):
    body = client.get("/api/recipes?difficulty=中等").json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "香菇炖鸡"


def test_recipes_search_by_recipe_name(client):
    body = client.get("/api/recipes/search?q=排骨").json()
    assert any(r["name"] == "莲藕排骨汤" for r in body["items"])


def test_recipes_search_by_ingredient_name(client):
    """说明书 §11.2：既要能搜菜名，也要能搜食材。

    "鸡腿肉" 只出现在配料里，菜名里没有。
    """
    body = client.get("/api/recipes/search?q=鸡腿肉").json()
    names = [r["name"] for r in body["items"]]
    assert names == ["香菇炖鸡"]


def test_recipe_detail(client):
    resp = client.get("/api/recipes/1")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["name"] == "莲藕排骨汤"
    assert body["duration_minutes"] == 60
    assert body["servings"] == "3人份"
    assert body["difficulty"] == "简单"
    assert body["tags"] == ["秋日暖汤", "家常", "营养"]
    assert len(body["ingredients"]) == 6
    assert len(body["steps"]) == 4
    assert body["tips"]
    # 未登录时一律 false，而不是报错（菜谱详情是公开接口）
    assert body["is_favorite"] is False


def test_recipe_detail_amount_formatting(client):
    """500.0 要显示成 "500"，"适量" 这类没有数值的保持为空。"""
    body = client.get("/api/recipes/1").json()
    amounts = {i["name"]: i["amount"] for i in body["ingredients"]}
    assert amounts["排骨"] == "500"
    assert amounts["莲藕"] == "1"
    assert amounts["盐"] is None


def test_recipe_detail_404(client):
    assert client.get("/api/recipes/9999").status_code == 404
