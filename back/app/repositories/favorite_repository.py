"""收藏数据访问（说明书 §7.8）。"""

from sqlmodel import Session, col, select

from app.models.favorite import Favorite
from app.models.recipe import Recipe


def _find(session: Session, user_id: int, recipe_id: int) -> Favorite | None:
    return session.exec(
        select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.recipe_id == recipe_id,
        )
    ).first()


def is_favorite(session: Session, user_id: int, recipe_id: int) -> bool:
    return _find(session, user_id, recipe_id) is not None


def add(session: Session, user_id: int, recipe_id: int) -> Favorite:
    """重复收藏不报错，直接返回已有记录（表上有联合唯一约束）。"""
    existing = _find(session, user_id, recipe_id)
    if existing is not None:
        return existing
    favorite = Favorite(user_id=user_id, recipe_id=recipe_id)
    session.add(favorite)
    session.commit()
    session.refresh(favorite)
    return favorite


def remove(session: Session, user_id: int, recipe_id: int) -> bool:
    existing = _find(session, user_id, recipe_id)
    if existing is None:
        return False
    session.delete(existing)
    session.commit()
    return True


def list_recipes(session: Session, user_id: int) -> list[Recipe]:
    """最近收藏的排前面。

    ⚠️ 这里必须 join Favorite 才能按收藏时间排序。之前写成
       `select(Recipe).where(...).order_by(Favorite.id)` —— FROM 是 recipes
       却在 ORDER BY 里引用 favorites.id，SQLite 直接报
       "no such column: favorites.id"。
    """
    return list(
        session.exec(
            select(Recipe)
            .join(Favorite, col(Favorite.recipe_id) == col(Recipe.id))
            .where(Favorite.user_id == user_id)
            .order_by(col(Favorite.created_at).desc())
        ).all()
    )
