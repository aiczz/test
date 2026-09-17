"""数据库连接（说明书 §7 / §25）。

SQLite 与 PostgreSQL 的差异只在这一层处理，上层代码不感知。
"""

from collections.abc import Generator

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


def create_db_and_tables() -> None:
    """建表。

    SQLite 阶段直接用 `create_all`（幂等）；
    切到 PostgreSQL 后应改用 Alembic 迁移（说明书 §25），
    这里的调用可以保留，不会有副作用。
    """
    # 必须先把模型模块 import 进来，否则 SQLModel.metadata 是空的，
    # create_all 什么都不会建 —— 这是最常见的"表没建出来"的原因。
    from app import models  # noqa: F401  （只为触发注册）

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个 Session。"""
    with Session(engine) as session:
        yield session
