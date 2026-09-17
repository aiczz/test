"""购物清单业务逻辑（说明书 §19）。

流程照说明书：
    读取菜单所有菜谱 → 合并相同食材 → 扣除用户已有食材（可选）
    → 按类别分组 → 生成购物清单
"""

from fastapi import HTTPException, status
from sqlmodel import Session

from app.models.shopping import ShoppingItem, ShoppingList
from app.repositories import (
    menu_repository,
    my_food_repository,
    recipe_repository,
    shopping_repository,
)
from app.schemas.shopping import (
    GenerateShoppingListRequest,
    ShoppingCategoryGroup,
    ShoppingItemPublic,
    ShoppingItemUpdate,
    ShoppingListResponse,
)

# 类别展示顺序。"其他" 兜底放最后。
_CATEGORY_ORDER = ["蔬菜", "肉蛋", "水产", "豆制品", "主食", "调味", "其他"]


def _to_public(item: ShoppingItem) -> ShoppingItemPublic:
    return ShoppingItemPublic(
        id=item.id,
        food_id=item.food_id,
        name=item.name,
        amount=item.amount,
        unit=item.unit,
        category=item.category,
        checked=item.checked,
    )


def _build_response(
    session: Session, shopping_list: ShoppingList
) -> ShoppingListResponse:
    rows = shopping_repository.list_items(session, shopping_list.id)

    grouped: dict[str, list[ShoppingItemPublic]] = {}
    for row in rows:
        grouped.setdefault(row.category or "其他", []).append(_to_public(row))

    def order(category: str) -> int:
        return (
            _CATEGORY_ORDER.index(category)
            if category in _CATEGORY_ORDER
            else len(_CATEGORY_ORDER)
        )

    categories = [
        ShoppingCategoryGroup(category=name, items=grouped[name])
        for name in sorted(grouped, key=order)
    ]

    return ShoppingListResponse(
        id=shopping_list.id,
        title=shopping_list.title,
        menu_plan_id=shopping_list.menu_plan_id,
        categories=categories,
        total_items=len(rows),
    )


def generate(
    session: Session,
    user_id: int,
    payload: GenerateShoppingListRequest,
) -> ShoppingListResponse:
    plan = menu_repository.get_plan(session, payload.menu_plan_id, user_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="菜单不存在"
        )

    plan_items = menu_repository.get_items(session, plan.id)

    # ---- 1. 合并相同食材 ----
    # key 用 (名称, 单位)：同样是"盐"，一个按"克"一个按"适量"不能直接相加
    merged: dict[tuple[str, str], dict] = {}
    for plan_item in plan_items:
        for ingredient in recipe_repository.list_ingredients(
            session, plan_item.recipe_id
        ):
            key = (ingredient.ingredient_name, ingredient.unit or "")
            entry = merged.get(key)
            if entry is None:
                merged[key] = {
                    "food_id": ingredient.food_id,
                    "name": ingredient.ingredient_name,
                    "amount": ingredient.amount,
                    "unit": ingredient.unit or "份",
                    "category": ingredient.category or "其他",
                }
            elif ingredient.amount is not None and entry["amount"] is not None:
                entry["amount"] += ingredient.amount

    # ---- 2. 扣除用户已有食材（可选）----
    if payload.subtract_my_foods:
        owned = {
            item.food_id
            for item in my_food_repository.list_for_user(session, user_id)
            if item.food_id
        }
        merged = {
            key: value
            for key, value in merged.items()
            if value["food_id"] not in owned
        }

    # ---- 3. 落库 ----
    shopping_list = shopping_repository.create_list(
        session,
        ShoppingList(
            user_id=user_id,
            menu_plan_id=plan.id,
            title=f"{plan.title} · 购物清单",
        ),
    )

    shopping_repository.add_items(
        session,
        [
            ShoppingItem(
                shopping_list_id=shopping_list.id,
                food_id=entry["food_id"],
                name=entry["name"],
                # 「适量」这类没有数值，存 0，前端只看 unit
                amount=entry["amount"] if entry["amount"] is not None else 0,
                unit=entry["unit"],
                category=entry["category"],
            )
            for entry in merged.values()
        ],
    )

    return _build_response(session, shopping_list)


def get_latest(session: Session, user_id: int) -> ShoppingListResponse | None:
    shopping_list = shopping_repository.get_latest(session, user_id)
    if shopping_list is None:
        return None
    return _build_response(session, shopping_list)


def update_item(
    session: Session,
    user_id: int,
    item_id: int,
    payload: ShoppingItemUpdate,
) -> ShoppingItemPublic:
    item = shopping_repository.get_item_for_user(session, item_id, user_id)
    if item is None:
        # 别人的条目也返回 404，不泄露存在性
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="清单条目不存在"
        )
    item.checked = payload.checked
    return _to_public(shopping_repository.save_item(session, item))
