"""我的现有食材（说明书 §13 / §14）。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.recipe import RecipeBrief


class MyFoodCreate(BaseModel):
    food_id: int | None = Field(default=None, description="指向食材库")
    custom_name: str | None = Field(
        default=None, max_length=64, description="不在食材库里的东西，自己写名字"
    )
    amount: float = Field(default=1, gt=0)
    unit: str = Field(default="份", max_length=16)
    expire_hint: str | None = Field(
        default=None, max_length=64, description="如「周四到期」"
    )

    def has_target(self) -> bool:
        """必须至少指明是哪个食材 —— 要么给 food_id，要么给 custom_name。"""
        return self.food_id is not None or bool(self.custom_name)


class MyFoodUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=16)
    expire_hint: str | None = Field(default=None, max_length=64)


class MyFoodPublic(BaseModel):
    id: int
    food_id: int | None = None
    name: str
    image: str | None = None
    category: str | None = None
    amount: float
    unit: str
    expire_hint: str | None = None
    created_at: datetime


class RecommendByFoodsRequest(BaseModel):
    """说明书 §14。food_ids 留空时用当前用户的库存。"""

    food_ids: list[int] | None = None
    people: int = Field(default=3, ge=1, le=20)


class RecommendByFoodsResponse(BaseModel):
    recommended_recipes: list[RecipeBrief] = []
    # 做这些菜还缺什么（说明书 §14 的 missing_ingredients）
    missing_ingredients: list[str] = []
