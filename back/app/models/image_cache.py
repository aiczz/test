"""持久化图片状态和每日生成额度，独立于导入的内容库。"""
from sqlmodel import Field, SQLModel


class ImageCache(SQLModel, table=True):
    __tablename__ = "image_cache"
    key: str = Field(primary_key=True, max_length=64)
    kind: str
    name: str
    status: str = "pending"
    source: str = "generated"
    filename: str = ""
    attempts: int = 0
    updated_at: float = 0
    retry_at: float = 0
    error: str = ""
    model: str = ""


class ImageBudget(SQLModel, table=True):
    __tablename__ = "image_generation_budget"
    day: str = Field(primary_key=True)
    used: int = 0
