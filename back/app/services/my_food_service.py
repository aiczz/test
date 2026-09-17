"""我的现有食材业务逻辑（说明书 §13 / §14）。"""

from fastapi import HTTPException, status
from sqlmodel import Session

from app.models.food import Food
from app.models.my_food import MyFood
from app.repositories import food_repository, my_food_repository, recipe_repository
from app.schemas.my_food import (
    MyFoodCreate,
    MyFoodPublic,
    MyFoodUpdate,
    RecommendByFoodsRequest,
    RecommendByFoodsResponse,
)
from app.services import recipe_service


def _to_public(item: MyFood, food: Food | None) -> MyFoodPublic:
    return MyFoodPublic(
        id=item.id,
        food_id=item.food_id,
        # 不在食材库里的东西用用户自己写的名字
        name=food.name if food else (item.custom_name or "未知食材"),
        image=food.image_url if food else None,
        category=food.category if food else None,
        amount=item.amount,
        unit=item.unit,
        expire_hint=item.expire_hint,
        created_at=item.created_at,
    )


def _food_of(session: Session, item: MyFood) -> Food | None:
    return food_repository.get(session, item.food_id) if item.food_id else None


def list_items(session: Session, user_id: int) -> list[MyFoodPublic]:
    return [
        _to_public(item, _food_of(session, item))
        for item in my_food_repository.list_for_user(session, user_id)
    ]


def add_item(
    session: Session, user_id: int, payload: MyFoodCreate
) -> MyFoodPublic:
    if not payload.has_target():
        raise HTTPException(
            # starlette 新版把 UNPROCESSABLE_ENTITY 改名成 UNPROCESSABLE_CONTENT
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="必须指定 food_id 或 custom_name",
        )

    if payload.food_id is not None:
        food = food_repository.get(session, payload.food_id)
        if food is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="食材不存在"
            )
        # 同一种食材只留一条记录，重复添加就累加数量 ——
        # 不然「我的食材」里会出现三行莲藕。
        existing = my_food_repository.find_by_food(
            session, user_id, payload.food_id
        )
        if existing is not None:
            existing.amount += payload.amount
            if payload.expire_hint:
                existing.expire_hint = payload.expire_hint
            return _to_public(my_food_repository.save(session, existing), food)

    item = MyFood(
        user_id=user_id,
        food_id=payload.food_id,
        custom_name=payload.custom_name,
        amount=payload.amount,
        unit=payload.unit,
        expire_hint=payload.expire_hint,
    )
    saved = my_food_repository.add(session, item)
    return _to_public(saved, _food_of(session, saved))


def update_item(
    session: Session, user_id: int, item_id: int, payload: MyFoodUpdate
) -> MyFoodPublic:
    item = my_food_repository.get_for_user(session, item_id, user_id)
    if item is None:
        # 别人的记录同样返回 404 —— 不泄露「这条记录存在」
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="库存记录不存在"
        )

    if payload.amount is not None:
        item.amount = payload.amount
    if payload.unit is not None:
        item.unit = payload.unit
    if payload.expire_hint is not None:
        item.expire_hint = payload.expire_hint

    saved = my_food_repository.save(session, item)
    return _to_public(saved, _food_of(session, saved))


def remove_item(session: Session, user_id: int, item_id: int) -> None:
    item = my_food_repository.get_for_user(session, item_id, user_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="库存记录不存在"
        )
    my_food_repository.delete(session, item)


def recommend_by_foods(
    session: Session,
    user_id: int | None,
    payload: RecommendByFoodsRequest,
) -> RecommendByFoodsResponse:
    """说明书 §14：按现有食材推荐菜谱。

    ★ 纯规则匹配，不调用大模型 —— 说明书 §14 明确说「第一版可以先用规则匹配」。
      规则：找出用得上这些食材的菜谱 → 按命中食材数降序 → 算出还缺什么主料。
    """
    food_ids = payload.food_ids
    if not food_ids:
        if user_id is None:
            return RecommendByFoodsResponse()
        food_ids = [
            item.food_id
            for item in my_food_repository.list_for_user(session, user_id)
            if item.food_id
        ]

    have = set(food_ids)
    if not have:
        return RecommendByFoodsResponse()

    # 候选：任意一个已有食材能用上的菜谱
    candidates: dict[int, object] = {}
    for food_id in have:
        for recipe in recipe_repository.list_by_food(session, food_id, limit=50):
            candidates[recipe.id] = recipe

    ingredients_cache = {
        recipe_id: recipe_repository.list_ingredients(session, recipe_id)
        for recipe_id in candidates
    }

    def hit_count(recipe_id: int) -> int:
        return sum(
            1 for i in ingredients_cache[recipe_id] if i.food_id in have
        )

    # 命中越多越靠前；同样命中数时，快的排前面
    ordered = sorted(
        candidates.values(),
        key=lambda r: (-hit_count(r.id), r.duration_minutes),
    )
    top = ordered[:3]

    missing: list[str] = []
    seen: set[str] = set()
    for recipe in top:
        for ingredient in ingredients_cache[recipe.id]:
            if (
                ingredient.food_id is not None
                and ingredient.food_id not in have
                and ingredient.ingredient_name not in seen
            ):
                missing.append(ingredient.ingredient_name)
                seen.add(ingredient.ingredient_name)

    return RecommendByFoodsResponse(
        recommended_recipes=[recipe_service.to_brief(r) for r in top],
        missing_ingredients=missing,
    )
