"""个人偏好（说明书 §12 里「需要登录」的个人偏好）。

⚠️ 这里返回的是**求解器的输入**，不只是展示信息：
   人数 / 烹饪时间上限 / 限钠 / 口味偏好 / 忌口 / 厨具
   首页推荐、对话助手、配菜都按这套值算。
   所以它必须能存住 —— 只活在前端内存里的话，刷新一次就回默认的 3 人。
"""

from pydantic import BaseModel, Field


class PreferencePublic(BaseModel):
    taste: str | None = None
    diet_style: str | None = None
    avoid_foods: list[str] = []
    favorite_categories: list[str] = []
    # 家庭人数存在 users 表上，但对前端来说和偏好是一组设置
    family_size: int = 3

    # ---- 会进求解器的约束 ----
    preferences: list[str] = []
    tools: list[str] = []
    low_sodium: bool = True
    cook_minutes: int = 45


class PreferenceUpdate(BaseModel):
    taste: str | None = None
    diet_style: str | None = None
    avoid_foods: list[str] | None = None
    favorite_categories: list[str] | None = None
    family_size: int | None = Field(default=None, ge=1, le=20)

    preferences: list[str] | None = None
    tools: list[str] | None = None
    low_sodium: bool | None = None
    cook_minutes: int | None = Field(default=None, ge=5, le=600)
