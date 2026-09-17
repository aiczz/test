"""所有表模型。

集中 import 一次，保证 `SQLModel.metadata` 里注册了全部表 ——
`create_all()` 靠的就是它。
"""

from app.models.favorite import Favorite
from app.models.food import Food, FoodSeason
from app.models.menu import MenuPlan, MenuPlanItem
from app.models.my_food import MyFood
from app.models.recipe import Recipe, RecipeIngredient, RecipeStep
from app.models.shopping import ShoppingItem, ShoppingList
from app.models.user import User, UserPreference

__all__ = [
    "Favorite",
    "Food",
    "FoodSeason",
    "MenuPlan",
    "MenuPlanItem",
    "MyFood",
    "Recipe",
    "RecipeIngredient",
    "RecipeStep",
    "ShoppingItem",
    "ShoppingList",
    "User",
    "UserPreference",
]
