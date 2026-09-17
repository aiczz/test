"""管理员接口测试。

覆盖：权限隔离、用户统计、用户列表、封禁/解封、登录记录。
两个安全重点是【封禁要能踢掉已登录会话】和【管理员不能封自己】。
"""

from app.data.seed import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    DEMO_PASSWORD,
    DEMO_USERNAME,
)


def _auth(client, username: str, password: str) -> dict:
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _admin(client) -> dict:
    return _auth(client, ADMIN_USERNAME, ADMIN_PASSWORD)


def _demo(client) -> dict:
    return _auth(client, DEMO_USERNAME, DEMO_PASSWORD)


def _demo_id(client, header) -> int:
    rows = client.get("/api/admin/users", headers=header).json()["items"]
    return next(u["id"] for u in rows if u["username"] == DEMO_USERNAME)


# ---------------------------------------------------------------- 权限


def test_admin_endpoints_require_login(client):
    for path in ("/api/admin/stats", "/api/admin/users", "/api/admin/logins"):
        assert client.get(path).status_code == 401


def test_admin_endpoints_reject_normal_user(client):
    """普通用户拿到 403，不是 404 —— 管理员接口的存在不是秘密，但权限必须挡住。"""
    header = _demo(client)
    for path in ("/api/admin/stats", "/api/admin/users", "/api/admin/logins"):
        assert client.get(path, headers=header).status_code == 403


def test_demo_account_is_not_admin(client):
    header = _demo(client)
    assert (
        client.get("/api/auth/me", headers=header).json()["username"] == DEMO_USERNAME
    )
    assert client.get("/api/admin/stats", headers=header).status_code == 403


# ---------------------------------------------------------------- 统计


def test_admin_stats(client):
    header = _admin(client)
    body = client.get("/api/admin/stats", headers=header).json()
    # 种子数据：demo + admin
    assert body["total_users"] == 2
    assert body["admin_users"] == 1
    assert body["banned_users"] == 0
    assert body["active_users_today"] >= 1  # admin 刚登录过
    assert body["logins_today"] >= 1


def test_stats_counts_new_registration(client):
    header = _admin(client)
    before = client.get("/api/admin/stats", headers=header).json()

    client.post(
        "/api/auth/register", json={"username": "newbie", "password": "pw123456"}
    )

    after = client.get("/api/admin/stats", headers=header).json()
    assert after["total_users"] == before["total_users"] + 1
    # ⚠️ 用相对断言：种子账号（demo/admin）也是"今天创建"的，
    #    写死 == 1 会因为它们在同一个内存库里而失败。
    assert after["new_users_today"] == before["new_users_today"] + 1


def test_stats_counts_banned(client):
    header = _admin(client)
    client.post(f"/api/admin/users/{_demo_id(client, header)}/ban", headers=header)
    assert client.get("/api/admin/stats", headers=header).json()["banned_users"] == 1


# ---------------------------------------------------------------- 用户列表


def test_admin_user_list(client):
    header = _admin(client)
    body = client.get("/api/admin/users", headers=header).json()

    assert body["total"] == 2
    usernames = [u["username"] for u in body["items"]]
    assert DEMO_USERNAME in usernames
    assert ADMIN_USERNAME in usernames

    admin_row = next(u for u in body["items"] if u["username"] == ADMIN_USERNAME)
    assert admin_row["is_admin"] is True
    assert admin_row["is_banned"] is False
    assert admin_row["last_login_at"] is not None  # 刚刚登录过
    assert admin_row["login_count"] >= 1
    # ★ 响应里绝不能出现密码哈希
    assert "password_hash" not in admin_row


def test_admin_user_search(client):
    header = _admin(client)
    body = client.get("/api/admin/users?keyword=dem", headers=header).json()
    assert body["total"] == 1
    assert body["items"][0]["username"] == DEMO_USERNAME


# ---------------------------------------------------------------- 封禁


def test_ban_then_unban(client):
    header = _admin(client)
    demo_id = _demo_id(client, header)

    resp = client.post(f"/api/admin/users/{demo_id}/ban", headers=header)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_banned"] is True

    # 被封后登录被拒（403，不是 401 —— 区分「密码错」和「被封了」）
    resp = client.post(
        "/api/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD}
    )
    assert resp.status_code == 403

    resp = client.post(f"/api/admin/users/{demo_id}/unban", headers=header)
    assert resp.json()["is_banned"] is False
    resp = client.post(
        "/api/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD}
    )
    assert resp.status_code == 200


def test_banned_user_cannot_use_existing_token(client):
    """★ 封禁必须能踢掉【已经登录】的会话。

    否则「封禁」只挡得住新登录，已经在线的照用不误。
    """
    demo_header = _demo(client)
    assert client.get("/api/my-foods", headers=demo_header).status_code == 200

    header = _admin(client)
    client.post(
        f"/api/admin/users/{_demo_id(client, header)}/ban", headers=header
    )

    # 拿着封禁【之前】签发的 token 也不好使了
    assert client.get("/api/my-foods", headers=demo_header).status_code == 401


def test_cannot_ban_self(client):
    """★ 管理员不能封自己 —— 封了就没人能解封这个系统了。"""
    header = _admin(client)
    rows = client.get("/api/admin/users", headers=header).json()["items"]
    admin_id = next(u["id"] for u in rows if u["username"] == ADMIN_USERNAME)

    resp = client.post(f"/api/admin/users/{admin_id}/ban", headers=header)
    assert resp.status_code == 400
    assert "自己" in resp.json()["detail"]


def test_ban_unknown_user_is_404(client):
    header = _admin(client)
    assert (
        client.post("/api/admin/users/9999/ban", headers=header).status_code == 404
    )


# ---------------------------------------------------------------- 登录记录


def test_login_log_records_success(client):
    _demo(client)
    header = _admin(client)  # admin 最后登录，所以最新一条是它
    body = client.get("/api/admin/logins", headers=header).json()

    assert body["total"] >= 2
    latest = body["items"][0]
    assert latest["username"] == ADMIN_USERNAME
    assert latest["success"] is True
    assert latest["ip"] is not None


def test_login_log_records_failure(client):
    client.post(
        "/api/auth/login",
        json={"username": DEMO_USERNAME, "password": "definitely-wrong"},
    )
    header = _admin(client)
    body = client.get(
        "/api/admin/logins?only_failed=true", headers=header
    ).json()

    assert body["total"] >= 1
    failed = next(i for i in body["items"] if i["username"] == DEMO_USERNAME)
    assert failed["success"] is False
    assert failed["detail"] == "用户名或密码不正确"


def test_login_log_records_unknown_user(client):
    """用户名打错时也留一条 —— 否则「刷账号」的行为完全看不见。"""
    client.post(
        "/api/auth/login", json={"username": "ghost-who", "password": "x"}
    )
    header = _admin(client)
    body = client.get(
        "/api/admin/logins?username=ghost-who", headers=header
    ).json()

    assert body["total"] == 1
    assert body["items"][0]["user_id"] is None


def test_login_log_records_ban_attempt(client):
    header = _admin(client)
    client.post(
        f"/api/admin/users/{_demo_id(client, header)}/ban", headers=header
    )
    client.post(
        "/api/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD}
    )

    body = client.get(
        "/api/admin/logins?only_failed=true", headers=header
    ).json()
    assert any(i["detail"] == "账号已被封禁" for i in body["items"])


def test_login_log_search(client):
    _demo(client)
    header = _admin(client)
    body = client.get(
        f"/api/admin/logins?username={DEMO_USERNAME}", headers=header
    ).json()

    assert body["total"] >= 1
    assert all(i["username"] == DEMO_USERNAME for i in body["items"])
