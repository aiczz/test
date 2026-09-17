"""汇总所有业务路由（说明书 §4）。

新增一组接口时，在这里 include 一次就够了。
"""

from fastapi import APIRouter

from app.api.routes import auth

api_router = APIRouter()

api_router.include_router(auth.router)
