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
    created_at: datetime
