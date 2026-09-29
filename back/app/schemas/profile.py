"""个人偏好（说明书 §12 里「需要登录」的个人偏好）。"""

from pydantic import BaseModel, Field


class PreferencePublic(BaseModel):
    taste: str | None = None
    diet_style: str | None = None
    avoid_foods: list[str] = []
    favorite_categories: list[str] = []
    # 家庭人数存在 users 表上，但对前端来说和偏好是一组设置
    family_size: int = 3


class PreferenceUpdate(BaseModel):
    taste: str | None = None
    diet_style: str | None = None
    avoid_foods: list[str] | None = None
    favorite_categories: list[str] | None = None
    family_size: int | None = Field(default=None, ge=1, le=20)
