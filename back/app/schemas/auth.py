"""认证相关的请求/响应模型（说明书 §12）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 只做基本形状校验，不追求 RFC 完备 —— 邮箱真实性由「能不能收到验证码」来证明。
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64, description="登录名")
    password: str = Field(
        min_length=6,
        max_length=128,
        pattern=r"^\d{6,}$",
        description="不少于 6 位的数字密码",
    )
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


class SmsRegisterRequest(SmsAuthRequest):
    """手机号注册：验证码确认手机号，密码用于后续账号密码登录。"""

    password: str = Field(
        min_length=6,
        max_length=128,
        pattern=r"^\d{6,}$",
        description="不少于 6 位的数字密码",
    )


class EmailCodeRequest(BaseModel):
    """请求发送邮箱验证码。"""

    email: str = Field(pattern=_EMAIL_PATTERN, max_length=128)
    purpose: Literal["register", "login"] = "login"


class EmailAuthRequest(BaseModel):
    """邮箱验证码认证请求。"""

    email: str = Field(pattern=_EMAIL_PATTERN, max_length=128)
    code: str = Field(min_length=6, max_length=6, description="6 位验证码")


class EmailRegisterRequest(EmailAuthRequest):
    """邮箱注册：验证码确认邮箱归属，密码用于后续账号密码登录。"""

    password: str = Field(
        min_length=6,
        max_length=128,
        pattern=r"^\d{6,}$",
        description="不少于 6 位的数字密码",
    )


class CodeSentResponse(BaseModel):
    """发码成功的响应。

    ⚠️ 这里【不含】验证码本身 —— 码只能从邮箱里拿到。
    返回 channel 是为了让前端/运维一眼看出是真发了邮件还是只打了日志。
    """

    channel: str = Field(description="实际使用的下发通道：smtp / console")
    expires_in: int = Field(description="有效期（秒）")
    message: str


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
