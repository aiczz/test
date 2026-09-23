"""认证接口测试（说明书 §12）。"""

from sqlmodel import select

from app.data.seed import DEMO_PASSWORD, DEMO_USERNAME
from app.models.user import User


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_register_then_login_then_me(client):
    resp = client.post(
        "/api/auth/register",
        json={"username": "xiaoming", "password": "pw123456", "family_size": 4},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["username"] == "xiaoming"
    assert body["family_size"] == 4
    # ★ 响应里绝不能出现密码哈希
    assert "password_hash" not in body

    resp = client.post(
        "/api/auth/login", json={"username": "xiaoming", "password": "pw123456"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["token_type"] == "bearer"
    token = resp.json()["access_token"]

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "xiaoming"


def test_me_without_token_is_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_garbage_token_is_401(client):
    resp = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code == 401


def test_duplicate_username_is_409(client):
    payload = {"username": "dup", "password": "pw123456"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_wrong_password_is_401(client):
    client.post("/api/auth/register", json={"username": "u1", "password": "pw123456"})
    resp = client.post(
        "/api/auth/login", json={"username": "u1", "password": "wrong-one"}
    )
    assert resp.status_code == 401


def test_unknown_user_and_wrong_password_give_same_message(client):
    """用户名不存在和密码错误必须返回同一句话，否则可以枚举用户名。"""
    client.post("/api/auth/register", json={"username": "u2", "password": "pw123456"})
    wrong_pw = client.post(
        "/api/auth/login", json={"username": "u2", "password": "nope"}
    )
    no_user = client.post(
        "/api/auth/login", json={"username": "ghost", "password": "nope"}
    )
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["detail"] == no_user.json()["detail"]


def test_password_is_stored_as_hash(client, session):
    """密码必须哈希后保存，禁止明文（说明书 §12）。"""
    client.post(
        "/api/auth/register",
        json={"username": "hashme", "password": "plaintext123"},
    )
    user = session.exec(select(User).where(User.username == "hashme")).first()
    assert user is not None
    assert user.password_hash != "plaintext123"
    assert user.password_hash.startswith("$2")  # bcrypt


def test_demo_account_is_seeded_and_usable(client):
    """演示账号必须开箱可用 —— 评委不注册也能进去。"""
    resp = client.post(
        "/api/auth/login",
        json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["family_size"] == 3


def test_sms_register_then_login_persists_user(client):
    payload = {"phone": "13800138000", "code": "123456"}
    registered = client.post("/api/auth/sms/register", json=payload)
    assert registered.status_code == 201, registered.text
    assert registered.json()["username"] == payload["phone"]

    logged_in = client.post("/api/auth/sms/login", json=payload)
    assert logged_in.status_code == 200, logged_in.text
    token = logged_in.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["nickname"] == "用户8000"


def test_sms_wrong_code_is_rejected(client):
    response = client.post(
        "/api/auth/sms/register",
        json={"phone": "13900139000", "code": "000000"},
    )
    assert response.status_code == 401


def test_seed_is_idempotent(session):
    """重复灌种子数据不应该产生重复记录；启动时会反复调用。"""
    from app.data.seed import seed_all
    from app.models.recipe import Recipe

    before = len(session.exec(select(Recipe)).all())
    seed_all(session)
    seed_all(session)
    after = len(session.exec(select(Recipe)).all())
    assert before == after > 0
