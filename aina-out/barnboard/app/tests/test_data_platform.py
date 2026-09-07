"""Data-platform tests (D6.3) — the open data contracts (D1) and the
inference path (D4/D5), same throwaway-DB pattern as test_barnboard.py.

Run:  cd app && .venv/bin/python -m pytest -q
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "test.db"))

from app import db, main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

HUB = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(HUB / "tools"))
import train_models  # noqa: E402

FEED_TOKEN = "test-feed-token-abc123"


@pytest.fixture(scope="module")
def client():
    db.init_db()
    with db.get_db() as con:
        if not db.has_users(con):
            db.create_user(con, "tester", "testpass123", role="owner", approved=True)
        db.set_setting(con, "feed_token", FEED_TOKEN)
        con.execute("INSERT OR IGNORE INTO cows (id, tag, name, breed, status) "
                    "VALUES (1, 'T1', 'Testcow', 'Gir', 'milking')")
        con.execute("INSERT OR IGNORE INTO milk_logs (cow_id, log_date, session, litres) "
                    "VALUES (1, '2026-09-01', 'AM', 10.5)")
    return TestClient(main.app)


# ── D1: open data contracts ────────────────────────────────────────────────

def test_api_requires_auth(client):
    r = client.get("/api/v1/milk_logs.json")
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_api_token_auth_and_envelope(client):
    r = client.get(f"/api/v1/milk_logs.json?token={FEED_TOKEN}")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == main.DATA_SCHEMA_VERSION
    assert body["table"] == "milk_logs"
    assert body["row_count"] == len(body["rows"]) >= 1


def test_api_bearer_header(client):
    r = client.get("/api/v1/cows.json", headers={"Authorization": f"Bearer {FEED_TOKEN}"})
    assert r.status_code == 200


def test_api_rejects_non_whitelisted(client):
    r = client.get(f"/api/v1/users.json?token={FEED_TOKEN}")
    assert r.status_code == 404


def test_schema_matches_pragma(client):
    r = client.get(f"/api/v1/schema?token={FEED_TOKEN}")
    assert r.status_code == 200
    tables = r.json()["tables"]
    with db.get_db() as con:
        for t in db.EXPORT_TABLES:
            live = [c[1] for c in con.execute(f"PRAGMA table_info({t})").fetchall()]
            assert [c["name"] for c in tables[t]] == live


# ── D4/D5: model logic + inference serving ─────────────────────────────────

def _fake_artifact(tmpdir: str, version: str, level: float) -> None:
    d = Path(tmpdir) / "yield_forecast" / version
    d.mkdir(parents=True, exist_ok=True)
    (d / "params.json").write_text(json.dumps({
        "model": "yield_forecast", "version": version, "damp": 0.92,
        "cows": {"1": {"tag": "T1", "breed": "Gir", "level": level,
                       "trend": 0.0, "trained_through": "2026-09-01", "n_days": 10}}}))
    (Path(tmpdir) / "yield_forecast" / "LATEST").write_text(version + "\n")


def test_predict_endpoint_and_hot_reload(client, monkeypatch):
    mdir = tempfile.mkdtemp()
    monkeypatch.setattr(main, "MODELS_DIR", mdir)
    _fake_artifact(mdir, "v1", level=20.0)
    r = client.get(f"/api/v1/predict/yield/1?token={FEED_TOKEN}")
    assert r.status_code == 200
    body = r.json()
    assert body["model_version"] == "v1"
    assert len(body["forecast"]) == 7
    assert body["forecast"][0]["litres"] == 20.0
    # unknown cow
    assert client.get(f"/api/v1/predict/yield/99?token={FEED_TOKEN}").status_code == 404
    # bump the version file only -> new numbers, no restart
    _fake_artifact(mdir, "v2", level=25.0)
    body2 = client.get(f"/api/v1/predict/yield/1?token={FEED_TOKEN}").json()
    assert body2["model_version"] == "v2"
    assert body2["forecast"][0]["litres"] == 25.0


def test_holt_beats_flat_on_trending_series():
    values = [30 - 0.5 * i for i in range(15)]  # steady decliner
    level, trend = train_models.holt_fit(values)
    pred = train_models.holt_forecast(level, trend, 3)
    actual = [30 - 0.5 * (15 + i) for i in range(3)]
    mae_model = sum(abs(a - p) for a, p in zip(actual, pred)) / 3
    mae_naive = sum(abs(a - values[-1]) for a in actual) / 3
    assert mae_model < mae_naive


def test_incomplete_cow_days_excluded(tmp_path):
    import sqlite3
    g = tmp_path / "gold.db"
    con = sqlite3.connect(g)
    con.execute("CREATE TABLE agg_milk_cow_daily "
                "(cow_id, tag, breed, log_date_day, litres, milk_logs_count)")
    rows = [(1, "T1", "Gir", f"2026-08-{d:02d}", 20.0, 2) for d in range(1, 15)]
    rows.append((1, "T1", "Gir", "2026-08-15", 9.0, 1))  # half-logged day
    con.executemany("INSERT INTO agg_milk_cow_daily VALUES (?,?,?,?,?,?)", rows)
    con.commit(); con.close()
    cows = train_models.load_series(str(g))
    days = cows[1]["days"]
    assert len(days) == 14 and all(l == 20.0 for _, l in days)


def test_revenue_projection_within_target():
    rev = train_models.revenue_projection(str(HUB))
    assert "abs_pct_error" in rev and rev["abs_pct_error"] < 15
