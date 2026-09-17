"""购物清单（说明书 §19）。"""

from pydantic import BaseModel


class GenerateShoppingListRequest(BaseModel):
    menu_plan_id: int
    # 说明书 §19 的流程里「扣除用户已有食材」标了"可选"，默认不扣。
    subtract_my_foods: bool = False


class ShoppingItemPublic(BaseModel):
    id: int
    food_id: int | None = None
    name: str
    amount: float
    unit: str
    category: str
    checked: bool


class ShoppingCategoryGroup(BaseModel):
    category: str
    items: list[ShoppingItemPublic] = []


class ShoppingListResponse(BaseModel):
    id: int
    title: str
    menu_plan_id: int | None = None
    categories: list[ShoppingCategoryGroup] = []
    total_items: int = 0


class ShoppingItemUpdate(BaseModel):
    checked: bool
