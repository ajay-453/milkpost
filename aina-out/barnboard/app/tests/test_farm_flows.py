"""Farm-flow tests (TestForge-fix arc F4.2): the daily routes an owner uses —
herd, milk log, treatments with withholding, breeding to calving, sales, the
calendar feed and the account/team pages. Same throwaway-DB pattern as
test_barnboard.py.

Run:  cd app && .venv/bin/python -m pytest -q
"""
import os
import tempfile
from datetime import date, timedelta

import pytest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "test.db"))

from app import db, main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TODAY = date.today()


@pytest.fixture(scope="module")
def owner():
    db.init_db()
    with db.get_db() as con:
        if not con.execute("SELECT 1 FROM users WHERE username = 'farmer'").fetchone():
            db.create_user(con, "farmer", "farmpass123", role="owner", approved=True)
    c = TestClient(main.app)
    r = c.post("/login", data={"username": "farmer", "password": "farmpass123"},
               headers={"x-forwarded-for": "203.0.113.40"}, follow_redirects=False)
    assert r.status_code == 303
    return c


def _cow(owner, tag, status="milking"):
    r = owner.post("/cows", data={"tag": tag, "name": "Lakshmi", "breed": "Gir", "status": status})
    assert r.status_code == 200, r.headers.get("x-toast")
    with db.get_db() as con:
        return con.execute("SELECT id FROM cows WHERE tag = ?", (tag,)).fetchone()["id"]


# ── herd ────────────────────────────────────────────────────────────────────

def test_cow_create_validates_and_rejects_duplicates(owner):
    cid = _cow(owner, "F42")
    assert owner.post("/cows", data={"tag": "  "}).status_code == 422
    dup = owner.post("/cows", data={"tag": "F42"})
    assert dup.status_code == 422 and "already exists" in dup.headers["x-toast"]
    # unknown status falls back to milking
    _cow(owner, "F43", status="flying")
    with db.get_db() as con:
        assert con.execute("SELECT status FROM cows WHERE tag='F43'").fetchone()["status"] == "milking"
    assert "F42" in owner.get("/cows").text
    assert cid


def test_cow_status_change(owner):
    cid = _cow(owner, "F44")
    r = owner.post(f"/cows/{cid}/status", data={"status": "dry"})
    assert r.status_code == 200 and "is now dry" in r.headers["x-toast"]
    assert owner.post(f"/cows/{cid}/status", data={"status": "zzz"}).status_code == 422
    assert owner.post("/cows/999999/status", data={"status": "dry"}).status_code == 404


# ── milk log ────────────────────────────────────────────────────────────────

def test_milk_log_upserts_and_validates(owner):
    cid = _cow(owner, "F45")
    day = db.iso(TODAY)
    form = {"cow_id": cid, "log_date": day, "session": "AM", "litres": "7.5"}
    r = owner.post("/milk/log", data=form)
    assert r.status_code == 200 and "7.5 L saved" in r.headers["x-toast"]
    owner.post("/milk/log", data={**form, "litres": "8"})   # same session: overwrite
    with db.get_db() as con:
        rows = con.execute("SELECT litres FROM milk_logs WHERE cow_id = ?", (cid,)).fetchall()
    assert [r["litres"] for r in rows] == [8.0]
    assert owner.post("/milk/log", data={**form, "session": "XX"}).status_code == 422
    assert owner.post("/milk/log", data={**form, "log_date": "nope"}).status_code == 422
    assert owner.post("/milk/log", data={**form, "litres": "lots"}).status_code == 422
    assert owner.post("/milk/log", data={**form, "litres": "81"}).status_code == 422
    assert owner.post("/milk/log", data={**form, "cow_id": 999999}).status_code == 404
    page = owner.get("/milk", params={"d": day, "session": "AM"})
    assert page.status_code == 200 and "F45" in page.text
    assert owner.get("/milk", params={"d": "garbage", "session": "noon"}).status_code == 200


# ── treatments: the withholding core ────────────────────────────────────────

def test_treatment_withholds_milk_until_clear_date(owner):
    cid = _cow(owner, "F46")
    r = owner.post("/treatments", data={"cow_id": cid, "drug": "Oxytet",
                                        "treated_on": db.iso(TODAY), "withhold_days": 500})
    clear = db.iso(TODAY + timedelta(days=120))   # capped at 120 days
    assert r.status_code == 200 and f"withheld until {clear}" in r.headers["x-toast"]
    with db.get_db() as con:
        assert cid in db.withheld_cow_ids(con, TODAY)
    old = owner.post("/treatments", data={"cow_id": cid, "drug": "Vit B",
                                          "treated_on": db.iso(TODAY - timedelta(days=30)),
                                          "withhold_days": 2})
    assert "Treatment recorded" in old.headers["x-toast"]
    assert owner.post("/treatments", data={"cow_id": 999999, "drug": "x",
                                           "treated_on": db.iso(TODAY)}).status_code == 404
    assert "Oxytet" in owner.get("/treatments").text


# ── breeding → calving ──────────────────────────────────────────────────────

def test_breeding_due_date_and_calving_adds_calf(owner):
    cid = _cow(owner, "F47")
    bred = TODAY - timedelta(days=10)
    r = owner.post("/breeding", data={"cow_id": cid, "inseminated_on": db.iso(bred)})
    due = db.iso(bred + timedelta(days=db.GESTATION_DAYS))
    assert r.status_code == 200 and f"due {due}" in r.headers["x-toast"]
    assert owner.post("/breeding", data={"cow_id": cid, "inseminated_on": "x"}).status_code == 422
    assert owner.post("/breeding", data={"cow_id": 999999,
                                         "inseminated_on": db.iso(bred)}).status_code == 404
    with db.get_db() as con:
        bid = con.execute("SELECT id FROM breedings WHERE cow_id = ?", (cid,)).fetchone()["id"]
    assert owner.post(f"/breeding/{bid}/outcome", data={"outcome": "maybe"}).status_code == 422
    assert owner.post("/breeding/999999/outcome", data={"outcome": "open"}).status_code == 404
    assert owner.post(f"/breeding/{bid}/outcome", data={"outcome": "confirmed"}).status_code == 200
    cal = owner.post(f"/breeding/{bid}/outcome", data={"outcome": "calved", "calf_tag": "F47-1"})
    assert "calf #F47-1 added" in cal.headers["x-toast"]
    with db.get_db() as con:
        calf = con.execute("SELECT status FROM cows WHERE tag = 'F47-1'").fetchone()
    assert calf["status"] == "calf"
    again = owner.post(f"/breeding/{bid}/outcome", data={"outcome": "calved", "calf_tag": "F47-1"})
    assert again.status_code == 422
    assert "F47" in owner.get("/breeding").text


# ── sales ───────────────────────────────────────────────────────────────────

def test_sales_record_and_month_rollup(owner):
    r = owner.post("/sales", data={"collected_on": db.iso(TODAY), "litres": "20",
                                   "price_per_litre": "45"})
    assert r.status_code == 200 and "Rs 900.00" in r.headers["x-toast"]
    assert owner.post("/sales", data={"collected_on": db.iso(TODAY), "litres": "a",
                                      "price_per_litre": "1"}).status_code == 422
    assert owner.post("/sales", data={"collected_on": db.iso(TODAY), "litres": "0",
                                      "price_per_litre": "45"}).status_code == 422
    assert owner.get("/sales").status_code == 200


# ── calendar feed, pages, account, team ─────────────────────────────────────

def test_calendar_feed_by_secret_token(owner):
    r = owner.get("/calendar.ics", follow_redirects=False)
    assert r.status_code == 303
    feed = owner.get(r.headers["location"])
    assert feed.status_code == 200 and feed.text.startswith("BEGIN:VCALENDAR")
    assert "Milk OK again: #F46" in feed.text   # the 120-day withholding above
    assert TestClient(main.app).get("/calendar/wrong-token.ics").status_code == 404


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
