"""Treatments with milk withholding, breeding to calving, and the calendar feed built from them.

Run:  cd app && .venv/bin/python -m pytest -q   (fixtures: conftest.py)
"""

from datetime import timedelta

from app import db, main
from fastapi.testclient import TestClient
from conftest import _cow, TODAY


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


def test_calendar_feed_by_secret_token(owner):
    r = owner.get("/calendar.ics", follow_redirects=False)
    assert r.status_code == 303
    feed = owner.get(r.headers["location"])
    assert feed.status_code == 200 and feed.text.startswith("BEGIN:VCALENDAR")
    assert "Milk OK again: #F46" in feed.text   # the 120-day withholding above
    assert TestClient(main.app).get("/calendar/wrong-token.ics").status_code == 404


def test_treatment_needs_a_valid_date(owner):
    cid = _cow(owner, "F4T")
    r = owner.post("/treatments", data={"cow_id": cid, "drug": "Oxytet", "treated_on": "someday"})
    assert r.status_code == 422


def _logs(con, cow_id, days, litres_by_day):
    for d in days:
        for sess in ("AM", "PM"):
            con.execute("INSERT INTO milk_logs (cow_id, log_date, session, litres) VALUES (?,?,?,?)",
                        (cow_id, db.iso(d), sess, litres_by_day(d)))


def test_heat_watch_flags_a_return_to_heat_after_a_lost_insemination(owner):
    """A failed AI is recorded as 'lost'; ~21 days later a one-day milk dip = heat."""
    from datetime import timedelta
    cid = _cow(owner, "F4H")                     # dips today, on the 21-day cycle
    sparse = _cow(owner, "F4H2")                 # same cycle, but no log today and too little history
    steady = _cow(owner, "F4H3")                 # same cycle, no dip: never flagged
    owner.post("/cows", data={"tag": "F4H4"})    # not a lost AI: ignored
    bred = TODAY - timedelta(days=db.HEAT_CYCLE_DAYS)
    with db.get_db() as con:
        for c in (cid, sparse, steady):
            con.execute("INSERT INTO breedings (cow_id, inseminated_on, due_date, outcome) "
                        "VALUES (?,?,?, 'lost')", (c, db.iso(bred), db.iso(bred + timedelta(days=283))))
        span = [TODAY - timedelta(days=n) for n in range(10, -1, -1)]
        _logs(con, cid, span, lambda d: 8.0 if d == TODAY else 10.0)
        _logs(con, steady, span, lambda d: 10.0)
        _logs(con, sparse, [TODAY - timedelta(days=1)], lambda d: 10.0)
        alerts = db.heat_watch(con, TODAY)
    assert [a["tag"] for a in alerts] == ["F4H"]
    a = alerts[0]
    assert a["heat_day"] == db.iso(TODAY) and a["cycle"] == 1 and a["dip_pct"] == 20
    assert a["next_expected"] == db.iso(TODAY + timedelta(days=db.HEAT_CYCLE_DAYS))
    assert "F4H" in owner.get("/").text            # surfaces on the dashboard


def test_calendar_has_calving_and_dry_off_for_confirmed_pregnancy(owner):
    from datetime import timedelta
    cid = _cow(owner, "F4C")
    due = TODAY + timedelta(days=db.DRY_OFF_BEFORE_DUE + 30)
    with db.get_db() as con:
        con.execute("INSERT INTO breedings (cow_id, inseminated_on, due_date, outcome) VALUES (?,?,?, 'confirmed')",
                    (cid, db.iso(due - timedelta(days=283)), db.iso(due)))
        token = db.feed_token(con)
    feed = owner.get(f"/calendar/{token}.ics").text
    assert "Calving due: #F4C" in feed and "Dry off: #F4C" in feed
    assert f"DTSTART;VALUE=DATE:{(due - timedelta(days=db.DRY_OFF_BEFORE_DUE)).strftime('%Y%m%d')}" in feed
