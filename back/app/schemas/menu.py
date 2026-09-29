"""菜单（说明书 §16 / §17）。"""

from pydantic import BaseModel, Field

from app.schemas.recipe import RecipeBrief


class TodayMenuGenerateRequest(BaseModel):
    people: int = Field(default=3, ge=1, le=20)
    meal_types: list[str] = Field(
        default_factory=lambda: ["breakfast", "lunch", "dinner"]
    )
    preferences: list[str] = Field(default_factory=list)


class MenuPlanRequest(BaseModel):
    days: int = Field(default=3, ge=1, le=7)
    people: int = Field(default=3, ge=1, le=20)
    preferences: list[str] = Field(default_factory=list)


class MenuMeals(BaseModel):
    """今日菜单的三餐（说明书 §16 的 meals 字段）。"""

    breakfast: list[RecipeBrief] = []
    lunch: list[RecipeBrief] = []
    dinner: list[RecipeBrief] = []


class TodayMenuResponse(BaseModel):
    id: int
    title: str
    people: int
    meals: MenuMeals


class MenuDay(BaseModel):
    day_index: int
    label: str
    recipes: list[RecipeBrief] = []


class MenuPlanResponse(BaseModel):
    id: int
    title: str
    people: int
    days: list[MenuDay] = []
