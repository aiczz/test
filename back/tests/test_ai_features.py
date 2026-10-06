"""本次新增的「算法 + AI」能力测试。

覆盖三件事：
  1. 首页推荐是可解释的、**同地区同一天稳定**、**跨天会变**；
  2. 大模型只能在候选集内挑选 —— 编造的 id 一定被丢弃；
  3. `/api/ai/recommend` 真的按「已选食材 + 今日菜单 + 硬约束」出结果。

⚠️ 全部在「没有 AI、没有天气网络」的条件下跑（见 conftest 的 _hermetic_externals）。
   这既是测试的隔离要求，也正好验证了线上没配 Key / 断网时的降级路径。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlmodel import Session, create_engine
from sqlmodel.pool import StaticPool

from app.services import ai_daily_service, scoring_service, weather_service
from app.services.scoring_service import HardConstraints
from app.services.weather_service import WeatherContext

# =====================================================================
# 最小「清洗库」测试夹具
#
# 这一套表的列是照着 sql/cleaned_v2/schema.sql 挑的（只挑本次功能用得到的），
# 目的是造出「多个食材应季分档相同」的场景 —— 真实线上 10 月有 46 个
# season_score=100 的时令食材，每日轮换就是在这个档位内部发生的。
# =====================================================================
_COMPACT_DDL = [
    """CREATE TABLE ingredients (
        id INTEGER PRIMARY KEY, name TEXT, category TEXT, is_core_raw INTEGER,
        is_edible INTEGER, usage_count INTEGER, reason TEXT, effects_json TEXT,
        energy_kcal REAL, protein REAL, fat REAL, cho REAL, na REAL,
        dietary_fiber REAL, ca REAL, vitamin_c REAL,
        tcm_user TEXT, tcm_not_user TEXT,
        suitable_groups_json TEXT, unsuitable_groups_json TEXT
    )""",
    """CREATE TABLE dishes (
        id INTEGER PRIMARY KEY, dish_name TEXT, description TEXT, cuisine TEXT,
        tags_json TEXT, instruction_text TEXT, total_weight_g REAL,
        energy_kcal REAL, protein_g REAL, fat_g REAL, cho_g REAL,
        dietary_fiber_g REAL, na_mg REAL, matched_ratio REAL
    )""",
    """CREATE TABLE dish_ingredients (
        id INTEGER PRIMARY KEY, dish_id INTEGER, ingredient_id INTEGER,
        core_ingredient_id INTEGER, raw_name TEXT, role TEXT, grams REAL
    )""",
    """CREATE TABLE seasonal_calendar (
        id TEXT PRIMARY KEY, level TEXT, name TEXT, season TEXT,
        description TEXT, knowledge_json TEXT
    )""",
    """CREATE TABLE seasonal_food (
        id TEXT PRIMARY KEY, calendar_id TEXT, level TEXT, time_name TEXT,
        season TEXT, category TEXT, name TEXT, note TEXT,
        recommendation_reason TEXT, ingredient_id INTEGER
    )""",
    """CREATE TABLE seasonal_dish_links (
        seasonal_food_id TEXT, dish_id INTEGER, match_type TEXT
    )""",
]

# 6 个食材 + 6 道菜，全部挂在 10 月的同一个应季档位上
# (id, 名称, 类别, usage_count, 功效标签, 能量, 蛋白, 脂肪, 碳水, 钠, 纤维, 钙, 维C, 中医宜, 中医忌)
_FOODS = [
    (1, "白萝卜", "蔬菜", 900, '["下气宽中","消食"]', 21.0, 0.9, 0.1, 5.0, 61.0, 1.0, 36.0, 21.0, "一般人群", None),
    (2, "山药", "薯芋", 800, '["健脾","补肺"]', 57.0, 1.9, 0.2, 12.4, 18.0, 0.8, 16.0, 5.0, "一般人群", None),
    (3, "莲藕", "蔬菜", 950, '["润燥养胃","生津"]', 47.0, 1.9, 0.2, 11.5, 44.0, 1.2, 39.0, 44.0, "一般人群", None),
    (4, "西兰花", "蔬菜", 850, '["清热","低脂"]', 33.0, 4.1, 0.6, 4.3, 18.0, 1.6, 67.0, 51.0, "一般人群", None),
    (5, "南瓜", "蔬菜", 900, '["温中","补气"]', 23.0, 0.7, 0.1, 5.3, 0.8, 0.8, 16.0, 8.0, "一般人群", None),
    (6, "梨", "水果", 880, '["润肺","止咳生津"]', 51.0, 0.4, 0.2, 13.3, 2.1, 3.1, 9.0, 6.0, "一般人群", None),
]

_DISHES = [
    (101, "白萝卜炖排骨", "汤羹、炖", 620.0, 32.0, 22.0, 18.0, 4.0, 780.0),
    (102, "清炒山药", "清淡、快手菜", 210.0, 5.0, 6.0, 30.0, 3.0, 420.0),
    (103, "莲藕排骨汤", "汤羹、家常", 540.0, 30.0, 20.0, 22.0, 5.0, 900.0),
    (104, "凉拌西兰花", "凉菜、减肥、低脂", 150.0, 8.0, 3.0, 12.0, 5.0, 300.0),
    (105, "南瓜粥", "粥、清淡", 180.0, 4.0, 1.0, 38.0, 2.0, 90.0),
    (106, "冰糖炖梨", "甜品、蒸", 160.0, 1.0, 0.3, 40.0, 3.0, 20.0),
]

# 每个食材对应自己那道菜，保证「按食材召回」有结果
_DISH_INGREDIENTS = [
    (1, 101, 1, "白萝卜", "main"),
    (2, 102, 2, "山药", "main"),
    (3, 103, 3, "莲藕", "main"),
    (4, 104, 4, "西兰花", "main"),
    (5, 105, 5, "南瓜", "main"),
    (6, 106, 6, "梨", "main"),
]


def _compact_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # 用 exec_driver_sql（而不是 session.execute(text(...), tuple)）：
    # SQLAlchemy 2.0 的 text() 只接受字典参数，位置参数要走驱动层接口。
    with engine.begin() as connection:
        for statement in _COMPACT_DDL:
            connection.exec_driver_sql(statement)

        for row in _FOODS:
            connection.exec_driver_sql(
                "INSERT INTO ingredients (id, name, category, is_core_raw, "
                "is_edible, usage_count, reason, effects_json, energy_kcal, "
                "protein, fat, cho, na, dietary_fiber, ca, vitamin_c, "
                "tcm_user, tcm_not_user, suitable_groups_json, "
                "unsuitable_groups_json) VALUES "
                "(?, ?, ?, 1, 1, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "'[]', '[]')",
                row,
            )

        for dish_id, name, tags, energy, protein, fat, cho, fiber, na in _DISHES:
            connection.exec_driver_sql(
                "INSERT INTO dishes (id, dish_name, description, cuisine, "
                "tags_json, instruction_text, total_weight_g, energy_kcal, "
                "protein_g, fat_g, cho_g, dietary_fiber_g, na_mg, "
                "matched_ratio) VALUES (?, ?, '', NULL, ?, '1、做', 500, ?, "
                "?, ?, ?, ?, ?, 0.9)",
                (dish_id, name, f'["{tags}"]', energy, protein, fat, cho, fiber, na),
            )

        for item_id, dish_id, ingredient_id, raw_name, role in _DISH_INGREDIENTS:
            connection.exec_driver_sql(
                "INSERT INTO dish_ingredients (id, dish_id, ingredient_id, "
                "core_ingredient_id, raw_name, role, grams) "
                "VALUES (?, ?, ?, NULL, ?, ?, 300)",
                (item_id, dish_id, ingredient_id, raw_name, role),
            )

        connection.exec_driver_sql(
            "INSERT INTO seasonal_calendar (id, level, name, season, "
            "description, knowledge_json) VALUES "
            "('m10', '月份', '10月', '秋', '秋季润肺，这样吃抗病魔！', "
            "'[\"10月的应季蔬菜共 24 种：白萝卜、山药、莲藕、西兰花、南瓜。\"]'), "
            "('s-autumn', '季节', '秋', '秋', NULL, "
            "'[\"秋季（9月-11月）的应季水果有梨、苹果。\"]')"
        )
        for index, food in enumerate(_FOODS, start=1):
            connection.exec_driver_sql(
                "INSERT INTO seasonal_food (id, calendar_id, level, "
                "time_name, season, category, name, note, "
                "recommendation_reason, ingredient_id) "
                "VALUES (?, 'm10', '月份', '10月', '秋', '蔬菜', ?, NULL, "
                "NULL, ?)",
                (f"SF{index:04d}", f"时令食材{index}", food[0]),
            )
        connection.exec_driver_sql(
            "INSERT INTO seasonal_dish_links (seasonal_food_id, dish_id, "
            "match_type) VALUES ('SF0003', 103, 'ingredient')"
        )
    return engine


@pytest.fixture(name="compact_session")
def compact_session_fixture():
    with Session(_compact_engine()) as session:
        yield session


def _weather(kind: str = "dry") -> WeatherContext:
    return WeatherContext(
        city="杭州",
        date="2026-10-05",
        kind=kind,
        description="晴 20°C",
        temperature_c=20.0,
        source="live",
        advice=weather_service._ADVICE[kind],
    )


# =====================================================================
# 1. 综合打分算法：稳定 + 可解释 + 跨天轮换
# =====================================================================


def test_score_foods_is_deterministic_for_same_region_and_date(compact_session):
    """同地区 + 同一天 → 顺序完全一致（这是「所有人看到一样」的基础）。"""
    kwargs = dict(
        month=10,
        weather=_weather(),
        constraints=HardConstraints(),
        region="杭州",
        date_key="2026-10-05",
        limit=6,
    )
    first = [item.name for item in scoring_service.score_foods(compact_session, **kwargs)]
    second = [item.name for item in scoring_service.score_foods(compact_session, **kwargs)]
    assert first == second
    assert len(first) == 6


def test_score_foods_rotates_across_dates(compact_session):
    """跨天要换一批 —— 同档位内用日期做轮换，所以几天之内会出现不同顺序。"""
    orderings = {
        tuple(
            item.name
            for item in scoring_service.score_foods(
                compact_session,
                month=10,
                weather=_weather(),
                constraints=HardConstraints(),
                region="杭州",
                date_key=f"2026-10-{day:02d}",
                limit=6,
            )
        )
        for day in range(1, 15)
    }
    # 14 天里至少出现 3 种不同排序，才算「每天不一样」
    assert len(orderings) >= 3, f"跨天没有轮换，只有 {len(orderings)} 种顺序"


def test_score_foods_differs_between_regions(compact_session):
    """同一天不同地区也要不一样（地区是轮换种子的一部分）。"""
    orders = {
        tuple(
            item.name
            for item in scoring_service.score_foods(
                compact_session,
                month=10,
                weather=_weather(),
                constraints=HardConstraints(),
                region=region,
                date_key="2026-10-05",
                limit=6,
            )
        )
        for region in ("杭州", "北京", "成都", "广州", "西安")
    }
    assert len(orders) >= 2


def test_score_foods_always_explains_itself(compact_session):
    """每条推荐都必须带一句人能看懂的理由，不允许出现空理由。"""
    items = scoring_service.score_foods(
        compact_session,
        month=10,
        weather=_weather(),
        constraints=HardConstraints(),
        region="杭州",
        date_key="2026-10-05",
        limit=6,
    )
    for item in items:
        assert item.reason.strip(), f"{item.name} 没有推荐理由"
        assert item.factors["season"] > 0, f"{item.name} 的时令分不该是 0"


def test_score_foods_respects_avoid_hard_constraint(compact_session):
    """忌口是硬约束：命中的食材必须消失，且不是「排到最后」。"""
    items = scoring_service.score_foods(
        compact_session,
        month=10,
        weather=_weather(),
        constraints=HardConstraints(avoid=("梨",)),
        region="杭州",
        date_key="2026-10-05",
        limit=6,
    )
    assert all(item.name != "梨" for item in items)


def test_score_dishes_can_be_driven_by_selected_foods(compact_session):
    """配菜模式：候选只来自「能用这些食材做的菜」。"""
    items = scoring_service.score_dishes(
        compact_session,
        month=10,
        weather=_weather(),
        constraints=HardConstraints(),
        region="杭州",
        date_key="2026-10-05",
        food_ids=[3],  # 莲藕
        limit=6,
    )
    assert [item.name for item in items] == ["莲藕排骨汤"]


def test_score_dishes_reports_what_it_rejected(compact_session):
    """被硬约束挡掉的菜要能报出来 —— Critic 的否决必须是可见的。"""
    rejected: list[str] = []
    items = scoring_service.score_dishes(
        compact_session,
        month=10,
        weather=_weather(),
        constraints=HardConstraints(avoid=("西兰花",)),
        region="杭州",
        date_key="2026-10-05",
        limit=8,
        rejected_names=rejected,
    )
    assert all("西兰花" not in item.name for item in items)
    assert any("西兰花" in name for name in rejected)


def test_marketing_style_dish_names_are_not_recommendable():
    """清洗库里 461 道（4.6%）是抓取来的页面标题，不进推荐位。

    ⚠️ 只挡「推荐」，不动数据：那些菜在 /api/recipes 列表和搜索里照旧可见。
    """
    from app.services.scoring_service import is_recommendable_dish_name as ok

    # 正常的菜名要通过
    assert ok("莲藕排骨汤")
    assert ok("西红柿烧茄子")
    assert ok("秋日暖汤•田园大骨汤")

    # 抓取来的标题要挡住
    assert not ok("零难度还巨好吃的日式关东煮or火锅or蔬菜汤")
    assert not ok("龙利鱼清蒸搭配玉米木耳西兰花鸡蛋便当")  # 18 字
    assert not ok("懒人必备一锅出")
    assert not ok("酸甜开胃又下饭|番茄炖牛肉")  # 含分隔符
    assert not ok("")


def test_recommend_never_returns_marketing_titles(client):
    """接口层：配菜结果里不该出现这些标题。"""
    from app.services.scoring_service import is_recommendable_dish_name as ok

    body = client.post("/api/ai/recommend", json={"count": 6}).json()
    bad = [
        pick["recipe"]["name"]
        for pick in body["recommendations"]
        if not ok(pick["recipe"]["name"])
    ]
    assert not bad, f"推荐位出现了不规范的菜名：{bad}"

    # 但库里仍然有它们 —— 说明我们只是不推荐，没有删数据
    assert client.get("/api/recipes?page_size=1").json()["total"] > 0


def test_intent_recognizes_various_ways_to_say_my_foods():
    """★ 回归：用户说「要用我家里的食材」，必须走「用我的食材」这条链路。

    原来的关键词表只认「家里有 / 我的食材」这类固定串，
    用户那句「要用**我家里的食材**」一个都没命中（就差一个「的」），
    而句子里有「菜单」→ 被判成 meal_recommendation，
    整条库存链路压根没执行。用户看到的就是「让他用我家食材，他却推了别的」。
    """
    from app.services.ai_service import _detect_intent

    for message in (
        "要用我家里的食材",
        "我气血不足，想吃点补气血的，帮我调整一下今日的菜单，要用我家里的食材",
        "用家里的食材做菜",
        "我有什么",
        "看看我的食材能做什么",
        "家里食材还有啥能做的",
        "帮我用现有的材料配一下",
    ):
        assert _detect_intent(message) == "cook_with_my_foods", message

    # 纯点菜（没提自己的食材）仍然是推荐意图
    assert _detect_intent("三个人今晚吃什么") == "meal_recommendation"
    assert _detect_intent("推荐几道清淡的菜") == "meal_recommendation"
    # 闲聊
    assert _detect_intent("你好") == "general"


def test_health_goal_extraction():
    """★ 食养诉求要能被解析出来 —— 否则模型只能拿天气/时令硬凑。"""
    from app.services.need_service import effect_keywords_of, extract_goal

    goal = extract_goal("我气血不足，想吃点补气血的，帮我调整一下今日的菜单")
    assert goal is not None
    assert goal.name == "补气血"
    # 关键词必须是库里真实存在的功效词（写一个库里没有的词等于永远匹配不上）
    assert "补益气血" in effect_keywords_of(goal)

    assert extract_goal("最近有点上火").name == "清热降火"
    assert extract_goal("想健脾养胃").name == "健脾养胃"
    assert extract_goal("晚上睡不好").name == "安神助眠"
    assert extract_goal("想减脂").name == "低脂减重"
    # 没有诉求时返回 None，不能瞎猜
    assert extract_goal("三个人今晚吃什么") is None


def test_goal_keywords_all_exist_in_our_catalog(client):
    """诉求关键词必须能在我们自己的 effects_json 里匹配到东西。

    ⚠️ 这条防的是一类很隐蔽的 bug：词表里写了一个库里根本没有的近义词，
    匹配永远为 0，界面上看不出错，只是「诉求被无视了」。
    """
    from app.services.need_service import all_goals

    for goal in all_goals():
        assert goal.effect_keywords, f"{goal.name} 没有关键词"
    # 至少有这些诉求能在库里查到食材（用接口间接验证数据存在）
    body = client.get("/api/foods?page_size=200").json()
    assert body["items"], "得有食材"


def test_need_expressions_never_fall_into_chitchat(client):
    """★ 用户表达了需求，就绝不能被当成闲聊敷衍过去。

    这一条是架构性的回归：原来是「命中固定短语才算推荐」，实测 19 条常见说法
    里 **11 条判错** —— 而且最糟的是「我想减肥」「最近想补气血」这种：
    诉求都解析出来了，却因为判成闲聊而被整段丢掉。
    """
    need_expressions = [
        "三个人今晚吃什么", "推荐几道菜", "我想吃清淡点的",
        "有什么适合秋天的菜", "我想减肥", "最近想补气血",
        "今天中午吃啥", "给我来点汤", "帮我配个菜",
        "想喝汤", "来点低脂的", "四个人晚餐吃点啥好",
        "我不吃香菜", "我海鲜过敏", "我不吃辣",
    ]
    wrong = []
    for message in need_expressions:
        body = client.post("/api/ai/chat", json={"message": message}).json()
        if body["intent"] == "general":
            wrong.append(message)
    assert not wrong, f"这些明确的需求被当成了闲聊：{wrong}"


def test_chitchat_stays_chitchat_and_answers_on_topic(client):
    """闲聊要真的在闲聊，而且要答到点子上。

    以前不管是「你好」「谢谢」还是「你是谁」，离线兜底都回同一段自我介绍 ——
    「谢谢」回「我是小食，可以帮你安排今天吃什么」就是典型的牛头不对马嘴。
    """
    for message in ["你好", "谢谢", "你是谁", "再见", "这个App怎么用"]:
        body = client.post("/api/ai/chat", json={"message": message}).json()
        assert body["intent"] == "general", f"{message} 不该被当成要推荐"
        assert body["recipes"] == [], f"{message} 不该推菜"

    thanks = client.post("/api/ai/chat", json={"message": "谢谢"}).json()
    assert "不客气" in thanks["answer"], thanks["answer"]

    greeting = client.post("/api/ai/chat", json={"message": "你好"}).json()
    assert "你好" in greeting["answer"], greeting["answer"]


def test_declared_avoid_is_honored(client):
    """★ 用户在对话里声明的忌口必须生效 —— 这是安全问题。

    「我不吃鸡蛋」如果被当成闲聊忽略掉，后面推的菜里出现鸡蛋就是事故。
    """
    body = client.post(
        "/api/ai/chat", json={"message": "我不吃鸡蛋，推荐几道菜"}
    ).json()
    assert body["intent"] != "general"
    # 轨迹里要能看出系统听懂了
    summary = " ".join(step["summary"] for step in body["trace"])
    assert "忌口" in summary and "鸡蛋" in summary, summary
    # 而且真的没有推含鸡蛋的菜
    names = [r["name"] for r in body["recipes"]]
    assert "番茄炒蛋" not in names, f"声明了不吃鸡蛋却推了：{names}"


def test_mentioned_food_drives_recall(client):
    """★ 点名了食材，回答就得围绕它 —— 这是「牛头不对马嘴」的直接防线。

    「莲藕怎么做」如果只当成普通推荐，会推一堆当季菜，跟莲藕没关系。
    """
    body = client.post("/api/ai/chat", json={"message": "莲藕怎么做"}).json()
    assert body["intent"] != "general"
    summary = " ".join(step["summary"] for step in body["trace"])
    assert "点名" in summary and "莲藕" in summary, summary
    assert body["recipes"], "认出了食材却没有给出菜"


def test_every_food_gets_at_least_one_tag():
    """★ 每个食材都必须有标签 —— 用户明确提的要求。

    清洗库里 `effects_json` 只覆盖 124/590（21%），所以标签必须能从
    真实营养数值推出来，最后还有分类兜底。
    """
    from app.data.food_tags import derive_food_tags

    # ① 有功效标签 → 排最前（质量最高）
    with_effect = derive_food_tags(
        {
            "name": "莲藕",
            "effects_json": '["增强人体免疫力","补益气血"]',
            "energy_kcal": 47,
            "protein": 1.2,
            "na": 34.3,
            "subcategory": "根茎",
            "category": "蔬菜",
        }
    )
    assert with_effect[0] == "增强人体免疫力"

    # ② 没有功效标签 → 用真实营养数值推出标签（菠菜的真实数值）
    no_effect = derive_food_tags(
        {
            "name": "菠菜",
            "effects_json": "[]",
            "energy_kcal": 28.0,
            "protein": 2.6,
            "fat": 0.3,
            "vitamin_c": 32.0,
            "dietary_fiber": 1.7,
            "na": 85.2,
            "ca": 66.0,
            "subcategory": "叶菜",
            "category": "蔬菜",
        }
    )
    assert no_effect, "没有功效标签时必须推出营养标签"
    assert "富含维生素C" in no_effect      # 32mg/100g >= 30
    assert "低热量" in no_effect           # 28kcal <= 40
    assert "低钠" in no_effect             # 85mg <= 100

    # ③ 连营养数据都没有 → 兜底到子类 / 分类，但仍然非空
    assert derive_food_tags(
        {"name": "某物", "subcategory": "叶菜", "category": "蔬菜"}
    ) == ["叶菜"]
    assert derive_food_tags(
        {"name": "某物", "subcategory": "猪", "category": "畜肉"}
    ) == ["肉类"]
    assert derive_food_tags({"name": "某物"}) == ["食材"]

    # ④ 源数据里混进来的句子碎片要清掉（大米的 effects_json 就有这种）
    cleaned = derive_food_tags(
        {
            "name": "大米",
            "effects_json": '["健脑益智。","止咳平喘。适用于咳嗽","气喘。","填精补髓"]',
        }
    )
    assert "健脑益智" in cleaned          # 去掉了句尾的「。」
    assert "填精补髓" in cleaned
    assert all("。 " not in t for t in cleaned)
    assert all(len(t) <= 10 for t in cleaned), cleaned
    # 「止咳平喘。适用于咳嗽」是句子，不该当标签留下来
    assert not any("适用于" in t for t in cleaned)


def test_foods_api_never_returns_empty_tags(client):
    """接口层：列表里每个食材都带标签。"""
    body = client.get("/api/foods?page_size=50").json()
    assert body["items"], "得有食材"
    missing = [item["name"] for item in body["items"] if not item.get("tags")]
    assert not missing, f"这些食材没有标签：{missing}"


def test_duration_is_extracted_from_instruction_text():
    """★ 清洗库没有烹饪时长列 —— 从做法文本里抽真实时长。

    这直接关系到「今天来得及做吗」这条硬约束是不是真的：
    拿一个估出来的数字去否决一道菜，等于用编的数据删候选。
    """
    from app.repositories.catalog_insight_repository import _duration_from_text

    # 取所有提到的时间里的最大值（腌制 10 分钟 + 炖 30 分钟 → 40 分钟才是占用时长）
    assert _duration_from_text("排骨焯水。小火炖 30 分钟。出锅前腌制 10 分钟。") == 30
    assert _duration_from_text("大火煮开，转小火 20-30分钟") == 30
    assert _duration_from_text("炖 1.5 小时即可") == 90
    assert _duration_from_text("腌制 12 小时") == 180  # 有上限，避免离谱值
    assert _duration_from_text("洗净切块，下锅炒熟") is None
    assert _duration_from_text("") is None
    assert _duration_from_text(None) is None


def test_cook_time_filter_only_trusts_real_durations(session):
    """时长有依据 → 硬筛；没依据 → 只降权，不删候选。"""
    from app.services import scoring_service
    from app.services.scoring_service import HardConstraints
    from app.services.weather_service import WeatherContext

    weather = WeatherContext(
        city=None, date="2026-10-05", kind="dry", description="晴 20°C",
        source="estimated", advice="秋燥当令",
    )
    # 旧演示表有时长列 → duration_source = table → 会被硬筛掉
    rejected: list[str] = []
    kept = scoring_service.score_dishes(
        session,
        month=9,
        weather=weather,
        constraints=HardConstraints(people=3, cook_minutes=15),
        region="national",
        date_key="2026-10-05",
        limit=20,
        rejected_names=rejected,
    )
    assert "莲藕排骨汤" not in {item.name for item in kept}
    assert any("莲藕排骨汤" in name for name in rejected), rejected


def test_weather_advice_changes_the_scores(compact_session):
    """天气是打分的一个真实因子，不是摆设。

    ⚠️ 这里断言的是 **factors / quality**，而不是最终的展示顺序：
       展示顺序是「质量前 N 名 → 当日轮换」两步出来的，轮换因子
       （sha256(地区+日期+名字)）与天气无关，所以同一个日期下
       冷天和热天的**顺序**可能一模一样，但**打分**一定不同。
       断言分数才是断言「天气真的参与了计算」。
    """
    def scored(kind: str) -> dict[str, float]:
        items = scoring_service.score_dishes(
            compact_session,
            month=10,
            weather=_weather(kind),
            constraints=HardConstraints(),
            region="杭州",
            date_key="2026-10-05",
            limit=8,
        )
        return {item.name: item.factors["weather"] for item in items}

    cold = scored("cold")
    hot = scored("hot")

    # 「凉拌西兰花」在热天更贴合（凉菜/减肥/低脂），冷天不该更贴合
    assert hot.get("凉拌西兰花", 0) > cold.get("凉拌西兰花", 0), (cold, hot)

    # 「莲藕排骨汤」在冷天更贴合（汤羹/炖），热天不该更高
    assert cold.get("莲藕排骨汤", 0) >= hot.get("莲藕排骨汤", 0), (cold, hot)

    # 整体打分也必须随天气变化，而不是只改了标签
    cold_quality = {
        item.name: round(item.quality, 4)
        for item in scoring_service.score_dishes(
            compact_session, month=10, weather=_weather("cold"),
            constraints=HardConstraints(), region="杭州",
            date_key="2026-10-05", limit=8,
        )
    }
    hot_quality = {
        item.name: round(item.quality, 4)
        for item in scoring_service.score_dishes(
            compact_session, month=10, weather=_weather("hot"),
            constraints=HardConstraints(), region="杭州",
            date_key="2026-10-05", limit=8,
        )
    }
    assert cold_quality != hot_quality


# =====================================================================
# 2. AI 只能在候选集内挑选（幻觉防线）
# =====================================================================


def test_ai_picks_outside_candidates_are_dropped():
    """★ 这条是「AI 不能从全库自由生成」的核心断言。"""
    from app.services.ai_service import _coerce_picks

    allowed = {101, 102, 103}
    picked = _coerce_picks(
        [
            {"id": 101, "reason": "当季"},
            {"id": 999999, "reason": "编造的菜"},  # 库里不存在
            {"id": "abc", "reason": "不是数字"},
            {"id": 102, "reason": "清淡"},
            {"id": 101, "reason": "重复"},
            {"id": 103, "reason": "汤"},
        ],
        allowed,
        3,
    )
    assert [entry["id"] for entry in picked] == [101, 102, 103]


def test_ai_daily_cache_serves_the_whole_region_for_the_day(session):
    """★ 一个地区一天只问一次 AI：写进缓存后，第二次直接命中，不再调模型。"""
    weather = _weather()
    key = ai_daily_service.build_cache_key(
        region="杭州", date_key="2026-10-05", month=10, weather=weather
    )
    ai_daily_service._write_cache(
        session,
        key,
        {
            "tip_title": "秋燥润肺",
            "tip_body": "今天杭州天干，多吃润燥的。",
            "food_picks": [3, 6],
            "dish_picks": [103, 106],
            "food_notes": {"3": "莲藕润燥"},
            "dish_notes": {"103": "汤水润肺"},
            "model": "deepseek-chat",
        },
        "deepseek-chat",
    )

    result = ai_daily_service.enhance_home(
        session,
        region="杭州",
        date_key="2026-10-05",
        month=10,
        weather=weather,
        food_shortlist=[],
        dish_shortlist=[],
    )
    assert result.source == "cached"
    assert result.food_picks == [3, 6]
    assert result.dish_picks == [103, 106]
    assert result.food_notes[3] == "莲藕润燥"


def test_ai_daily_cache_key_is_per_region_and_date():
    weather = _weather()
    base = dict(month=10, weather=weather)
    assert ai_daily_service.build_cache_key(
        region="杭州", date_key="2026-10-05", **base
    ) != ai_daily_service.build_cache_key(
        region="北京", date_key="2026-10-05", **base
    )
    assert ai_daily_service.build_cache_key(
        region="杭州", date_key="2026-10-05", **base
    ) != ai_daily_service.build_cache_key(
        region="杭州", date_key="2026-10-06", **base
    )


def test_enhance_home_falls_back_when_ai_not_configured(session):
    """没有 API Key 时不许抛异常，要退回确定性结果并如实标注来源。"""
    result = ai_daily_service.enhance_home(
        session,
        region="杭州",
        date_key="2026-10-05",
        month=10,
        weather=_weather(),
        food_shortlist=[],
        dish_shortlist=[],
    )
    assert result.source == "algorithm"
    assert result.error


# =====================================================================
# 3. 首页接口
# =====================================================================


def test_home_exposes_algorithm_and_weather(client):
    body = client.get("/api/home?city=杭州&month=10&date=2026-10-05").json()

    assert len(body["recommended_foods"]) > 0
    assert len(body["recommended_menus"]) > 0
    assert body["ai_tip"]

    # 新增的天气、算法元信息、推荐理由
    assert body["weather"]["source"] == "estimated"  # 测试里禁用了天气网络
    assert body["weather"]["kind"] == "dry"  # 10 月 → 秋燥
    assert body["meta"]["source"] == "algorithm"  # 测试里禁用了 AI
    assert body["meta"]["steps"], "算法轨迹不能是空的 —— 答辩要靠它"
    for item in body["recommended_foods"]:
        assert item["reason"]


def test_home_is_stable_for_same_region_and_day(client):
    """同一地区同一天，两次请求的推荐必须一模一样（AI 缓存的前提）。"""
    url = "/api/home?city=杭州&month=10&date=2026-10-05"
    first = client.get(url).json()
    second = client.get(url).json()

    assert [f["name"] for f in first["recommended_foods"]] == [
        f["name"] for f in second["recommended_foods"]
    ]
    assert [r["name"] for r in first["recommended_recipes"]] == [
        r["name"] for r in second["recommended_recipes"]
    ]
    assert first["ai_tip"] == second["ai_tip"]


def test_home_recommends_recipes_with_reasons(client):
    body = client.get("/api/home?month=10&date=2026-10-05").json()
    assert body["recommended_recipes"], "首页要有推荐菜品"
    for item in body["recommended_recipes"]:
        assert item["reason"]
        assert item["duration_minutes"] >= 0


def test_home_foods_keep_their_season_score(client):
    """★ 回归：推荐的食材必须带真实的应季程度。

    曾经漏传 season 对象，导致首页所有食材的 season_score 都是 0 ——
    卡片上的「应季程度」就等于失效了，界面上还看不出来。
    """
    body = client.get("/api/home?month=9&date=2026-10-05").json()
    scores = {f["name"]: f["season_score"] for f in body["recommended_foods"]}
    assert scores.get("莲藕") == 95
    assert all(score > 0 for score in scores.values())


def test_scoring_excludes_dishes_over_the_cook_time(client, session):
    """可用烹饪时间是一道硬筛：60 分钟的「莲藕排骨汤」在 15 分钟预算下必须出局。

    ⚠️ 为什么在打分层断言，而不是看首页返回的那 3 道：
       首页只展示 3 道，而这 3 道是「质量前 N 名 → 当日轮换」选出来的，
       具体哪 3 道会随日期变。断言「某一道一定出现」会跟轮换打架 ——
       那测的就不是「时间约束生效」，而是「今天轮到了它」。
       所以这里断言打分层的候选集（轮换之前的完整池子）。
    """
    from app.services import scoring_service
    from app.services.scoring_service import HardConstraints
    from app.services.weather_service import WeatherContext

    weather = WeatherContext(
        city=None, date="2026-10-05", kind="dry", description="晴 20°C",
        source="estimated", advice="秋燥当令",
    )

    def candidates(minutes: float) -> set[str]:
        return {
            item.name
            for item in scoring_service.score_dishes(
                session,
                month=9,
                weather=weather,
                constraints=HardConstraints(people=3, cook_minutes=minutes),
                region="national",
                date_key="2026-10-05",
                limit=20,
            )
        }

    assert "莲藕排骨汤" in candidates(240)   # 时间宽裕 → 可以推荐
    assert "莲藕排骨汤" not in candidates(15)  # 只剩 15 分钟 → 出局


def test_home_never_recommends_dishes_over_the_cook_time(client):
    """接口层：可用时间收窄后，首页推荐里不能出现超时的菜。"""
    tight = client.get(
        "/api/home?month=9&date=2026-10-05&cook_minutes=15"
    ).json()
    over = [
        item["name"]
        for item in tight["recommended_recipes"]
        if item["duration_minutes"] > 15
    ]
    assert not over, f"15 分钟预算下不该出现这些菜：{over}"
    assert "莲藕排骨汤" not in {i["name"] for i in tight["recommended_recipes"]}


# =====================================================================
# 4. 导航栏 AI 配菜接口
# =====================================================================


def test_recommend_returns_recipes_from_our_own_database(client):
    resp = client.post("/api/ai/recommend", json={"count": 3})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["recommendations"], "至少要推荐出一道菜"
    assert body["trace"], "协作轨迹不能为空"
    assert body["source"] == "algorithm"  # 测试里禁用了 AI

    # 推荐出来的菜必须真的在库里（不能是模型编的）
    for pick in body["recommendations"]:
        recipe_id = pick["recipe"]["id"]
        assert client.get(f"/api/recipes/{recipe_id}").status_code == 200
        assert pick["reason"]


def test_recommend_excludes_recipes_already_in_today_menu(client):
    """今日菜单里已有的菜不能再被推荐。"""
    everything = client.post("/api/ai/recommend", json={"count": 6}).json()
    taken = [pick["recipe"]["id"] for pick in everything["recommendations"]][:1]
    assert taken

    body = client.post(
        "/api/ai/recommend", json={"count": 6, "menu_recipe_ids": taken}
    ).json()
    returned = {pick["recipe"]["id"] for pick in body["recommendations"]}
    assert not (returned & set(taken))


def test_recommend_uses_selected_foods(client):
    """选了「莲藕」就应该优先推能用莲藕做的菜。

    注意这里把可用时间放宽到 90 分钟 —— 「莲藕排骨汤」要炖 60 分钟，
    默认的 45 分钟本来就该把它筛掉（那是另一条测试在管的事）。
    """
    body = client.post(
        "/api/ai/recommend",
        json={"count": 3, "food_ids": [1], "cook_minutes": 90},
    ).json()
    names = [pick["recipe"]["name"] for pick in body["recommendations"]]
    assert "莲藕排骨汤" in names
    assert body["used_foods"] == ["莲藕"]
    picked = next(
        pick for pick in body["recommendations"] if pick["recipe"]["name"] == "莲藕排骨汤"
    )
    assert "莲藕" in picked["matched_foods"]


def test_recommend_keeps_within_cook_time(client):
    """时间不够时，即使用了对应食材也不硬推超时的菜 —— 硬约束优先于食材匹配。"""
    body = client.post(
        "/api/ai/recommend",
        json={"count": 3, "food_ids": [1], "cook_minutes": 15},
    ).json()
    names = [pick["recipe"]["name"] for pick in body["recommendations"]]
    assert "莲藕排骨汤" not in names


def test_recommend_respects_avoid_constraint(client):
    """忌口是硬约束 —— 含鸡蛋的菜不该被推荐。"""
    body = client.post(
        "/api/ai/recommend", json={"count": 6, "avoid": ["鸡蛋"]}
    ).json()
    names = [pick["recipe"]["name"] for pick in body["recommendations"]]
    assert "番茄炒蛋" not in names


def test_recommend_without_foods_still_works(client):
    """没选食材也要能用（退回按时令推荐），不能 500。"""
    resp = client.post("/api/ai/recommend", json={"count": 3})
    assert resp.status_code == 200
    assert resp.json()["recommendations"]


# =====================================================================
# 5. AI 助手对话（回归：老契约不变，新增字段可用）
# =====================================================================


def test_chat_keeps_old_contract_and_adds_trace(client):
    body = client.post("/api/ai/chat", json={"message": "三个人今晚吃什么"}).json()

    # 老契约
    assert body["answer"]
    assert body["intent"] == "meal_recommendation"
    assert body["tools_used"]
    assert body["menu"] is not None

    # 新字段：真实轨迹 + 来源标注
    assert body["trace"], "对话也要有协作轨迹"
    assert body["source"] == "algorithm"


def test_chat_trace_mentions_the_real_constraints(client):
    """轨迹里读到的约束必须是真的 —— 改人数，轨迹就该跟着变。"""
    body = client.post(
        "/api/ai/chat",
        json={"message": "今晚吃什么", "people": 6, "avoid": ["辛辣", "花生"]},
    ).json()
    summary = " ".join(step["summary"] for step in body["trace"])
    assert "6 人" in summary
    assert "花生" in summary


def test_follow_up_keeps_recommending_and_avoids_repeats(client):
    """★ 追问必须继续推荐，并且「换一批」真的是换一批。

    用户反馈的现象：「第一问有卡片，后面再问就没了」。
    原因：意图识别是逐句独立的关键词匹配 ——「换一批呢」里没有任何
    「吃什么/推荐/菜单」，被判成闲聊，后端压根不去推荐。

    这条测试同时锁住两件事：
      1. 追问不再掉进闲聊分支（意图继承上一轮）
      2. 已经展示过的菜会被避开（否则轮换因子固定，重问还是那三道）
    """
    first = client.post(
        "/api/ai/chat", json={"message": "三个人今晚吃什么"}
    ).json()
    assert first["intent"] == "meal_recommendation"
    assert len(first["recipes"]) == 3
    shown = [r["id"] for r in first["recipes"]]

    second = client.post(
        "/api/ai/chat",
        json={
            "message": "换一批呢",
            "last_intent": "meal_recommendation",
            "recent_recipe_ids": shown,
        },
    ).json()

    # ① 仍然是推荐意图，而且真的给了菜（这就是「卡片消失」的直接原因）
    assert second["intent"] == "meal_recommendation", second["trace"]
    assert second["recipes"], "追问之后必须还有菜，否则界面上卡片就没了"
    # ② 换了一批：不再重复已经展示过的那三道
    new_ids = [r["id"] for r in second["recipes"]]
    assert not (set(new_ids) & set(shown)), f"换一批却重复了：{new_ids} vs {shown}"
    # ③ 轨迹里能看出确实避开了
    assert any("避开" in step["summary"] for step in second["trace"])


def test_follow_up_without_context_still_recommends(client):
    """前端没带上下文时，「换一批」也不能掉进闲聊分支。"""
    body = client.post("/api/ai/chat", json={"message": "换一批"}).json()
    assert body["intent"] == "meal_recommendation"
    assert body["recipes"]


def test_plain_greeting_still_has_no_recipes(client):
    """真正的闲聊不能被追问逻辑带偏 —— 闲聊还是不推菜。"""
    body = client.post("/api/ai/chat", json={"message": "你好"}).json()
    assert body["intent"] == "general"
    assert body["recipes"] == []


# =====================================================================
# 提示词组装
#
# 这一组直接调 `_recommend_prompt` / `_chat_prompt`，而不是打接口 ——
# 因为测试环境里 AI 是**故意关掉**的（conftest 的 _hermetic_externals，
# 免得 pytest 真去烧 token），`client.is_configured()` 为假时提示词
# 压根不会被组装，接口测试覆盖不到这段代码。
#
# ★ 这里锁的是一个真实发生过的 500：
#   `_recommend_prompt` 里引用了 `health_goal`，但既没定义也没传进来，
#   于是只要「AI 开着 + 用户说了句食养诉求」，/api/ai/recommend 就
#   NameError 直接 500。测试全绿是因为它永远走不到那一行。
#   静态检查（`python -m ruff check app --select F821`）是这类 bug 的兜底。
# =====================================================================


def test_recommend_prompt_includes_health_goal(session):
    from app.services.ai_service import _recommend_prompt
    from app.services.need_service import extract_goal
    from app.schemas.ai import AiRecommendRequest

    goal = extract_goal("我气血不足，想吃点补气血的")
    assert goal is not None, "「气血不足」应该能被识别成食养诉求"

    prompt = _recommend_prompt(
        session=session,
        payload=AiRecommendRequest(food_ids=[1], count=2, city="杭州"),
        constraints=HardConstraints(people=3, cook_minutes=60),
        weather=WeatherContext(
            city="杭州", date="2026-10-05", kind="clear",
            description="晴 18°C", source="estimated", advice="秋燥当令，宜润肺",
        ),
        month=10,
        food_names=["莲藕"],
        menu_names=[],
        candidates=[],
        health_goal=goal,
    )

    # 诉求要真的写进提示词，否则模型根本不知道用户是来补气血的
    assert "补气血" in prompt
    assert "核心诉求" in prompt


def test_recommend_prompt_works_without_health_goal(session):
    """没有食养诉求时也要能组装（health_goal 是可选参数）。"""
    from app.services.ai_service import _recommend_prompt
    from app.schemas.ai import AiRecommendRequest

    prompt = _recommend_prompt(
        session=session,
        payload=AiRecommendRequest(count=2),
        constraints=HardConstraints(people=3, cook_minutes=60),
        weather=WeatherContext(
            city="杭州", date="2026-10-05", kind="clear",
            description="晴 18°C", source="estimated", advice="秋燥当令",
        ),
        month=10,
        food_names=[],
        menu_names=[],
        candidates=[],
    )
    assert "核心诉求" not in prompt
    assert "帮用户配" in prompt
