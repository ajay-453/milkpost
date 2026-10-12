"""Barnboard test suite — pure-logic units + live endpoint checks.

Run:  cd app && .venv/bin/python -m pytest -q
Covers: INR formatting, withholding clear-date, password hashing, and the auth
gate + login rate-limiting via FastAPI's TestClient (no network, no live server).
"""
import os
import tempfile
from datetime import date

import pytest

# Point the app at a throwaway DB before importing it.
_TMP = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["LOGIN_RATE_MAX"] = "5"
os.environ["LOGIN_RATE_WINDOW"] = "60"

from app import db, main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client():
    db.init_db()
    with db.get_db() as con:
        if not con.execute("SELECT 1 FROM users WHERE username = 'tester'").fetchone():
            uid = db.create_user(con, "tester", "testpass123", role="owner", approved=True)
            db.set_security(con, uid, "What is your village name?", "kondapur")
    return TestClient(main.app)


# ── pure logic ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("n,expected", [
    (0, "0"), (999, "999"), (1000, "1,000"), (100000, "1,00,000"),
    (1234567, "12,34,567"), (12345678, "1,23,45,678"),
])
def test_inr_grouping(n, expected):
    assert main.inr_format(n) == expected


def test_inr_decimals():
    assert main.inr_format(1234.5, 2) == "1,234.50"


def test_withhold_clear_date():
    # treated on the 1st with a 5-day withhold -> clears on the 6th
    assert db.withhold_clear_date("2026-09-01", 5) == date(2026, 9, 6)


def test_password_hash_roundtrip():
    h = db.hash_password("s3cret-pass")
    assert db.verify_password("s3cret-pass", h)
    assert not db.verify_password("wrong", h)


def test_security_answer_normalized(client):
    # answers compare case- and space-insensitively (client fixture seeds the user)
    con = db.get_db()
    row = con.execute("SELECT security_answer_hash FROM users WHERE username='tester'").fetchone()
    con.close()
    assert db.verify_password(db._norm_answer("  KONDAPUR "), row["security_answer_hash"])


# ── endpoints (auth gate + rate limiting) ────────────────────────────────────

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


# ── data exports + JSON API (TestForge-fix arc F0.3) ────────────────────────

@pytest.fixture(scope="module")
def authed(client):
    c = TestClient(main.app)
    r = c.post("/login", data={"username": "tester", "password": "testpass123"},
               headers={"x-forwarded-for": "203.0.113.20"}, follow_redirects=False)
    assert r.status_code == 303
    return c


def test_table_columns_binds_name(client):
    with db.get_db() as con:
        names = [c[1] for c in db.table_columns(con, "cows")]
        assert {"id", "tag"} <= set(names)
        assert db.table_columns(con, "cows; DROP TABLE cows") == []
    assert set(db.EXPORT_SELECT) == set(db.EXPORT_TABLES)


def test_export_csv_whitelist(authed):
    r = authed.get("/export/cows.csv")
    assert r.status_code == 200 and r.text.splitlines()[0].startswith("id")
    assert authed.get("/export/users.csv").status_code == 404
    assert authed.get("/export/sessions.csv").status_code == 404


def test_api_v1_schema_and_table(authed):
    s = authed.get("/api/v1/schema").json()
    assert set(s["tables"]) == set(db.EXPORT_TABLES)
    assert all(cols for cols in s["tables"].values())
    t = authed.get("/api/v1/cows.json")
    assert t.status_code == 200 and t.json()["table"] == "cows"
    assert authed.get("/api/v1/users.json").status_code == 404


# ── runtime: compression, cache headers, documented API (arc F2) ───────────

def test_gzip_on_pages(authed):
    r = authed.get("/", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_api_get_is_privately_cacheable(authed):
    for path in ("/api/v1/schema", "/api/v1/cows.json"):
        assert authed.get(path).headers.get("cache-control") == "private, max-age=30"


def test_openapi_documents_json_api(client):
    paths = main.app.openapi()["paths"]
    routes = [("/api/v1/schema", "get"), ("/api/v1/{table}.json", "get"),
              ("/api/v1/demo-credentials", "post"), ("/api/v1/metrics", "get"),
              ("/api/v1/metrics/{metric_id}", "get"), ("/api/v1/predict/yield/{cow_id}", "get")]
    for path, verb in routes:
        schema = paths[path][verb]["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema.get("$ref"), path


# ── structured request log (arc F5.3) ───────────────────────────────────────

def test_request_log_is_json_without_secret_tokens(authed):
    import json
    import logging
    lines = []

    class Grab(logging.Handler):
        def emit(self, record):
            lines.append(json.loads(main.access_log.handlers[0].format(record)))

    h = Grab()
    main.access_log.addHandler(h)
    try:
        r = authed.get("/api/v1/cows.json")
        TestClient(main.app).get("/reset/s3cret-token-abc")
    finally:
        main.access_log.removeHandler(h)
    hit = [ln for ln in lines if ln["path"] == "/api/v1/{table}.json"][0]
    assert hit["method"] == "GET" and hit["status"] == 200 and hit["level"] == "INFO"
    assert hit["duration_ms"] >= 0 and hit["request_id"] == r.headers["x-request-id"]
    assert {"ts", "message"} <= set(hit)
    reset = [ln for ln in lines if ln["path"].startswith("/reset/")][0]
    assert reset["path"] == "/reset/{token}" and reset["status"] == 404
    assert "s3cret" not in json.dumps(lines)
