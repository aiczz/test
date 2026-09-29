"""测试夹具。

每个测试用一套【独立的内存 SQLite】并灌好种子数据 —— 绝不碰开发用的
shishi.db，测试之间也互不干扰。
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.core.database import get_session
from app.core.config import settings
from app.data.seed import seed_all
from app.main import app

# 本机生产配置可以强制 CONTENT_MODE=compact；测试同时覆盖旧演示表和六表适配器，
# 因此必须按每个临时数据库的实际表结构自动识别。
settings.content_mode = "auto"


@pytest.fixture(name="engine")
def engine_fixture():
    # StaticPool + 内存库：所有连接共用同一个内存数据库。
    # 不用 StaticPool 的话每个新连接都是一个空库，表会"凭空消失"。
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_all(session)
    return engine


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session):
    def _override_get_session():
        yield session

    app.dependency_overrides[get_session] = _override_get_session
    # 注意：不写成 `with TestClient(app)`，那样会触发 lifespan，
    # 从而去连真实的 shishi.db 并重复灌种子数据。
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
