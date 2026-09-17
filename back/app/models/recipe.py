"""菜谱、配料与步骤（说明书 §7.5 / §7.6 / §7.7）。"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.utils.time import utcnow


class Recipe(SQLModel, table=True):
    __tablename__ = "recipes"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=128)
    image_url: str | None = Field(default=None, max_length=255)
    description: str | None = None
    # 前端首页就是按这个字段筛「每日可用烹饪时间」的，必须是分钟数
    duration_minutes: int = Field(default=30, index=True)
    servings: int = Field(default=3)
    difficulty: str = Field(default="简单", max_length=16)
    category: str | None = Field(default=None, max_length=32)
    season_recommendation: str | None = None
    tips: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column_kwargs={"onupdate": utcnow}
    )


class RecipeIngredient(SQLModel, table=True):
    __tablename__ = "recipe_ingredients"

    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipes.id", index=True)
    # 可以指向食材库，也可以是自由文本配料（比如"盐 适量"）
    food_id: int | None = Field(default=None, foreign_key="foods.id", index=True)
    ingredient_name: str = Field(max_length=64)
    amount: float | None = Field(default=None)
    unit: str | None = Field(default=None, max_length=16)
    is_required: bool = Field(default=True)
    # 购物清单按这个字段分组（蔬菜 / 肉蛋 / 调味 …）
    category: str | None = Field(default=None, max_length=32)


class RecipeStep(SQLModel, table=True):
    __tablename__ = "recipe_steps"

    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipes.id", index=True)
    step_no: int
    title: str | None = Field(default=None, max_length=64)
    description: str
    image_url: str | None = Field(default=None, max_length=255)
