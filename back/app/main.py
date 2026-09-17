"""食时 API 入口。

本地启动：
    cd back
    python -m uvicorn app.main:app --reload --port 8000

接口文档（自动生成，答辩时可以打开给评委看）：
    http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.api.router import api_router
from app.core.config import settings
from app.core.database import create_db_and_tables, engine
from app.data.seed import seed_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 建表 + 灌种子数据。两个都是幂等的，反复重启不会重复写。
    create_db_and_tables()
    with Session(engine) as session:
        seed_all(session)
    yield


app = FastAPI(
    title=settings.app_name,
    description="食时 · 顺应时令的智慧饮食助手 —— 后端接口",
    version="0.1.0",
    lifespan=lifespan,
)

# Flutter Web 跑在另一个端口（flutter run -d chrome 每次端口都不同），
# 不显式放行的话浏览器会直接拦掉所有请求。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/api/health", tags=["运维"], summary="健康检查")
def health() -> dict[str, str]:
    return {"status": "ok"}
