# MilkPost

MilkPost is a tool for small dairy farms in India. It keeps the list of cows,
the milk logs for each day, and the treatments with the time to hold back the
milk. It also keeps breeding, calving and milk sales. It gives a yield forecast
and a metrics API with governed definitions. It uses FastAPI, HTMX and SQLite,
in English and Telugu.

Live: https://milkpost.ajaykongala.online

> This repository is a mirror. You can only read it. The script
> `tools/mirror_repos.sh milkpost` makes it from the private hub. Make all
> changes in the hub, not here.

## Layout

| Path | What it holds |
| --- | --- |
| `aina-out/barnboard/app/` | The app: `app/main.py` (routes), `app/db.py` (SQLite schema and queries), `templates/`, `static/`, `tests/` |
| `aina-out/barnboard/docs/` | The first build documents (brief, SOW, PRD, dev notes, ops runbook) |
| `api/index.py` | Vercel entry point: it puts the app behind the settings of the hosted demo |
| `data-team-out/barnboard/`, `semantic-metrics/`, `data/` | Data platform: bronze/silver/gold layers and governed metric definitions |
| `models/`, `tools/train_models.py` | Yield-forecast model artifacts and the trainer (CI checks that it is still better than a naive baseline) |
| `betadoc-data/` | The documentation site for clients |
| `phasedoc-*/` | Internal build trackers, one per arc of work |
| `requirements.txt`, `requirements.lock` | Top-level pins (what Vercel installs) and the hash-locked full set |
| `package.json`, `vitest.config.mjs`, `stryker.config.json` | Tests and mutation testing for the browser JS (`static/js/ui.js`); the deploy does not include these files |

## Run locally

```bash
cd aina-out/barnboard/app
python3 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r ../../../requirements.lock
BARNBOARD_SEED=1 uvicorn app.main:app --port 8000
```

<!-- ste:strict -->
Open http://localhost:8000. When you open the app for the first time, create the owner account.
<!-- ste:end -->

## Tests

```bash
cd aina-out/barnboard/app
pip install pytest pytest-cov httpx mypy
mypy --ignore-missing-imports -p app
python -m pytest -q --cov=app --cov-report=xml:coverage.xml
```

CI (`.github/workflows/milkpost.yml`) runs mypy first. Then it runs the tests.
The tests must cover 100% of the lines. CI also compares the `coverage.xml` file
in the repository with a new run (`check_coverage.py`). If the two numbers are
more than one point apart, CI stops. Thus, when you change tests or code, run
the last command above again and commit the new file. Last, CI runs
`tools/train_models.py`. This step fails if the forecast is not better than the
naive baseline.

The browser JS has its own job (Node 24):

```bash
npm ci
npx vitest run      # unit tests for static/js/ui.js
npx stryker run     # mutation testing; fails below an 80% mutation score
```

## Deploy

<!-- ste:strict -->
- Deploy from the hub root with the Vercel CLI: `vercel deploy --prod --yes`.
- A push does not deploy.
<!-- ste:end -->
