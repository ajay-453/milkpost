"""Pure logic: Indian money format, withholding dates, password hashing, recovery answers, bound SQL names.

Run:  cd app && .venv/bin/python -m pytest -q   (fixtures: conftest.py)
"""

from datetime import date

import pytest

from app import db, main


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


def test_table_columns_binds_name(client):
    with db.get_db() as con:
        names = [c[1] for c in db.table_columns(con, "cows")]
        assert {"id", "tag"} <= set(names)
        assert db.table_columns(con, "cows; DROP TABLE cows") == []
    assert set(db.EXPORT_SELECT) == set(db.EXPORT_TABLES)


# ── internals reached only by unusual input (arc F6.1) ──────────────────────

def test_verify_password_rejects_malformed_hash():
    assert db.verify_password("x", "no-dollar-sign") is False


def test_inserted_id_refuses_a_missing_row_id():
    import pytest

    class NoRow:
        lastrowid = None
    with pytest.raises(RuntimeError):
        db.inserted_id(NoRow())


def test_reset_lock_minutes():
    from datetime import datetime, timedelta
    assert db.reset_locked_minutes({"reset_lock": None}) == 0
    assert db.reset_locked_minutes({"reset_lock": "not-a-date"}) == 0
    past = (datetime.now() - timedelta(minutes=5)).isoformat()
    assert db.reset_locked_minutes({"reset_lock": past}) == 0
    soon = (datetime.now() + timedelta(minutes=10, seconds=30)).isoformat()
    assert db.reset_locked_minutes({"reset_lock": soon}) == 11


def test_recovery_helpers_with_unknown_input(client):
    with db.get_db() as con:
        assert db.try_security_reset(con, "nobody-here", "x", "newpass123") == (False, "no_question")
        assert db.reset_user(con, None) is None
        assert db.consume_reset(con, "no-such-token", "newpass123") is False


def test_stateless_sessions(client, monkeypatch):
    """Serverless mode: the session is a signed token, no sessions row."""
    monkeypatch.setattr(db, "STATELESS", True)
    with db.get_db() as con:
        uid = con.execute("SELECT id FROM users WHERE username='tester'").fetchone()["id"]
        token = db.create_session(con, uid)
        assert con.execute("SELECT 1 FROM sessions WHERE token = ?", (token,)).fetchone() is None
        assert db.session_user(con, token)["id"] == uid
        assert db.session_user(con, token[:-2] + "xx") is None        # bad signature
        assert db.session_user(con, "%%%garbage") is None             # undecodable
        monkeypatch.setattr(db, "SESSION_DAYS", -1)
        assert db.session_user(con, db.create_session(con, uid)) is None   # expired


def test_old_users_table_is_migrated():
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, created_at TEXT)")
    con.executemany("INSERT INTO users (username, password_hash, created_at) VALUES (?, 'h', 'now')",
                    [("first",), ("second",)])
    db._migrate_users(con)
    rows = con.execute("SELECT username, role, approved, security_question FROM users ORDER BY id").fetchall()
    assert [(r["username"], r["role"], r["approved"]) for r in rows] == [("first", "owner", 1), ("second", "helper", 1)]
    assert rows[0]["security_question"] is None
    db._migrate_users(con)   # idempotent


def test_shared_guest_login_rejects_impossible_dates(client):
    with db.get_db() as con:
        pw = db._oc_guest_password(con, "guest-991399-abcd")
        assert db.authenticate(con, "guest-991399-abcd", pw) is None   # month 13


def test_script_json_escapes_markup():
    out = main._script_json({"label": "</script><b>&"})
    assert "<" not in out and ">" not in out and "&" not in out
    import json
    assert json.loads(out) == {"label": "</script><b>&"}


def test_golden_sql_shapes():
    g = main._golden_sql
    base = {"metric": "milk", "measure": "litres", "rollups": {"daily": "gold.daily_milk"}}
    assert g({**base, "aggregation": "sum"}, None) == 'SELECT sum("litres") AS "milk" FROM "daily_milk"'
    assert 'count("litres")' in g({**base, "aggregation": "count"}, None)
    assert "count(*)" in g({**base, "aggregation": "count", "measure": None}, None)
    assert 'avg("litres")' in g({**base, "aggregation": "avg"}, None)
    ratio = g({**base, "aggregation": "ratio", "numerator": "a", "denominator": "b"}, None)
    assert 'sum("a")*1.0/nullif(sum("b"),0)' in ratio
    assert "x + 1" in g({**base, "aggregation": "derived", "expression": "x + 1"}, None)
    assert g({**base, "aggregation": "median"}, None) is None
    assert g({"aggregation": "sum", "measure": "litres"}, None) is None          # no rollup table
    assert g({**base, "aggregation": "derived", "expression": ""}, None) is None


def test_svg_trend_empty():
    assert main._svg_trend([]) == ""
