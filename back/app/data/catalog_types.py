"""清洗内容库的只读返回对象。

字段名刻意与旧 ORM 模型保持一致，让业务层无需知道底层来自哪套表。
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class FoodRecord:
    id: int
    name: str
    category: str
    image_url: str | None = None
    description: str | None = None
    nutrition_summary: str | None = None
    texture: str | None = None
    common_methods: str | None = None
    tags: list[str] = field(default_factory=list)
    is_active: bool = True


@dataclass(slots=True)
class FoodSeasonRecord:
    food_id: int
    region: str = "national"
    start_month: int = 1
    end_month: int = 12
    season_name: str | None = None
    season_score: int = 0
    description: str | None = None


@dataclass(slots=True)
class RecipeRecord:
    id: int
    name: str
    image_url: str | None = None
    description: str | None = None
    duration_minutes: int = 30
    # ⚠️ 清洗库的 dishes 表**没有份量列**，所以这里默认 None（= 不知道），
    #    而不是随手写个 3。以前默认 3，于是每一道菜的卡片上都是「3人份」——
    #    用户改了家庭人数，这个数字一动不动（因为它从来就是个常量）。
    #    旧演示表 recipes 有真实的 servings 列，那条路径照常有值。
    servings: int | None = None
    difficulty: str = "简单"
    category: str | None = None
    season_recommendation: str | None = None
    tips: str | None = None
    tags: list[str] = field(default_factory=list)
    instruction_text: str | None = None
    # 这个时长是「估算」还是「有依据」？
    #
    # 清洗库的 dishes 表**没有**烹饪时长列，所以时长只能从做法文本里抽
    # （「小火炖 30 分钟」→ 30）。抽不到就只能按标签数估。
    # 界面据此决定显不显示数字：有依据才显示「约 N 分钟」。
    duration_estimated: bool = True


@dataclass(slots=True)
class RecipeIngredientRecord:
    id: int
    recipe_id: int
    food_id: int | None
    ingredient_name: str
    amount: float | None = None
    unit: str | None = None
    is_required: bool = True
    category: str | None = None


@dataclass(slots=True)
class RecipeStepRecord:
    id: int
    recipe_id: int
    step_no: int
    description: str
    title: str | None = None
    image_url: str | None = None
