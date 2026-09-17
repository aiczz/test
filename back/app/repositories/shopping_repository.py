"""购物清单数据访问（说明书 §7.12 / §7.13）。"""

from sqlmodel import Session, col, select

from app.models.shopping import ShoppingItem, ShoppingList


def create_list(session: Session, shopping_list: ShoppingList) -> ShoppingList:
    session.add(shopping_list)
    session.commit()
    session.refresh(shopping_list)
    return shopping_list


def add_items(session: Session, items: list[ShoppingItem]) -> None:
    for item in items:
        session.add(item)
    session.commit()


def get_list(
    session: Session, list_id: int, user_id: int
) -> ShoppingList | None:
    """★ 带 user_id，防止读到别人的清单。"""
    return session.exec(
        select(ShoppingList).where(
            ShoppingList.id == list_id, ShoppingList.user_id == user_id
        )
    ).first()


def get_latest(session: Session, user_id: int) -> ShoppingList | None:
    return session.exec(
        select(ShoppingList)
        .where(ShoppingList.user_id == user_id)
        .order_by(col(ShoppingList.id).desc())
    ).first()


def list_items(session: Session, list_id: int) -> list[ShoppingItem]:
    return list(
        session.exec(
            select(ShoppingItem)
            .where(ShoppingItem.shopping_list_id == list_id)
            .order_by(col(ShoppingItem.category), col(ShoppingItem.id))
        ).all()
    )


def get_item_for_user(
    session: Session, item_id: int, user_id: int
) -> ShoppingItem | None:
    """★ 通过清单归属校验，防止勾选到别人的条目。"""
    return session.exec(
        select(ShoppingItem)
        .join(
            ShoppingList,
            col(ShoppingItem.shopping_list_id) == col(ShoppingList.id),
        )
        .where(ShoppingItem.id == item_id, ShoppingList.user_id == user_id)
    ).first()


def save_item(session: Session, item: ShoppingItem) -> ShoppingItem:
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
