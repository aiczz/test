"""食材数据访问（说明书 §5.3）。"""

from sqlmodel import Session, col, func, select

from app.models.food import Food, FoodSeason


def list_foods(
    session: Session,
    *,
    category: str | None = None,
    keyword: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Food], int]:
    """返回 (当页数据, 总数)。"""
    conditions = [col(Food.is_active).is_(True)]
    if category:
        conditions.append(Food.category == category)
    if keyword:
        conditions.append(col(Food.name).like(f"%{keyword}%"))

    total = session.exec(
        select(func.count()).select_from(Food).where(*conditions)
    ).one()

    rows = session.exec(
        select(Food)
        .where(*conditions)
        .order_by(col(Food.id))
        .offset(offset)
        .limit(limit)
    ).all()
    return list(rows), int(total)


def get(session: Session, food_id: int) -> Food | None:
    return session.get(Food, food_id)


def get_season(session: Session, food_id: int) -> FoodSeason | None:
    return session.exec(
        select(FoodSeason).where(FoodSeason.food_id == food_id)
    ).first()


def list_seasonal(
    session: Session,
    *,
    month: int,
    limit: int = 10,
) -> list[tuple[Food, FoodSeason]]:
    """当月的时令食材，按应季程度降序。

    ⚠️ 目前只处理 start_month <= month <= end_month 的普通区间。
       「11 月到次年 2 月」这种跨年区间需要另外判断（说明书里的数据暂时没有），
       真要支持时在这里补一个 OR 分支即可。
    """
    statement = (
        select(Food, FoodSeason)
        .join(FoodSeason, col(FoodSeason.food_id) == col(Food.id))
        .where(col(Food.is_active).is_(True))
        .where(FoodSeason.start_month <= month)
        .where(FoodSeason.end_month >= month)
        .order_by(col(FoodSeason.season_score).desc())
        .limit(limit)
    )
    return [(food, season) for food, season in session.exec(statement).all()]


def list_all(session: Session) -> list[Food]:
    return list(session.exec(select(Food).order_by(col(Food.id))).all())
