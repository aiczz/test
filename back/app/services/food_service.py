"""食材业务逻辑（说明书 §10）。"""

from sqlmodel import Session

from app.models.food import Food, FoodSeason
from app.repositories import food_repository, recipe_repository
from app.schemas.food import FoodBrief, FoodDetail, FoodFeatures, SeasonInfo
from app.services import recipe_service


def to_brief(food: Food, season: FoodSeason | None = None) -> FoodBrief:
    return FoodBrief(
        id=food.id,
        name=food.name,
        image=food.image_url,
        category=food.category,
        season_score=season.season_score if season else 0,
        tags=list(food.tags or []),
    )


def list_foods(
    session: Session,
    *,
    category: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[FoodBrief], int]:
    offset = (page - 1) * page_size
    rows, total = food_repository.list_foods(
        session,
        category=category,
        keyword=keyword,
        offset=offset,
        limit=page_size,
    )
    items = [to_brief(f, food_repository.get_season(session, f.id)) for f in rows]
    return items, total


def list_seasonal(
    session: Session, *, month: int, limit: int = 10
) -> list[FoodBrief]:
    return [
        to_brief(food, season)
        for food, season in food_repository.list_seasonal(
            session, month=month, limit=limit
        )
    ]


def get_detail(session: Session, food_id: int) -> FoodDetail | None:
    food = food_repository.get(session, food_id)
    if food is None or not food.is_active:
        return None

    season = food_repository.get_season(session, food_id)
    recipes = recipe_repository.list_by_food(session, food_id)

    return FoodDetail(
        id=food.id,
        name=food.name,
        image=food.image_url,
        category=food.category,
        description=food.description,
        season=SeasonInfo(
            name=season.season_name if season else None,
            score=season.season_score if season else 0,
            description=season.description if season else None,
        ),
        tags=list(food.tags or []),
        features=FoodFeatures(
            # 说明书 §10.3 的 features 里有两项库里没有对应列，给个通用值
            suitable_for="适合大多数人群",
            common_methods=food.common_methods,
            texture=food.texture,
        ),
        recommended_recipes=[recipe_service.to_brief(r) for r in recipes],
    )
