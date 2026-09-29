"""首页聚合业务逻辑（说明书 §9）。"""

from datetime import datetime

from sqlmodel import Session

from app.schemas.home import (
    HomeHero,
    HomeResponse,
    HomeSeason,
    MenuBrief,
)
from app.services import food_service, recipe_service

# 月份 → 季节名。前端顶部那个「秋季 · 9月」的 pill 用的就是它。
_MONTH_TO_SEASON = {
    1: "冬季",
    2: "冬季",
    3: "春季",
    4: "春季",
    5: "春季",
    6: "夏季",
    7: "夏季",
    8: "夏季",
    9: "秋季",
    10: "秋季",
    11: "秋季",
    12: "冬季",
}

_AI_TIP = "先选当季食材，再搭配家常菜单，做饭更轻松。"


def season_name_of(month: int) -> str:
    return _MONTH_TO_SEASON.get(month, "当季")


def build_home(
    session: Session,
    *,
    region: str | None = None,
    month: int | None = None,
    limit: int = 3,
) -> HomeResponse:
    """首页聚合：时令食材 + 菜单推荐。

    ★ 不返回价格字段（说明书 §9 明确要求）。
    """
    current_month = month or datetime.now().month
    season = season_name_of(current_month)

    foods = food_service.list_seasonal(session, month=current_month, limit=limit)

    # 当季优先，不够就退回全部菜谱 —— 首页不能出现空区块
    recipes, _ = recipe_service.list_recipes(
        session, season=season, page=1, page_size=limit
    )
    if not recipes:
        recipes, _ = recipe_service.list_recipes(session, page=1, page_size=limit)

    # ⚠️ 「菜单推荐」是按当季菜谱【动态组合】出来的建议，不是数据库里的实体，
    #    所以 id 固定为 0 —— 前端据此知道这是组合推荐，不是可打开的菜单详情。
    menus: list[MenuBrief] = []
    if recipes:
        menus.append(
            MenuBrief(
                id=0,
                title=f"{season}家常菜单",
                image=recipes[0].image,
                servings=recipes[0].servings,
                tags=["当季推荐", "荤素搭配"],
            )
        )

    hero_image = foods[0].image if foods else (recipes[0].image if recipes else None)

    return HomeResponse(
        season=HomeSeason(name=season, month=current_month, region=region),
        hero=HomeHero(
            title="今日推荐",
            subtitle="应季食材 · 家常菜单 · 轻松安排",
            image=hero_image,
        ),
        recommended_foods=foods,
        recommended_menus=menus,
        ai_tip=_AI_TIP,
    )
