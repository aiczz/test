"""食材相关响应（说明书 §10）。"""

from pydantic import BaseModel

from app.schemas.recipe import RecipeBrief


class SeasonInfo(BaseModel):
    name: str | None = None
    score: int = 0
    description: str | None = None


class FoodBrief(BaseModel):
    """列表 / 首页用的精简食材。"""

    id: int
    name: str
    image: str | None = None
    category: str
    # 应季程度，不是价格评分（说明书 §7.4）
    season_score: int = 0
    tags: list[str] = []


class FoodFeatures(BaseModel):
    suitable_for: str | None = None
    common_methods: str | None = None
    texture: str | None = None


class FoodDetail(BaseModel):
    id: int
    name: str
    image: str | None = None
    category: str
    description: str | None = None
    season: SeasonInfo | None = None
    tags: list[str] = []
    features: FoodFeatures
    recommended_recipes: list[RecipeBrief] = []
