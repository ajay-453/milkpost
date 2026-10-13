"""The login gate: anonymous redirects, rate limiting, session cookies, guest and shared OC Apps logins.

Run:  cd app && .venv/bin/python -m pytest -q   (fixtures: conftest.py)
"""

from app import main
from fastapi.testclient import TestClient


def test_temp_guest_login_survives_instance_loss(client):
    # Serverless: the guest row is minted in one instance's /tmp DB, but the
    # login may land on another. The derived password must authenticate and
    # lazily re-create the account (db.authenticate); junk must not.
    from app import db
    with db.get_db() as con:
        u, p = db.create_temp_user(con)
        con.execute("DELETE FROM users WHERE username = ?", (u,))
    with db.get_db() as con:
        assert db.authenticate(con, u, "milk-0000-moo") is None
        user = db.authenticate(con, u, p)
        assert user is not None and user["is_temp"] == 1 and user["approved"] == 1
    r = client.post("/login", data={"username": u, "password": p}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    client.cookies.clear()  # leave the shared client anonymous again


def test_protected_route_redirects_when_anon(client):
    # Anonymous root lands on the public marketing page (cea9fca); protected
    # non-public paths still bounce to /login.
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/welcome"
    r = client.get("/cows", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_healthz_open(client):
    assert client.get("/healthz").text == "ok"


def test_wrong_password_401_then_rate_limited(client):
    # fresh IP bucket via a unique X-Forwarded-For
    hdr = {"x-forwarded-for": "203.0.113.7"}
    main._rl_hits.pop("login:203.0.113.7", None)   # a rerun in the same process starts fresh
    codes = [client.post("/login", data={"username": "tester", "password": f"nope{i}"},
                         headers=hdr, follow_redirects=False).status_code for i in range(5)]
    assert codes == [401, 401, 401, 401, 401]
    # 6th within the window is throttled
    assert client.post("/login", data={"username": "tester", "password": "nope"},
                       headers=hdr, follow_redirects=False).status_code == 429


def test_good_login_sets_secure_aware_cookie(client):
    hdr = {"x-forwarded-for": "203.0.113.8"}
    r = client.post("/login", data={"username": "tester", "password": "testpass123"},
                    headers=hdr, follow_redirects=False)
    assert r.status_code == 303
    assert "bb_session=" in r.headers.get("set-cookie", "")


def test_oc_apps_shared_guest_login(client):
    """One login for every OC app: guest-YYMMDD-xxxx with the Tallyard/Abhyas derivation."""
    import base64, hashlib, hmac, time
    from app import db as _db
    username = f"guest-{time.strftime('%y%m%d')}-abcd"
    with _db.get_db() as con:
        secret = _db._stateless_secret(con)
    raw = hmac.new(secret.encode(), f"guest:{username}".encode(), hashlib.sha256).digest()
    password = base64.b32encode(raw).decode().lower().rstrip("=")[:10]
    with _db.get_db() as con:
        assert _db.authenticate(con, username, password) is not None       # materialised on first use
        assert _db.authenticate(con, username, "wrong-password") is None
        assert _db.authenticate(con, "guest-000101-abcd", password) is None  # expired issue date
    r = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303)


# ── edges of the gate (arc F6.1) ────────────────────────────────────────────

def test_old_attempts_leave_the_rate_window(client):
    ip = "203.0.113.70"
    main._rl_hits[f"login:{ip}"].extend([main._time.monotonic() - 3600] * 5)   # an hour ago
    r = client.post("/login", data={"username": "tester", "password": "nope"},
                    headers={"x-forwarded-for": ip}, follow_redirects=False)
    assert r.status_code == 401                       # not 429: stale hits were dropped
    assert len(main._rl_hits[f"login:{ip}"]) == 1


def test_htmx_request_without_session_gets_401_redirect(client):
    r = TestClient(main.app).get("/cows", headers={"HX-Request": "true"}, follow_redirects=False)
    assert r.status_code == 401 and r.headers["HX-Redirect"] == "/login"


def test_public_pages_and_language(client):
    anon = TestClient(main.app)
    assert anon.get("/welcome").status_code == 200
    r = anon.get("/lang/xx", params={"next": "/cows"}, follow_redirects=False)
    assert r.headers["location"] == "/cows" and "bb_lang=en" in r.headers["set-cookie"]


def test_demo_login(client, monkeypatch):
    anon = TestClient(main.app)
    monkeypatch.delenv("DEMO_LOGIN", raising=False)
    assert anon.get("/demo", follow_redirects=False).headers["location"] == "/welcome"
    monkeypatch.setenv("DEMO_LOGIN", "nobody-like-this:pw")
    assert anon.get("/demo", follow_redirects=False).headers["location"] == "/login"
    monkeypatch.setenv("DEMO_LOGIN", "tester:testpass123")
    r = anon.get("/demo", follow_redirects=False)
    assert r.headers["location"] == "/" and "bb_session=" in r.headers["set-cookie"]
