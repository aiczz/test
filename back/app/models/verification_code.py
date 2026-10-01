"""验证码记录（邮箱 / 手机号通用）。

几个刻意的设计：

- **只存哈希，不存明文**：库里、日志里都不该出现可用的验证码。
  哈希里掺了 SECRET_KEY，拿到库也没法对着 6 位码做彩虹表。
- **每条码是一行，旧码不删**：重发间隔和「每小时上限」都是靠历史行数统计的，
  删了就统计不出来。
- **consumed_at 记录被用掉**：同一条码不能用第二次（防重放）。
- **时间统一用 naive UTC**：SQLite 不保存时区，aware datetime 写进去读出来会变成
  naive，两者直接比较会 TypeError（已实测）。所以这里一律存 naive。
"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.utils.time import utcnow


def naive_utcnow() -> datetime:
    """naive UTC —— 本模块所有时间字段都用它，保证读写与比较口径一致。"""
    return utcnow().replace(tzinfo=None)


class VerificationCode(SQLModel, table=True):
    __tablename__ = "verification_codes"

    id: int | None = Field(default=None, primary_key=True)
    # 邮箱（统一小写）或手机号
    target: str = Field(index=True, max_length=128)
    # register / login
    purpose: str = Field(index=True, max_length=20)
    # 实际用的通道名，排查「码到底发出去没有」时很有用
    channel: str = Field(default="console", max_length=20)
    code_hash: str = Field(max_length=128)
    attempts: int = Field(default=0)
    expires_at: datetime = Field(index=True)
    consumed_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=naive_utcnow, index=True)
