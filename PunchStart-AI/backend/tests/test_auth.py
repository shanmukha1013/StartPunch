from tests.conftest import signup


def test_signup_login_me_logout(client):
    user = signup(client, "Ada Lovelace", "ada@example.com")
    assert user["email"] == "ada@example.com"
    assert user["handle"].startswith("ada")
    me = client.get("/api/auth/me").json()
    assert me["user"]["name"] == "Ada Lovelace"
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    bad = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-pass1"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/login", json={"email": "ADA@example.com", "password": "Founder123"})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_session_cookie_is_httponly(client):
    response = client.post("/api/auth/signup", json={"name": "Bo", "email": "bo@example.com", "password": "Founder123"})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_duplicate_email_and_weak_password(client):
    signup(client, "Ada", "ada@example.com")
    dup = client.post("/api/auth/signup", json={"name": "Ada2", "email": "ada@example.com", "password": "Founder123"})
    assert dup.status_code == 409
    weak = client.post("/api/auth/signup", json={"name": "Weak", "email": "weak@example.com", "password": "short"})
    assert weak.status_code == 422


def test_csrf_header_required_for_writes(client):
    response = client.post("/api/auth/signup", json={"name": "X", "email": "x@example.com", "password": "Founder123"},
                           headers={"X-StartPunch-Client": ""})
    assert response.status_code == 403


def test_password_change_invalidates_other_sessions(make_client):
    c1, user = make_client("Ada", "ada@example.com")
    from fastapi.testclient import TestClient
    from startpunch.main import app

    c2 = TestClient(app)
    c2.headers.update({"X-StartPunch-Client": "web"})
    assert c2.post("/api/auth/login", json={"email": "ada@example.com", "password": "Founder123"}).status_code == 200
    assert c1.post("/api/auth/password", json={"current_password": "Founder123", "new_password": "NewPass456"}).status_code == 200
    assert c1.get("/api/auth/me").status_code == 200  # current session re-issued
    assert c2.get("/api/auth/me").status_code == 401  # other session revoked
    c2.close()


def test_auth_rate_limit(client):
    codes = [client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Whatever1"}).status_code
             for _ in range(12)]
    assert 429 in codes


def test_export_and_delete_account(client):
    signup(client, "Del", "del@example.com")
    client.post("/api/posts", json={"body": "hello world"})
    export = client.get("/api/auth/export").json()
    assert export["profile"]["email"] == "del@example.com"
    assert "password_hash" not in export["profile"]
    assert len(export["posts"]) == 1
    assert client.request("DELETE", "/api/auth/account", json={"password": "wrong"}).status_code == 403
    assert client.request("DELETE", "/api/auth/account", json={"password": "Founder123"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "del@example.com", "password": "Founder123"}).status_code == 401


def test_health(client):
    body = client.get("/api/health").json()
    assert body["database"] == "ok"
    assert body["ai_configured"] is False


def test_session_probe_never_401(client):
    assert client.get("/api/auth/session").json() == {"authenticated": False, "handle": None}
    user = signup(client, "Cy", "cy@example.com")
    assert client.get("/api/auth/session").json() == {"authenticated": True, "handle": user["handle"]}


def test_public_overview_is_aggregate_only(client):
    body = client.get("/api/intelligence/public-overview").json()
    assert set(body) == {"entities", "startups", "shutdowns", "sectors", "built_at", "sources"}
    assert client.get("/api/intelligence/coverage").status_code == 401  # detailed data requires sign-in
