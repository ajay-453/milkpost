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
        if not db.has_users(con):
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
