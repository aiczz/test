"""购物清单与条目（说明书 §7.12 / §7.13）。"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.utils.time import utcnow


class ShoppingList(SQLModel, table=True):
    __tablename__ = "shopping_lists"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    # 可以由菜单生成，也可以独立存在
    menu_plan_id: int | None = Field(
        default=None, foreign_key="menu_plans.id", index=True
    )
    title: str = Field(default="购物清单", max_length=64)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column_kwargs={"onupdate": utcnow}
    )


class ShoppingItem(SQLModel, table=True):
    __tablename__ = "shopping_items"

    id: int | None = Field(default=None, primary_key=True)
    shopping_list_id: int = Field(foreign_key="shopping_lists.id", index=True)
    food_id: int | None = Field(default=None, index=True)
    # 冗余存名字：食材库改了也不影响历史清单
    name: str = Field(max_length=64)
    amount: float = Field(default=1)
    unit: str = Field(default="份", max_length=16)
    category: str = Field(default="其他", max_length=32)
    checked: bool = Field(default=False)
