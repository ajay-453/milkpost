"""CSV exports and the /api/v1 JSON API: whitelists, schema, caching, OpenAPI documentation.

Run:  cd app && .venv/bin/python -m pytest -q   (fixtures: conftest.py)
"""

from app import db, main


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


def test_metric_api_errors(authed, monkeypatch, tmp_path):
    (tmp_path / "semantic" / "metrics" / "broken.json").mkdir(parents=True)   # unreadable "file"
    monkeypatch.setattr(main, "RUN_DIR", str(tmp_path))
    assert main._metric_defs() == {}
    defs = {"m": {"metric": "m", "aggregation": "median", "dimensions": ["cow"]}}
    monkeypatch.setattr(main, "_metric_defs", lambda: defs)
    assert authed.get("/api/v1/metrics/m", params={"by": "breed"}).status_code == 422   # undeclared
    r = authed.get("/api/v1/metrics/m")
    assert r.status_code == 422 and r.json()["error"] == "metric not computable"


def test_export_csv_with_rows(authed):
    with db.get_db() as con:
        con.execute("INSERT INTO sales (collected_on, litres, price_per_litre, notes) "
                    "VALUES ('2026-09-01', 12.5, 44.0, 'csv test')")
    lines = authed.get("/export/sales.csv").text.strip().splitlines()
    assert lines[0].split(",")[:3] == ["id", "collected_on", "litres"]
    assert any(ln.endswith(",csv test") and "12.5" in ln for ln in lines[1:])


def test_metric_without_gold_layer_is_503(authed, monkeypatch, tmp_path):
    defs = {"m": {"metric": "m", "aggregation": "sum", "measure": "litres",
                  "rollups": {"daily": "gold.daily_milk"}}}
    monkeypatch.setattr(main, "_metric_defs", lambda: defs)
    monkeypatch.setattr(main, "RUN_DIR", str(tmp_path))
    r = authed.get("/api/v1/metrics/m")
    assert r.status_code == 503 and r.json()["error"] == "gold layer unavailable"
