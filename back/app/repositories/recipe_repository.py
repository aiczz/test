"""菜谱数据访问（说明书 §5.3）。"""

from sqlmodel import Session, col, func, select

from app.core.database import uses_compact_catalog
from app.models.recipe import Recipe, RecipeIngredient, RecipeStep
from app.repositories import compact_catalog_repository as compact


def _conditions(
    *,
    category: str | None = None,
    season: str | None = None,
    difficulty: str | None = None,
    max_duration: int | None = None,
    keyword: str | None = None,
) -> list:
    conditions: list = []
    if category:
        conditions.append(Recipe.category == category)
    if season:
        conditions.append(Recipe.season_recommendation == season)
    if difficulty:
        conditions.append(Recipe.difficulty == difficulty)
    if max_duration:
        # ★ 前端「每日可用烹饪时间」就是靠这个条件做硬筛的
        conditions.append(Recipe.duration_minutes <= max_duration)
    if keyword:
        conditions.append(col(Recipe.name).like(f"%{keyword}%"))
    return conditions


def list_recipes(
    session: Session,
    *,
    category: str | None = None,
    season: str | None = None,
    difficulty: str | None = None,
    max_duration: int | None = None,
    keyword: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Recipe], int]:
    if uses_compact_catalog(session.get_bind()):
        return compact.list_recipes(
            session,
            category=category,
            season=season,
            difficulty=difficulty,
            max_duration=max_duration,
            keyword=keyword,
            offset=offset,
            limit=limit,
        )
    conditions = _conditions(
        category=category,
        season=season,
        difficulty=difficulty,
        max_duration=max_duration,
        keyword=keyword,
    )

    total = session.exec(
        select(func.count()).select_from(Recipe).where(*conditions)
    ).one()

    rows = session.exec(
        select(Recipe)
        .where(*conditions)
        .order_by(col(Recipe.id))
        .offset(offset)
        .limit(limit)
    ).all()
    return list(rows), int(total)


def search(
    session: Session, keyword: str, *, offset: int = 0, limit: int = 20
) -> tuple[list[Recipe], int]:
    """菜名 或 配料名 命中即可（说明书 §11.2）。"""
    if uses_compact_catalog(session.get_bind()):
        return compact.search_recipes(
            session, keyword, offset=offset, limit=limit
        )
    like = f"%{keyword}%"
    # 配料命中的菜谱 id 子查询
    by_ingredient = select(RecipeIngredient.recipe_id).where(
        col(RecipeIngredient.ingredient_name).like(like)
    )
    condition = col(Recipe.name).like(like) | col(Recipe.id).in_(by_ingredient)

    total = session.exec(
        select(func.count()).select_from(Recipe).where(condition)
    ).one()

    rows = session.exec(
        select(Recipe)
        .where(condition)
        .order_by(col(Recipe.id))
        .offset(offset)
        .limit(limit)
    ).all()
    return list(rows), int(total)


def get(session: Session, recipe_id: int) -> Recipe | None:
    if uses_compact_catalog(session.get_bind()):
        return compact.get_recipe(session, recipe_id)
    return session.get(Recipe, recipe_id)


def list_ingredients(session: Session, recipe_id: int) -> list[RecipeIngredient]:
    if uses_compact_catalog(session.get_bind()):
        return compact.list_recipe_ingredients(session, recipe_id)
    return list(
        session.exec(
            select(RecipeIngredient)
            .where(RecipeIngredient.recipe_id == recipe_id)
            .order_by(col(RecipeIngredient.id))
        ).all()
    )


def list_steps(session: Session, recipe_id: int) -> list[RecipeStep]:
    if uses_compact_catalog(session.get_bind()):
        return compact.list_recipe_steps(session, recipe_id)
    return list(
        session.exec(
            select(RecipeStep)
            .where(RecipeStep.recipe_id == recipe_id)
            .order_by(col(RecipeStep.step_no))
        ).all()
    )


def list_by_food(session: Session, food_id: int, *, limit: int = 5) -> list[Recipe]:
    """某食材能做的菜谱 —— 食材详情页的 recommended_recipes。"""
    if uses_compact_catalog(session.get_bind()):
        return compact.list_recipes_by_food(session, food_id, limit=limit)
    subquery = select(RecipeIngredient.recipe_id).where(
        RecipeIngredient.food_id == food_id
    )
    return list(
        session.exec(
            select(Recipe).where(col(Recipe.id).in_(subquery)).limit(limit)
        ).all()
    )


def list_by_ids(session: Session, recipe_ids: list[int]) -> list[Recipe]:
    if not recipe_ids:
        return []
    if uses_compact_catalog(session.get_bind()):
        return compact.list_recipes_by_ids(session, recipe_ids)
    return list(
        session.exec(select(Recipe).where(col(Recipe.id).in_(recipe_ids))).all()
    )
