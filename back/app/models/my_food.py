"""我的现有食材（说明书 §7.9）。"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.utils.time import utcnow


class MyFood(SQLModel, table=True):
    __tablename__ = "my_foods"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    # 指向食材库；也允许只填 custom_name（用户自己写的东西）
    food_id: int | None = Field(default=None, foreign_key="foods.id", index=True)
    custom_name: str | None = Field(default=None, max_length=64)
    amount: float = Field(default=1)
    unit: str = Field(default="份", max_length=16)
    # 前端「菠菜周四到期」这类提示
    expire_hint: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column_kwargs={"onupdate": utcnow}
    )
