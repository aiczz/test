"""收藏（说明书 §7.8）。"""

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.utils.time import utcnow


class Favorite(SQLModel, table=True):
    __tablename__ = "favorites"
    # 联合唯一：同一个用户不能重复收藏同一道菜
    __table_args__ = (
        UniqueConstraint("user_id", "recipe_id", name="uq_favorite_user_recipe"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    recipe_id: int = Field(foreign_key="recipes.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
