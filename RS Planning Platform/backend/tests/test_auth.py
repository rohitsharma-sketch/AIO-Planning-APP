def test_login_wrong_password_returns_401(client, test_user):
    r = client.post("/api/auth/login", json={"username": "test_planner", "password": "wrong"})
    assert r.status_code == 401


def test_login_success_sets_session(client, test_user):
    r = client.post("/api/auth/login", json={"username": "test_planner", "password": "testpass123"})
    assert r.status_code == 200
    assert r.json()["role"] == "planner"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "test_planner"


def test_me_without_login_returns_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout_clears_session(client, test_user):
    client.post("/api/auth/login", json={"username": "test_planner", "password": "testpass123"})
    client.post("/api/auth/logout")
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_admin_route_rejects_non_admin(client, test_user):
    client.post("/api/auth/login", json={"username": "test_planner", "password": "testpass123"})
    r = client.get("/api/auth/admin/users")
    assert r.status_code == 403
