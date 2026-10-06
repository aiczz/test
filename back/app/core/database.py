"""数据库连接（说明书 §7 / §25）。

SQLite 与 PostgreSQL 的差异只在这一层处理，上层代码不感知。
"""

from collections.abc import Generator
from weakref import WeakKeyDictionary

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

# SQLite 默认禁止跨线程复用连接，而 FastAPI 会把同步依赖丢到线程池里跑，
# 不关掉这个检查就会报 "SQLite objects created in a thread can only be used
# in that same thread"。PostgreSQL 不需要这个参数。
_is_sqlite = settings.database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args=_connect_args,
)

COMPACT_CATALOG_TABLES = {
    "ingredients",
    "dishes",
    "dish_ingredients",
    "seasonal_calendar",
    "seasonal_food",
    "seasonal_dish_links",
}

STATE_TABLES = {
    "users",
    "user_preferences",
    "login_logs",
    "favorites",
    "my_foods",
    "menu_plans",
    "menu_plan_items",
    "shopping_lists",
    "shopping_items",
    # 验证码也是用户侧状态表。漏了它的话，compact 模式下 create_all 只建
    # STATE_TABLES 里的表，这张新表在服务器上根本不会被创建。
    "verification_codes",
    # 首页每日 AI 结果缓存。同上 —— 漏了它，服务器（compact 模式）上不会建表，
    # 于是每天每地区都要重新问一次大模型，token 白烧。
    "ai_daily_cache",
}

_catalog_mode_cache: WeakKeyDictionary[Engine, bool] = WeakKeyDictionary()


def uses_compact_catalog(bind: Engine | None = None) -> bool:
    """判断当前连接是否使用清洗后的六表内容库。

    auto 模式会拒绝“只导入了一部分”的数据库，避免后端在残缺数据上运行。
    """
    if settings.content_mode == "legacy":
        return False

    target = bind or engine
    target = getattr(target, "engine", target)
    cached = _catalog_mode_cache.get(target)
    if cached is not None:
        return cached
    existing = set(inspect(target).get_table_names())
    present = COMPACT_CATALOG_TABLES & existing
    complete = present == COMPACT_CATALOG_TABLES

    if settings.content_mode == "compact" and not complete:
        missing = ", ".join(sorted(COMPACT_CATALOG_TABLES - existing))
        raise RuntimeError(f"清洗数据库缺少表：{missing}")
    if present and not complete:
        missing = ", ".join(sorted(COMPACT_CATALOG_TABLES - existing))
        raise RuntimeError(f"检测到不完整的清洗数据库，缺少表：{missing}")
    _catalog_mode_cache[target] = complete
    return complete


# 增量列：表已经存在时，`create_all` 不会补列，缺的列要在启动时 ALTER 上去。
#
# 【为什么需要这个】
# 家庭档案新增了 low_sodium / cook_minutes / tools / diet_preferences 四列。
# 开发机和服务器上都已经有一个建好表的 shishi.db 了，光靠 create_all
# 新列永远不会出现 —— 于是「保存了偏好，一查就报 no such column」。
#
# 只做 `ADD COLUMN`（幂等、不丢数据），不做改类型/删列。
# 上 PostgreSQL 后这一小段应该换成 Alembic（说明书 §25）。
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "user_preferences": {
        "diet_preferences": "JSON",
        "tools": "JSON",
        "low_sodium": "BOOLEAN DEFAULT 1",
        "cook_minutes": "INTEGER DEFAULT 45",
    },
}


def _ensure_columns() -> None:
    """把 `_ADDED_COLUMNS` 里声明的列补到已有表上（幂等）。"""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table, columns in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue  # 表还不存在，create_all 会带着全部列建出来
        present = {column["name"] for column in inspector.get_columns(table)}
        missing = {name: ddl for name, ddl in columns.items() if name not in present}
        if not missing:
            continue
        with engine.begin() as connection:
            for name, ddl in missing.items():
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                )


def create_db_and_tables() -> None:
    """建表 + 补列。

    SQLite 阶段直接用 `create_all`（幂等）；
    切到 PostgreSQL 后应改用 Alembic 迁移（说明书 §25），
    这里的调用可以保留，不会有副作用。
    """
    # 必须先把模型模块 import 进来，否则 SQLModel.metadata 是空的，
    # create_all 什么都不会建 —— 这是最常见的"表没建出来"的原因。
    from app import models  # noqa: F401  （只为触发注册）

    if uses_compact_catalog(engine):
        # 六张内容表由清洗脚本维护，后端只创建用户侧业务表，绝不改写内容库。
        tables = [
            table
            for name, table in SQLModel.metadata.tables.items()
            if name in STATE_TABLES
        ]
        SQLModel.metadata.create_all(engine, tables=tables)
    else:
        SQLModel.metadata.create_all(engine)

    _ensure_columns()


def get_session() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个 Session。"""
    with Session(engine) as session:
        yield session
