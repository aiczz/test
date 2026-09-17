"""食材与时令（说明书 §7.3 / §7.4）。

category 用说明书约定的英文枚举：
    vegetable / fruit / meat_egg / aquatic / soy / grain / seasoning
"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.utils.time import utcnow


class Food(SQLModel, table=True):
    __tablename__ = "foods"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=64)
    category: str = Field(index=True, max_length=32)
    image_url: str | None = Field(default=None, max_length=255)
    description: str | None = None
    nutrition_summary: str | None = None
    texture: str | None = Field(default=None, max_length=64)
    common_methods: str | None = None
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column_kwargs={"onupdate": utcnow}
    )


class FoodSeason(SQLModel, table=True):
    __tablename__ = "food_seasons"

    id: int | None = Field(default=None, primary_key=True)
    food_id: int = Field(foreign_key="foods.id", index=True)
    # local / nearby / national —— 与前端的三档价格来源口径一致
    region: str = Field(default="national", max_length=32)
    start_month: int
    end_month: int
    season_name: str | None = Field(default=None, max_length=32)
    # 应季程度（0-100），注意：这不是价格评分（说明书 §7.4）
    season_score: int = Field(default=80)
    description: str | None = None
