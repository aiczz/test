"""管理员接口的响应模型。

说明书里没有这一节 —— 这是本次新增的功能（后台管理）。
"""

from datetime import datetime

from pydantic import BaseModel


class AdminStats(BaseModel):
    """管理员首页的统计卡片。"""

    total_users: int
    admin_users: int
    banned_users: int
    new_users_today: int
    total_logins: int
    logins_today: int
    failed_logins_today: int
    # 今天登录成功过的去重用户数 —— 比「登录次数」更能说明活跃度
    active_users_today: int


class AdminUserRow(BaseModel):
    id: int
    username: str
    nickname: str | None = None
    email: str | None = None
    family_size: int
    is_admin: bool
    is_banned: bool
    created_at: datetime
    last_login_at: datetime | None = None
    login_count: int = 0


class LoginLogRow(BaseModel):
    id: int
    user_id: int | None = None
    username: str
    success: bool
    ip: str | None = None
    user_agent: str | None = None
    detail: str | None = None
    created_at: datetime
