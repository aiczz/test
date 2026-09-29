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
    servings: int = 3
    difficulty: str = "简单"
    category: str | None = None
    season_recommendation: str | None = None
    tips: str | None = None
    tags: list[str] = field(default_factory=list)
    instruction_text: str | None = None


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
