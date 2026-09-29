"""我的现有食材数据访问（说明书 §7.9）。

★ 所有按 id 查的函数都必须同时带 user_id —— 只查 id 的话，
  用户 A 就能改用户 B 的库存（越权）。
"""

from sqlmodel import Session, col, select

from app.models.my_food import MyFood


def list_for_user(session: Session, user_id: int) -> list[MyFood]:
    return list(
        session.exec(
            select(MyFood)
            .where(MyFood.user_id == user_id)
            .order_by(col(MyFood.created_at))
        ).all()
    )


def get_for_user(session: Session, item_id: int, user_id: int) -> MyFood | None:
    """取一条【属于该用户】的记录。别人的记录返回 None。"""
    return session.exec(
        select(MyFood).where(MyFood.id == item_id, MyFood.user_id == user_id)
    ).first()


def find_by_food(session: Session, user_id: int, food_id: int) -> MyFood | None:
    return session.exec(
        select(MyFood).where(MyFood.user_id == user_id, MyFood.food_id == food_id)
    ).first()


def add(session: Session, item: MyFood) -> MyFood:
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def save(session: Session, item: MyFood) -> MyFood:
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def delete(session: Session, item: MyFood) -> None:
    session.delete(item)
    session.commit()
