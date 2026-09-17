"""菜谱相关响应（说明书 §11）。"""

from pydantic import BaseModel


class IngredientPublic(BaseModel):
    name: str
    amount: str | None = None
    unit: str | None = None
    category: str | None = None
    food_id: int | None = None


class StepPublic(BaseModel):
    step_no: int
    title: str | None = None
    description: str
    image: str | None = None


class RecipeBrief(BaseModel):
    """列表 / 首页用的精简菜谱。"""

    id: int
    name: str
    image: str | None = None
    description: str | None = None
    # ★ 前端首页「按你的条件能做」就是按这个字段筛每日可用烹饪时间的
    duration_minutes: int
    # 响应里是文案（"3人份"），不是数字
    servings: str
    difficulty: str
    tags: list[str] = []


class RecipeDetail(RecipeBrief):
    ingredients: list[IngredientPublic] = []
    steps: list[StepPublic] = []
    tips: list[str] = []
    is_favorite: bool = False
