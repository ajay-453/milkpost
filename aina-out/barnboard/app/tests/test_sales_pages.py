"""Milk sales, page rendering and language switch, and account settings.

Run:  cd app && .venv/bin/python -m pytest -q   (fixtures: conftest.py)
"""

import pytest

from app import db, main
from fastapi.testclient import TestClient
from conftest import TODAY


def test_sales_record_and_month_rollup(owner):
    r = owner.post("/sales", data={"collected_on": db.iso(TODAY), "litres": "20",
                                   "price_per_litre": "45"})
    assert r.status_code == 200 and "Rs 900.00" in r.headers["x-toast"]
    assert owner.post("/sales", data={"collected_on": db.iso(TODAY), "litres": "a",
                                      "price_per_litre": "1"}).status_code == 422
    assert owner.post("/sales", data={"collected_on": db.iso(TODAY), "litres": "0",
                                      "price_per_litre": "45"}).status_code == 422
    assert owner.get("/sales").status_code == 200


def test_pages_render(owner):
    for path in ("/", "/roadmap", "/account", "/team", "/cows", "/treatments", "/breeding"):
        assert owner.get(path).status_code == 200, path
    r = owner.get("/lang/te", params={"next": "//evil.example"}, follow_redirects=False)
    assert r.headers["location"] == "/" and "bb_lang=te" in r.headers["set-cookie"]


def test_account_password_and_question_validation(owner):
    bad = owner.post("/account/password", data={"current": "wrong", "new": "x" * 8, "new2": "x" * 8})
    assert bad.status_code == 422
    short = owner.post("/account/password", data={"current": "farmpass123", "new": "x", "new2": "x"})
    assert short.status_code == 422
    q = owner.post("/account/security", data={"question": "Pet?", "answer": "a"})
    assert q.status_code == 422
    ok = owner.post("/account/security", data={"question": "Pet?", "answer": "Tommy"},
                    follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/account?saved_q=1"
    assert owner.get("/account", params={"saved_q": 1}).status_code == 200


# ── first run, demo seed and dashboard on an empty farm (arc F6.1) ──────────

@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A brand-new empty database for one test (the shared one already has data)."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "fresh.db"))
    db.init_db()
    return tmp_path


def _signed_in(username="newowner"):
    with db.get_db() as con:
        uid = db.create_user(con, username, "ownerpass1", role="owner", approved=True)
        token = db.create_session(con, uid)
    c = TestClient(main.app)
    c.cookies.set("bb_session", token)
    return c


def test_startup_seeds_demo_farm_and_login(fresh_db, monkeypatch):
    monkeypatch.setenv("BARNBOARD_SEED", "1")
    monkeypatch.setenv("DEMO_LOGIN", "demo: demopass1")
    main.startup()
    with db.get_db() as con:
        assert con.execute("SELECT COUNT(*) n FROM cows").fetchone()["n"] == len(db._SEED_COWS)
        assert db.authenticate(con, "demo", " demopass1") is not None
    main.startup()                       # second start: nothing duplicated
    with db.get_db() as con:
        assert con.execute("SELECT COUNT(*) n FROM cows").fetchone()["n"] == len(db._SEED_COWS)


def test_first_request_self_heals_a_recycled_db(fresh_db, monkeypatch):
    monkeypatch.setenv("BARNBOARD_SEED", "1")
    monkeypatch.setenv("DEMO_LOGIN", "demo:demopass1")
    main._ensure_seed()
    with db.get_db() as con:
        assert con.execute("SELECT COUNT(*) n FROM cows").fetchone()["n"] == len(db._SEED_COWS)
        assert db.authenticate(con, "demo", "demopass1") is not None

    def broken():
        raise OSError("read-only filesystem")
    monkeypatch.setattr(db, "init_db", broken)
    main._ensure_seed()                  # never takes a request down


def test_empty_farm_then_demo_seed_and_dashboard(fresh_db, monkeypatch):
    c = _signed_in()
    empty = c.get("/export/cows.csv")
    assert empty.status_code == 200 and empty.text.strip().startswith("id,")   # header only
    assert len(empty.text.strip().splitlines()) == 1
    r = c.post("/demo-seed")
    assert r.headers["HX-Redirect"] == "/"
    c.post("/demo-seed")                 # already seeded: no-op
    with db.get_db() as con:
        assert con.execute("SELECT COUNT(*) n FROM cows").fetchone()["n"] == len(db._SEED_COWS)
        drops = db.yield_drop_alerts(con, TODAY)
        calvings = db.upcoming_calvings(con, TODAY, 30)
    assert [d["tag"] for d in drops] == ["102"]          # the seeded decline
    assert [b["days_left"] for b in calvings] == [12]    # the seeded confirmed pregnancy
    # no price reference and no model artifact: the dashboard still renders
    monkeypatch.setattr(main, "_hub_root", lambda: fresh_db)
    monkeypatch.setattr(main, "MODELS_DIR", str(fresh_db / "no-models"))
    page = c.get("/")
    assert page.status_code == 200 and "Lakshmi" in page.text and "Milk price outlook" not in page.text
    assert c.get("/api/v1/predict/yield/1").status_code == 503
