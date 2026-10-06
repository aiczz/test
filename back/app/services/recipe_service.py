"""菜谱业务逻辑（说明书 §11）。"""

from sqlmodel import Session

from app.core.database import uses_compact_catalog
from app.models.recipe import Recipe
from app.repositories import (
    compact_catalog_repository,
    favorite_repository,
    recipe_repository,
)
from app.schemas.recipe import (
    IngredientPublic,
    RecipeBrief,
    RecipeDetail,
    StepPublic,
)


def _fmt_amount(value: float | None) -> str | None:
    """500.0 → "500"；1.5 → "1.5"；None → None（"适量"这类没有数值）。"""
    if value is None:
        return None
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def to_brief(recipe: Recipe) -> RecipeBrief:
    return RecipeBrief(
        id=recipe.id,
        name=recipe.name,
        image=recipe.image_url,
        description=recipe.description,
        duration_minutes=recipe.duration_minutes,
        # 旧演示表（recipes）真的有时长列 → False（有依据）；
        # 清洗库（dishes）没有时长列 → 由评分层按「做法文本里抽没抽到」回填
        duration_estimated=bool(getattr(recipe, "duration_estimated", False)),
        servings=f"{recipe.servings}人份",
        difficulty=recipe.difficulty,
        tags=list(recipe.tags or []),
    )


def list_recipes(
    session: Session,
    *,
    category: str | None = None,
    season: str | None = None,
    difficulty: str | None = None,
    max_duration: int | None = None,
    keyword: str | None = None,
    tag: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[RecipeBrief], int]:
    rows, total = recipe_repository.list_recipes(
        session,
        category=category,
        season=season,
        difficulty=difficulty,
        max_duration=max_duration,
        keyword=keyword,
        tag=tag,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return [to_brief(r) for r in rows], total


def tag_groups(
    session: Session,
) -> list[tuple[str, list[tuple[str, int]]]]:
    """菜谱分类筛选区（分组 + 每个分类的菜品数）。

    分类名和 `app.data.dish_tags` 里归一化用的是同一套常量，
    所以「点分类能筛到菜」和「卡片上显示的标签」天然一致。
    """
    if uses_compact_catalog(session.get_bind()):
        return compact_catalog_repository.tag_groups_with_counts(session)
    return []


def search(
    session: Session, keyword: str, *, page: int = 1, page_size: int = 20
) -> tuple[list[RecipeBrief], int]:
    rows, total = recipe_repository.search(
        session, keyword, offset=(page - 1) * page_size, limit=page_size
    )
    return [to_brief(r) for r in rows], total


def get_detail(
    session: Session, recipe_id: int, *, user_id: int | None = None
) -> RecipeDetail | None:
    recipe = recipe_repository.get(session, recipe_id)
    if recipe is None:
        return None

    ingredients = [
        IngredientPublic(
            name=item.ingredient_name,
            amount=_fmt_amount(item.amount),
            unit=item.unit,
            category=item.category,
            food_id=item.food_id,
        )
        for item in recipe_repository.list_ingredients(session, recipe_id)
    ]

    steps = [
        StepPublic(
            step_no=step.step_no,
            title=step.title,
            description=step.description,
            image=step.image_url,
        )
        for step in recipe_repository.list_steps(session, recipe_id)
    ]

    return RecipeDetail(
        **to_brief(recipe).model_dump(),
        ingredients=ingredients,
        steps=steps,
        tips=[recipe.tips] if recipe.tips else [],
        # 未登录时 is_favorite 一律 false，而不是报错 —— 菜谱详情是公开接口
        is_favorite=(
            favorite_repository.is_favorite(session, user_id, recipe_id)
            if user_id
            else False
        ),
    )
