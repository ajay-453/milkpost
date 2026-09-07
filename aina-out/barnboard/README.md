# Barnboard — AiNa App Factory build

**Problem statement:** "Build a dairy farm" web app — modern, very low
complexity, high impact on the end user.

**Result:** Barnboard, a self-hosted dairy farm command center. Verified
running end-to-end during the build.

## What's in this package

```
docs/                     the document set (the headline deliverable)
  01-braindoc.md          problem, users, scope, economics, risks, phasing
  02-intent-sow.md        domain analysis + 3 costed variants (lean chosen)
  03-ideation-prd.md      PRD: features w/ acceptance criteria, data model, NFRs
  04-dev-notes.md         architecture, decisions, live verification log
  07-marketing.md         brand strategy + messaging
  09-ops-runbook.md       deploy, monitoring, backup, incidents, go-live checklist
app/                      the working codebase (FastAPI + HTMX + SQLite)
  README.md               quickstart (venv or Docker), feature tour, config
  marketing.html          self-contained landing page (open in a browser)
```

## Try it in 60 seconds

```bash
cd app
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
BARNBOARD_SEED=1 uvicorn app.main:app --port 8000
```

Open http://localhost:8000 — the demo herd shows an active DO-NOT-TANK
withholding, a yield-drop alert, a calving countdown, and 3 weeks of
production history. Press **Ctrl+K** for the command palette; subscribe to
`/calendar.ics` from a calendar app to see the reminder feed.

> ⚠️ V1 has no login — run it on your LAN or behind a VPN. See the ops runbook.
