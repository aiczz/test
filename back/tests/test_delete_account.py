"""注销账号接口测试（DELETE /api/auth/me）。

这个接口是【真删】，不是打个 is_deleted 标记停用。所以要盯住两件事：

  1. 该用户在每一张关联表里的行都必须一条不剩。漏一张表不会报错、
     不会崩，只是数据留在磁盘上 —— 这种错只有逐表数行数才看得出来。
  2. 管理员和演示账号必须删不掉。演示账号（demo，评委一键登录用的那个）
     密码是写在 README 里的公开值，而且它在种子里**不是**管理员 ——
     只判 is_admin 的话，任何人都能删掉它。比赛演示用的 admin 同理，
     被误删之后后台进不去、也没有人能再建一个回来。

删除顺序的约束见 `auth_service.delete_account`。
"""

from sqlalchemy import func
from sqlmodel import select

from app.data.seed import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    DEMO_PASSWORD,
    DEMO_USERNAME,
)
from app.models.favorite import Favorite
from app.models.login_log import LoginLog
from app.models.menu import MenuPlan, MenuPlanItem
from app.models.my_food import MyFood
from app.models.shopping import ShoppingItem, ShoppingList
from app.models.user import User, UserPreference

PASSWORD = "12345678"


def _register_and_login(client, username: str) -> tuple[str, int]:
    """注册 + 登录，返回 (token, user_id)。

    刻意走真实接口而不是直接往库里插用户：注销要清掉的 `login_logs` 和
    `user_preferences` 正是注册 / 登录顺手写下的两行，走接口才覆盖得到。
    """
    created = client.post(
        "/api/auth/register", json={"username": username, "password": PASSWORD}
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    logged_in = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert logged_in.status_code == 200, logged_in.text
    return logged_in.json()["access_token"], user_id


def _seed_user_data(session, user_id: int) -> dict[str, int]:
    """把六张关联表都写上这个用户的数据，返回两张父表的 id。

    父表 id 要留给断言用：删完之后父行已经不在了，「按 user_id 查子表」
    会连一条都查不到 —— 那时「没删干净」和「删干净了」看起来一模一样。
    """
    plan = MenuPlan(user_id=user_id)
    session.add(plan)
    shopping = ShoppingList(user_id=user_id)
    session.add(shopping)
    session.commit()
    session.refresh(plan)
    session.refresh(shopping)

    session.add(MenuPlanItem(menu_plan_id=plan.id, recipe_id=1))
    session.add(ShoppingItem(shopping_list_id=shopping.id, name="莲藕"))
    session.add(Favorite(user_id=user_id, recipe_id=1))
    session.add(MyFood(user_id=user_id, custom_name="藕"))
    session.commit()

    return {"plan": plan.id, "shopping": shopping.id}


def _count(session, model, condition) -> int:
    return int(
        session.exec(select(func.count()).select_from(model).where(condition)).one()
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_delete_account_returns_204_and_wipes_every_related_row(client, session):
    token, user_id = _register_and_login(client, "leave-me")
    ids = _seed_user_data(session, user_id)

    # 先确认数据确实写进去了。不先断言一次的话，下面那一串「等于 0」
    # 也可能只是因为压根没插进去，测试就变成了空转。
    assert _count(session, User, User.id == user_id) == 1
    assert _count(session, UserPreference, UserPreference.user_id == user_id) == 1
    assert _count(session, LoginLog, LoginLog.user_id == user_id) >= 1
    assert _count(session, Favorite, Favorite.user_id == user_id) == 1
    assert _count(session, MyFood, MyFood.user_id == user_id) == 1
    assert _count(session, MenuPlan, MenuPlan.user_id == user_id) == 1
    assert _count(session, ShoppingList, ShoppingList.user_id == user_id) == 1
    assert _count(session, MenuPlanItem, MenuPlanItem.menu_plan_id == ids["plan"]) == 1
    assert (
        _count(session, ShoppingItem, ShoppingItem.shopping_list_id == ids["shopping"])
        == 1
    )

    resp = client.delete("/api/auth/me", headers=_auth(token))
    assert resp.status_code == 204, resp.text

    assert _count(session, User, User.id == user_id) == 0
    assert _count(session, UserPreference, UserPreference.user_id == user_id) == 0
    # 登录记录也要清 —— 注销就该把个人痕迹一并带走
    assert _count(session, LoginLog, LoginLog.user_id == user_id) == 0
    assert _count(session, Favorite, Favorite.user_id == user_id) == 0
    assert _count(session, MyFood, MyFood.user_id == user_id) == 0
    assert _count(session, MenuPlan, MenuPlan.user_id == user_id) == 0
    assert _count(session, ShoppingList, ShoppingList.user_id == user_id) == 0
    # ★ 子表按【删除前记下的父 id】查。子表删漏了的话，这两条会红 ——
    #   而按 user_id 查是查不出来的（父表都没了）。
    assert _count(session, MenuPlanItem, MenuPlanItem.menu_plan_id == ids["plan"]) == 0
    assert (
        _count(session, ShoppingItem, ShoppingItem.shopping_list_id == ids["shopping"])
        == 0
    )


def test_delete_account_keeps_other_users_data(client, session):
    """删的是「我」，不是「所有人」。"""
    token, user_id = _register_and_login(client, "delete-me")
    _seed_user_data(session, user_id)

    _, other_id = _register_and_login(client, "bystander")
    other_ids = _seed_user_data(session, other_id)

    assert client.delete("/api/auth/me", headers=_auth(token)).status_code == 204

    assert _count(session, User, User.id == other_id) == 1
    assert _count(session, UserPreference, UserPreference.user_id == other_id) == 1
    assert _count(session, Favorite, Favorite.user_id == other_id) == 1
    assert _count(session, MyFood, MyFood.user_id == other_id) == 1
    assert _count(session, MenuPlan, MenuPlan.user_id == other_id) == 1
    assert _count(session, ShoppingList, ShoppingList.user_id == other_id) == 1
    assert (
        _count(session, MenuPlanItem, MenuPlanItem.menu_plan_id == other_ids["plan"])
        == 1
    )
    assert (
        _count(
            session,
            ShoppingItem,
            ShoppingItem.shopping_list_id == other_ids["shopping"],
        )
        == 1
    )


def test_deleted_token_is_401_on_second_call(client):
    """注销之后 token 不该还能用 —— 用户行都没了，鉴权要查不到人。"""
    token, _ = _register_and_login(client, "twice")

    assert client.delete("/api/auth/me", headers=_auth(token)).status_code == 204
    assert client.delete("/api/auth/me", headers=_auth(token)).status_code == 401
    # 顺带把「拿旧 token 读自己的资料」也锁住
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401


def test_admin_account_cannot_be_deleted(client, session):
    """★ 管理员账号必须删不掉，且删失败之后账号仍然完好可用。"""
    logged_in = client.post(
        "/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert logged_in.status_code == 200, logged_in.text
    token = logged_in.json()["access_token"]

    resp = client.delete("/api/auth/me", headers=_auth(token))
    assert resp.status_code == 403, resp.text
    # 理由要说人话：用户得知道「不是我操作错了，是这类账号不让注销」
    assert "管理员" in resp.json()["detail"]

    assert _count(session, User, User.username == ADMIN_USERNAME) == 1
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200
    assert (
        client.post(
            "/api/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        ).status_code
        == 200
    )


def test_demo_account_cannot_be_deleted(client, session):
    """★ 演示账号同样要挡住 —— 它的密码是公开的，能删就等于人人都有删除权。

    这个用例锁的是一条容易想当然的假设：「演示账号 = 管理员，判 is_admin 就够了」。
    实际上 seed 里的 demo 是 is_admin=False，只判 is_admin 的话它能被任何人删掉。
    """
    logged_in = client.post(
        "/api/auth/login",
        json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
    )
    assert logged_in.status_code == 200, logged_in.text
    token = logged_in.json()["access_token"]

    resp = client.delete("/api/auth/me", headers=_auth(token))
    assert resp.status_code == 403, resp.text

    assert _count(session, User, User.username == DEMO_USERNAME) == 1
    # 偏好也跟着留着 —— 否则「账号在、档案没了」，评委点进去看到的是默认值
    demo = session.exec(select(User).where(User.username == DEMO_USERNAME)).one()
    assert _count(session, UserPreference, UserPreference.user_id == demo.id) == 1


def test_delete_account_without_token_is_401(client):
    assert client.delete("/api/auth/me").status_code == 401


def test_delete_account_with_garbage_token_is_401(client):
    assert (
        client.delete("/api/auth/me", headers=_auth("not-a-real-token")).status_code
        == 401
    )
