"""菜单方案与条目（说明书 §7.10 / §7.11）。

plan_type: today / three_day / custom
meal_type: breakfast / lunch / dinner
source:    manual / ai
"""

from datetime import date, datetime

from sqlmodel import Field, SQLModel

from app.utils.time import utcnow


class MenuPlan(SQLModel, table=True):
    __tablename__ = "menu_plans"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str = Field(default="今日菜单", max_length=64)
    plan_type: str = Field(default="today", max_length=16)
    people: int = Field(default=3)
    start_date: date | None = Field(default=None)
    days: int = Field(default=1)
    source: str = Field(default="manual", max_length=16)
    created_at: datetime = Field(default_factory=utcnow)


class MenuPlanItem(SQLModel, table=True):
    __tablename__ = "menu_plan_items"

    id: int | None = Field(default=None, primary_key=True)
    menu_plan_id: int = Field(foreign_key="menu_plans.id", index=True)
    # 第几天（0 开始），对应前端的三日菜单
    day_index: int = Field(default=0)
    meal_type: str = Field(default="dinner", max_length=16)
    recipe_id: int = Field(foreign_key="recipes.id", index=True)
    sort_order: int = Field(default=0)
