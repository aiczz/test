"""用户与偏好（说明书 §7.1 / §7.2）。"""

from datetime import datetime

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

from app.utils.time import utcnow


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=64)
    email: str | None = Field(default=None, index=True, max_length=128)
    # 只存哈希，永远不存明文（说明书 §12）
    password_hash: str = Field(max_length=255)
    nickname: str | None = Field(default=None, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=255)
    # 用于默认菜单人数
    family_size: int = Field(default=3)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column_kwargs={"onupdate": utcnow}
    )


class UserPreference(SQLModel, table=True):
    __tablename__ = "user_preferences"

    id: int | None = Field(default=None, primary_key=True)
    # 一个用户一条偏好记录
    user_id: int = Field(foreign_key="users.id", index=True, unique=True)
    taste: str | None = Field(default=None, max_length=64)
    diet_style: str | None = Field(default=None, max_length=64)
    # 说明书 §7.2：简单版本中这两个字段可以先用 JSON
    avoid_foods: list[str] = Field(default_factory=list, sa_type=JSON)
    favorite_categories: list[str] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column_kwargs={"onupdate": utcnow}
    )
