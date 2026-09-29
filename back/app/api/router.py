"""汇总所有业务路由（说明书 §4）。

新增一组接口时，在这里 include 一次就够了。

⚠️ 路由顺序有意义：`/foods/seasonal` 这类固定路径必须在 `/foods/{id}`
   之前注册，否则会被动态段吞掉。
"""

from fastapi import APIRouter

from app.api.routes import (
    admin,
    ai,
    auth,
    favorites,
    foods,
    home,
    menus,
    my_foods,
    profile,
    recipes,
    shopping,
)

api_router = APIRouter()

api_router.include_router(home.router)
api_router.include_router(foods.router)
api_router.include_router(recipes.router)
api_router.include_router(auth.router)
api_router.include_router(my_foods.router)
api_router.include_router(favorites.router)
api_router.include_router(menus.router)
api_router.include_router(shopping.router)
api_router.include_router(ai.router)
api_router.include_router(profile.router)
api_router.include_router(admin.router)
