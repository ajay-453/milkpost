"""Shared test setup: a throwaway DB (set before the app is imported) and the
logged-in clients most test files use. Fixtures are module-scoped, so each test
file gets its own clients.

Run:  cd app && .venv/bin/python -m pytest -q
"""
import os
import tempfile
from datetime import date

import pytest

# Point the app at a throwaway DB before importing it.
_TMP = tempfile.mkdtemp()
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "test.db"))
os.environ["LOGIN_RATE_MAX"] = "5"
os.environ["LOGIN_RATE_WINDOW"] = "60"

from app import db, main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TODAY = date.today()


def _login(username, password, ip):
    main._rl_hits.pop(f"login:{ip}", None)   # fixtures log in once per module; never throttle them
    c = TestClient(main.app)
    r = c.post("/login", data={"username": username, "password": password},
               headers={"x-forwarded-for": ip}, follow_redirects=False)
    assert r.status_code == 303
    return c


@pytest.fixture(scope="module")
def client():
    db.init_db()
    with db.get_db() as con:
        if not con.execute("SELECT 1 FROM users WHERE username = 'tester'").fetchone():
            uid = db.create_user(con, "tester", "testpass123", role="owner", approved=True)
            db.set_security(con, uid, "What is your village name?", "kondapur")
    return TestClient(main.app)


@pytest.fixture(scope="module")
def authed(client):
    """The `tester` owner, logged in."""
    return _login("tester", "testpass123", "203.0.113.20")


@pytest.fixture(scope="module")
def owner():
    """The `farmer` owner, logged in, with this module's F4x cows cleared first
    (so a module can run twice in one process, as mutation testing does)."""
    db.init_db()
    with db.get_db() as con:
        mine = "SELECT id FROM cows WHERE tag LIKE 'F4%'"
        for table in ("milk_logs", "treatments", "breedings"):
            con.execute(f"DELETE FROM {table} WHERE cow_id IN ({mine})")
        con.execute("DELETE FROM cows WHERE tag LIKE 'F4%'")
        if not con.execute("SELECT 1 FROM users WHERE username = 'farmer'").fetchone():
            db.create_user(con, "farmer", "farmpass123", role="owner", approved=True)
    return _login("farmer", "farmpass123", "203.0.113.40")


def _cow(owner, tag, status="milking"):
    """Add a cow through the app and return its id."""
    r = owner.post("/cows", data={"tag": tag, "name": "Lakshmi", "breed": "Gir", "status": status})
    assert r.status_code == 200, r.headers.get("x-toast")
    with db.get_db() as con:
        return con.execute("SELECT id FROM cows WHERE tag = ?", (tag,)).fetchone()["id"]
