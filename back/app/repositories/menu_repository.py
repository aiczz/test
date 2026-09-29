"""菜单数据访问（说明书 §7.10 / §7.11）。"""

from sqlmodel import Session, col, select

from app.models.menu import MenuPlan, MenuPlanItem


def create_plan(session: Session, plan: MenuPlan) -> MenuPlan:
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


def add_items(session: Session, items: list[MenuPlanItem]) -> None:
    for item in items:
        session.add(item)
    session.commit()


def get_plan(session: Session, plan_id: int, user_id: int) -> MenuPlan | None:
    """★ 必须带 user_id —— 只按 id 查的话能读到别人的菜单（越权）。"""
    return session.exec(
        select(MenuPlan).where(
            MenuPlan.id == plan_id, MenuPlan.user_id == user_id
        )
    ).first()


def get_items(session: Session, plan_id: int) -> list[MenuPlanItem]:
    return list(
        session.exec(
            select(MenuPlanItem)
            .where(MenuPlanItem.menu_plan_id == plan_id)
            .order_by(col(MenuPlanItem.day_index), col(MenuPlanItem.sort_order))
        ).all()
    )


def get_latest(session: Session, user_id: int, plan_type: str) -> MenuPlan | None:
    return session.exec(
        select(MenuPlan)
        .where(MenuPlan.user_id == user_id, MenuPlan.plan_type == plan_type)
        .order_by(col(MenuPlan.id).desc())
    ).first()
