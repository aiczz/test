"""首页聚合响应（说明书 §9）。"""

from pydantic import BaseModel

from app.schemas.food import FoodBrief


class HomeSeason(BaseModel):
    name: str
    month: int
    region: str | None = None


class HomeHero(BaseModel):
    title: str
    subtitle: str
    image: str | None = None


class MenuBrief(BaseModel):
    id: int
    title: str
    image: str | None = None
    servings: str
    tags: list[str] = []


class HomeResponse(BaseModel):
    """说明书 §9：首页必须同时包含「食材推荐」和「菜单推荐」。

    ★ 刻意不返回价格字段（说明书 §9 明确要求）。
    """

    season: HomeSeason
    hero: HomeHero
    recommended_foods: list[FoodBrief]
    recommended_menus: list[MenuBrief]
    ai_tip: str
