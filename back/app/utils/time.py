"""时间工具。

统一用 UTC 存库，避免 SQLite / PostgreSQL 之间时区表现不一致。
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
