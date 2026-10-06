"""部署路径的测试：建表 / 补列 / 内容数据这三件事在服务器上必须成立。

为什么单独一个文件：
    这些不是业务逻辑，是**运维会依赖的机制**。它们在本地开发时看不出来 ——
    因为开发库早就建好了，而服务器上的情况是：
      · 全新库 → 靠 create_all 建表
      · 老库升级 → create_all **不会**加列，只能靠 _ensure_columns 的 ALTER
    这两种都要测，否则「服务器上起来就报 no such column」会一直复发。
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlmodel import create_engine

from app.core import database as db


def _make_legacy_table(engine) -> None:
    """造一张「旧版」的 user_preferences：只有加新列之前的字段。"""
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE user_preferences ("
                "id INTEGER PRIMARY KEY, user_id INTEGER, taste TEXT, "
                "diet_style TEXT, avoid_foods JSON, favorite_categories JSON)"
            )
        )


def test_ensure_columns_upgrades_an_existing_table(tmp_path):
    """★ 老库升级：缺的列要能补上。

    这是最容易漏、后果最直接的一环 —— `create_all` 只建**不存在**的表，
    给已存在的表加字段它一概不管。不补的话服务器上表现是
    「保存了偏好，一查就 500: no such column」。
    """
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    _make_legacy_table(engine)

    before = {c["name"] for c in inspect(engine).get_columns("user_preferences")}
    assert "low_sodium" not in before, "前提：这张表一开始就没有新列"

    original = db.engine
    db.engine = engine
    try:
        db._ensure_columns()
    finally:
        db.engine = original

    after = {c["name"] for c in inspect(engine).get_columns("user_preferences")}
    for column in ("low_sodium", "cook_minutes", "tools", "diet_preferences"):
        assert column in after, f"升级后仍然缺列：{column}"


def test_ensure_columns_is_idempotent(tmp_path):
    """补列必须幂等 —— deploy.sh 会被反复跑，第二次不能报 duplicate column。"""
    engine = create_engine(f"sqlite:///{(tmp_path / 'twice.db').as_posix()}")
    _make_legacy_table(engine)

    original = db.engine
    db.engine = engine
    try:
        db._ensure_columns()
        db._ensure_columns()  # 再跑一次不该炸
        db._ensure_columns()
    finally:
        db.engine = original

    cols = [c["name"] for c in inspect(engine).get_columns("user_preferences")]
    assert cols.count("low_sodium") == 1


def test_ensure_columns_skips_tables_that_do_not_exist_yet(tmp_path):
    """表还不存在时不能报错 —— 全新库的路径上，create_all 已经把它带着全部列建好了。"""
    engine = create_engine(f"sqlite:///{(tmp_path / 'empty.db').as_posix()}")

    original = db.engine
    db.engine = engine
    try:
        db._ensure_columns()  # 空库，什么都不该做，也不该抛
    finally:
        db.engine = original


def test_added_columns_are_declared_for_every_new_model_field():
    """`_ADDED_COLUMNS` 不能漏 —— 它和模型字段是手工同步的。

    漏一个的后果：新库没事（create_all 带着列一起建），
    **老库升级就会 500**，而且只在服务器上复现。
    """
    from app.models.user import UserPreference

    model_columns = set(UserPreference.model_fields.keys())
    declared = set(db._ADDED_COLUMNS.get("user_preferences", {}))

    # 加列之前就有的字段（它们本来就存在，不需要 ALTER）
    original_columns = {
        "id", "user_id", "taste", "diet_style", "avoid_foods",
        "favorite_categories", "created_at", "updated_at",
    }
    new_fields = model_columns - original_columns
    missing = new_fields - declared
    assert not missing, (
        f"这些新字段没有写进 database._ADDED_COLUMNS，老库升级会缺列：{missing}"
    )
