"""Herd and milk log: adding cows, status changes, milk entries, and cow names that look like markup.

Run:  cd app && .venv/bin/python -m pytest -q   (fixtures: conftest.py)
"""

from app import db
from conftest import _cow, TODAY


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


def test_palette_json_cannot_close_its_script_tag(authed):
    import json
    import re
    evil = "</script><script>alert(1)</script>"
    with db.get_db() as con:
        con.execute("DELETE FROM cows WHERE tag = 'XSS1'")
        con.execute("INSERT INTO cows (tag, name, status) VALUES ('XSS1', ?, 'milking')", (evil,))
    html = authed.get("/").text
    assert evil not in html
    blob = re.search(r'<script id="palette-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    assert any(evil in it["label"] for it in json.loads(blob))   # same data after parsing
    with db.get_db() as con:
        con.execute("DELETE FROM cows WHERE tag = 'XSS1'")
