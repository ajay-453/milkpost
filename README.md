# MilkPost

A dairy-farm command center for small Indian farms: herd register, daily milk
logs, treatments with milk-withholding countdowns, breeding and calving, milk
sales, a yield forecast, and a governed metrics API. FastAPI + HTMX + SQLite,
English and Telugu.

Live: https://milkpost.ajaykongala.online

> This repository is a read-only mirror, cut from the private working hub with
> `tools/mirror_repos.sh milkpost`. Changes are made in the hub, never here.

## Layout

| Path | What it holds |
| --- | --- |
| `aina-out/barnboard/app/` | The app: `app/main.py` (routes), `app/db.py` (SQLite schema and queries), `templates/`, `static/`, `tests/` |
| `aina-out/barnboard/docs/` | Original build documents (brief, SOW, PRD, dev notes, ops runbook) |
| `api/index.py` | Vercel entry point: wraps the app with the hosted-demo settings |
| `data-team-out/barnboard/`, `semantic-metrics/`, `data/` | Data platform: bronze/silver/gold layers and governed metric definitions |
| `models/`, `tools/train_models.py` | Yield-forecast model artifacts and the trainer (CI checks it still beats a naive baseline) |
| `betadoc-data/` | The client-facing documentation site |
| `phasedoc-*/` | Internal build trackers, one per arc of work |
| `requirements.txt`, `requirements.lock` | Top-level pins (what Vercel installs) and the hash-locked full set |

## Run locally

```bash
cd aina-out/barnboard/app
python3 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r ../../../requirements.lock
BARNBOARD_SEED=1 uvicorn app.main:app --port 8000
```

Open http://localhost:8000. The first visit offers to create the owner account.

## Tests

```bash
cd aina-out/barnboard/app
pip install pytest pytest-cov httpx mypy
mypy --ignore-missing-imports -p app
python -m pytest -q --cov=app --cov-report=xml:coverage.xml
```

CI (`.github/workflows/milkpost.yml`) runs mypy, then the suite with a 75%
coverage floor. It also checks that the committed `coverage.xml` is within one
point of a fresh run (`check_coverage.py`), so refresh it with the last command
above whenever tests or code change. Finally it runs `tools/train_models.py`,
which fails if the forecast stops beating the naive baseline.

## Deploy

Vercel, from the hub root with the CLI (`vercel deploy --prod --yes`). Pushes
do not deploy.
