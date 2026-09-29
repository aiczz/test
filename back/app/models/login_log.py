"""登录日志（管理员用来「监听新账号登录」）。

每次调用 /api/auth/login 都记一条 —— 成功和失败都记。
失败也记是有意的：刷密码的行为在日志里一眼能看出来。
"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.utils.time import utcnow


class LoginLog(SQLModel, table=True):
    __tablename__ = "login_logs"

    id: int | None = Field(default=None, primary_key=True)
    # 用户名打错时用户不存在，所以 user_id 可空 —— 但 username 一定要留
    user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    username: str = Field(index=True, max_length=64)
    success: bool = Field(default=False, index=True)
    ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=255)
    # 失败原因，如「用户名或密码不正确」「账号已被封禁」
    detail: str | None = Field(default=None, max_length=128)
    created_at: datetime = Field(default_factory=utcnow, index=True)
