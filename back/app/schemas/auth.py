"""认证相关的请求/响应模型（说明书 §12）。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64, description="登录名")
    password: str = Field(min_length=6, max_length=128, description="至少 6 位")
    email: str | None = Field(default=None, max_length=128)
    nickname: str | None = Field(default=None, max_length=64)
    family_size: int = Field(default=3, ge=1, le=20, description="家庭人数")


class LoginRequest(BaseModel):
    username: str
    password: str


class SmsAuthRequest(BaseModel):
    """比赛演示用的手机验证码认证请求。"""

    phone: str = Field(pattern=r"^1\d{10}$", description="11 位中国大陆手机号")
    code: str = Field(min_length=6, max_length=6, description="6 位验证码")


class TokenResponse(BaseModel):
    """说明书的登录响应格式。"""

    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    """对外暴露的用户信息。

    ⚠️ 这里【没有】password_hash —— 用这个模型做 response_model，
       哈希就不可能被序列化出去。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    family_size: int
    # 前端靠这个决定要不要显示「管理员控制台」入口
    is_admin: bool = False
    created_at: datetime
