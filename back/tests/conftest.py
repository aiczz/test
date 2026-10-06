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
from app.services import weather_service

# 本机生产配置可以强制 CONTENT_MODE=compact；测试同时覆盖旧演示表和六表适配器，
# 因此必须按每个临时数据库的实际表结构自动识别。
settings.content_mode = "auto"


@pytest.fixture(autouse=True)
def _hermetic_externals():
    """★ 测试绝不碰网络。

    开发机上 back/.env 里配了真的 AI_API_KEY，如果不隔离，
    `pytest` 会真的去调 DeepSeek：慢、要花钱、断网就红。
    这里强制关掉 AI 与天气，让测试只验证「没有外部服务时」的确定性行为 ——
    这恰好也是线上没配 Key / 断网时的降级路径。
    """
    saved = (
        settings.ai_enabled,
        settings.ai_api_key,
        settings.weather_enabled,
    )
    settings.ai_enabled = False
    settings.ai_api_key = ""
    settings.weather_enabled = False
    weather_service.reset_cache()
    try:
        yield
    finally:
        (
            settings.ai_enabled,
            settings.ai_api_key,
            settings.weather_enabled,
        ) = saved
        weather_service.reset_cache()


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
