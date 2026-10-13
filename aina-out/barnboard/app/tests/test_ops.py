"""Operations: gzip, the JSON request log, and the Prometheus /metrics endpoint.

Run:  cd app && .venv/bin/python -m pytest -q   (fixtures: conftest.py)
"""

from app import db, main
from fastapi.testclient import TestClient


def test_gzip_on_pages(authed):
    r = authed.get("/", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


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


def test_metrics_needs_owner_or_token(authed, monkeypatch):
    authed.get("/api/v1/schema")
    anon = TestClient(main.app)
    assert anon.get("/metrics").status_code == 401
    monkeypatch.setenv("METRICS_TOKEN", "scrape-me")
    assert anon.get("/metrics", headers={"authorization": "Bearer wrong"}).status_code == 401
    r = anon.get("/metrics", headers={"authorization": "Bearer scrape-me"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert 'http_requests_total{handler="/api/v1/schema"' in r.text
    assert authed.get("/metrics").status_code == 200          # owner session
    with db.get_db() as con:
        if not con.execute("SELECT 1 FROM users WHERE username='helper1'").fetchone():
            db.create_user(con, "helper1", "helperpass1", role="helper", approved=True)
    helper = TestClient(main.app)
    helper.post("/login", data={"username": "helper1", "password": "helperpass1"},
                headers={"x-forwarded-for": "203.0.113.61"})
    assert helper.get("/metrics").status_code == 401           # helpers can't


def test_unhandled_error_is_logged_as_json(authed, monkeypatch):
    import json
    import logging
    lines = []

    class Grab(logging.Handler):
        def emit(self, record):
            lines.append(json.loads(main.access_log.handlers[0].format(record)))

    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(main.db, "daily_totals", boom)
    h = Grab()
    main.access_log.addHandler(h)
    try:
        c = TestClient(main.app, raise_server_exceptions=False)
        c.cookies.update(authed.cookies)
        assert c.get("/").status_code == 500
    finally:
        main.access_log.removeHandler(h)
    err = [ln for ln in lines if ln["level"] == "ERROR"][0]
    assert err["message"] == "unhandled error" and "disk on fire" in err["exc_info"]
    req = [ln for ln in lines if ln["message"] == "request"][0]
    assert req["status"] == 500 and req["request_id"] == err["request_id"]
