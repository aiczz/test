"""数据库连接（说明书 §7 / §25）。

SQLite 与 PostgreSQL 的差异只在这一层处理，上层代码不感知。
"""

from collections.abc import Generator
from weakref import WeakKeyDictionary

from sqlalchemy import inspect
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


def create_db_and_tables() -> None:
    """建表。

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


def get_session() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个 Session。"""
    with Session(engine) as session:
        yield session
