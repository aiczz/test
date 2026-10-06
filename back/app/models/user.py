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
    # ---- 管理员相关 ----
    # 管理员可以封禁其他账号、看用户统计和登录记录
    is_admin: bool = Field(default=False, index=True)
    # 被封禁后不能登录；已经登录的拿着旧 token 也会被拒
    is_banned: bool = Field(default=False, index=True)
    last_login_at: datetime | None = Field(default=None)
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

    # ---- 家庭档案里「会进求解器」的那几项 ----
    #
    # ★ 为什么必须存服务端：这些值原先只活在前端内存里（AppState），
    #   刷新一下页面就回到默认的 3 人 / 45 分钟 —— 用户改了设置、换个页面看
    #   还是 3 人，就是这个原因。约束是求解器的输入，不能只活在一次会话里。
    #
    # ⚠️ 用 JSON 列表而不是逗号拼接：「清淡,少油」这种口味名本身可能含逗号，
    #   拼起来再拆就会出错。SQLModel 的 sa_type=JSON 在 SQLite / PostgreSQL
    #   上都能用。
    diet_preferences: list[str] = Field(default_factory=list, sa_type=JSON)
    tools: list[str] = Field(default_factory=list, sa_type=JSON)
    # 限钠是硬约束开关；烹饪时间上限进的是时间硬筛
    low_sodium: bool = Field(default=True)
    cook_minutes: int = Field(default=45)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column_kwargs={"onupdate": utcnow}
    )
