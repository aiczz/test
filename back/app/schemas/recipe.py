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
    # 这个时长是不是估的？清洗库的 dishes 没有时长列，只能从做法文本里抽
    # （「小火炖 30 分钟」）；抽不到就只能估。界面据此显示「约 30 分钟」，
    # 不把一个估出来的数字说得像真的。
    duration_estimated: bool = False
    # 响应里是文案（"3人份"），不是数字。
    # ⚠️ 可能是 null：清洗库的 dishes 没有份量列，这时前端不要显示这一项，
    #    而不是拿一个默认的「3人份」顶上（那会让用户以为改了人数没生效）。
    servings: str | None = None
    difficulty: str
    tags: list[str] = []


class RecipeDetail(RecipeBrief):
    ingredients: list[IngredientPublic] = []
    steps: list[StepPublic] = []
    tips: list[str] = []
    is_favorite: bool = False


class RecipeTag(BaseModel):
    """一个可点击的分类。

    `count` 是这个分类下的菜品数 —— 前端直接显示，用户点之前就知道有没有菜，
    不会出现「点进去是空的」。
    """

    name: str
    count: int


class RecipeTagGroup(BaseModel):
    """菜谱分类筛选区的一个分组（如「做法」「主要食材」）。"""

    group: str
    tags: list[RecipeTag]
