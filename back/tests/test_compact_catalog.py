"""清洗后六表内容库的兼容性测试。"""

from sqlalchemy import text
from sqlmodel import Session, create_engine
from sqlmodel.pool import StaticPool

from app.repositories import food_repository, recipe_repository
from app.services import food_service, recipe_service


def _compact_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    statements = [
        """CREATE TABLE ingredients (
            id INTEGER PRIMARY KEY, name TEXT, ingredient_type TEXT,
            core_ingredient_id INTEGER, category TEXT, subcategory TEXT,
            is_core_raw INTEGER, is_edible INTEGER, review_status TEXT,
            usage_count INTEGER, reason TEXT, energy_kcal REAL, protein REAL,
            fat REAL, cho REAL, effects_json TEXT
        )""",
        """CREATE TABLE dishes (
            id INTEGER PRIMARY KEY, dish_name TEXT, dish_name_original TEXT,
            description TEXT, cuisine TEXT, instruction_text TEXT,
            tags_json TEXT
        )""",
        """CREATE TABLE dish_ingredients (
            id INTEGER PRIMARY KEY, dish_id INTEGER, ingredient_id INTEGER,
            core_ingredient_id INTEGER, raw_name TEXT, raw_text TEXT,
            quantity TEXT, role TEXT, grams REAL
        )""",
        """CREATE TABLE seasonal_calendar (
            id TEXT PRIMARY KEY, level TEXT, name TEXT, season TEXT
        )""",
        """CREATE TABLE seasonal_food (
            id TEXT PRIMARY KEY, calendar_id TEXT, level TEXT, time_name TEXT,
            season TEXT, ingredient_id INTEGER, note TEXT,
            recommendation_reason TEXT
        )""",
        """CREATE TABLE seasonal_dish_links (
            seasonal_food_id TEXT, dish_id INTEGER, match_type TEXT
        )""",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text(
                "INSERT INTO ingredients VALUES "
                "(1, '鸡肉', 'core', NULL, '禽肉', '禽肉', 1, 1, 'approved', 20, "
                "'优质蛋白', 167, 19.3, 9.4, 1.3, '[\"补充蛋白质\"]'), "
                "(2, '鸡胸肉', 'variant', 1, '禽肉', '禽肉', 0, 1, 'approved', 10, "
                "'低脂', 133, 19.4, 5, 2.5, '[\"低脂\"]')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO dishes VALUES "
                "(10, '香煎鸡胸肉', '香煎鸡胸肉', '简单健康', '家常菜', "
                "'1、鸡胸肉切片\n2、煎至熟透', '[\"高蛋白\"]')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO dish_ingredients VALUES "
                "(100, 10, 2, 1, '鸡胸肉', '鸡胸肉200克', '200克', 'main', 200)"
            )
        )
        connection.execute(text("INSERT INTO seasonal_calendar VALUES ('m09', '月份', '9月', '秋')"))
        connection.execute(
            text(
                "INSERT INTO seasonal_food VALUES "
                "('sf1', 'm09', '月份', '9月', '秋', 2, NULL, '秋季适宜')"
            )
        )
        connection.execute(text("INSERT INTO seasonal_dish_links VALUES ('sf1', 10, 'ingredient')"))
    return engine


def test_compact_catalog_food_recipe_and_parent_inference():
    with Session(_compact_engine()) as session:
        foods, total = food_repository.list_foods(session, offset=0, limit=20)
        assert total == 2
        assert foods[0].name == "鸡肉"
        assert foods[0].category == "meat_egg"

        # 核心食材“鸡肉”能推出使用子类“鸡胸肉”的菜谱。
        inferred = recipe_repository.list_by_food(session, 1)
        assert [item.name for item in inferred] == ["香煎鸡胸肉"]

        detail = recipe_service.get_detail(session, 10)
        assert detail is not None
        assert detail.ingredients[0].food_id == 2
        assert detail.ingredients[0].amount == "200"
        assert len(detail.steps) == 2

        food_detail = food_service.get_detail(session, 1)
        assert food_detail is not None
        assert food_detail.recommended_recipes[0].id == 10


def test_compact_catalog_search_and_season():
    with Session(_compact_engine()) as session:
        rows, total = recipe_repository.search(session, "鸡胸", offset=0, limit=10)
        assert total == 1
        assert rows[0].id == 10

        seasonal = food_repository.list_seasonal(session, month=9, limit=10)
        assert len(seasonal) == 1
        assert seasonal[0][0].name == "鸡胸肉"
        assert seasonal[0][1].season_score == 100
