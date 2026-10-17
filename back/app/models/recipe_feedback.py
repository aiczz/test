from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel
from app.utils.time import utcnow


class RecipeFeedback(SQLModel, table=True):
    __tablename__ = 'recipe_feedback'
    __table_args__ = (UniqueConstraint('user_id', 'recipe_id', name='uq_recipe_feedback_user_recipe'),)
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key='users.id', index=True)
    recipe_id: int = Field(index=True)
    rating: int
    reason: str | None = Field(default=None, max_length=40)
    updated_at: datetime = Field(default_factory=utcnow)
