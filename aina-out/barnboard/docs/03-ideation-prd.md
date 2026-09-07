# Barnboard — Product Requirements Document

*Stage 3 of the AiNa App Factory pipeline · engine: local Claude · variant: tier_lean*

### Name

Barnboard

### Elevator pitch

Barnboard is a self-hosted daily command center for a small dairy farm: log milk in seconds, get warned before treated milk reaches the tank, and see calvings and dry-offs coming on your own phone calendar. It replaces the pocket notebook and the weekend spreadsheet with one screen the farmer trusts.

### Chosen variant

`tier_lean`

### Tech stack (one-line)

Python 3.12 + FastAPI · Jinja2 + HTMX (server-rendered, golden starter design system) · SQLite (stdlib sqlite3, no ORM) · Docker on VPS/home server

**Architectural posture:** monolith, server-rendered, mobile-first. All interactivity via HTMX fragment swaps — no client build step, no JSON SPA layer. Pages must stay small enough for barn-grade connectivity. **Non-obvious constraint flagged for Dev:** the withholding alert must be computed at *read time* from treatment dates (never a stored boolean that can go stale) and must appear on the dashboard AND the milk-log screen for the affected cow.

**Auth:** none in V1 — single-farm deployment behind LAN/VPN/firewall. Stated on every ops document. **Skipped on purpose:** SQLAlchemy (stdlib sqlite3 keeps deps identical to the golden starter), JSON API layer (HTMX consumes HTML fragments), Postgres (one farm = one file).

### Features

- **Herd register** [P0]
  - what: CRUD for cattle — tag, name, breed, DOB, status (calf/heifer/milking/dry/sold), notes.
  - acceptance: create a cow via form → appears in herd table; edit status inline; sold/dead cows hidden from logging flows but retained in history; auto-computed age shown.
  - depends on: `cows` · `/cows` routes · Herd page

- **Fast milk logging** [P0]
  - what: one screen listing all milking cows for today's AM or PM session, each with a yield input, saved per-row without page reload.
  - acceptance: logging one cow takes one tap + one number (HTMX row swap, no reload); previous session's value shown as placeholder; session totals update live; a cow under active withholding shows a red DO-NOT-TANK marker in the row.
  - depends on: `milk_logs`, `cows`, `treatments` · `/milk` routes · Milk Log page

- **Treatments & withholding alerts** [P0]
  - what: record a treatment (cow, drug, date, withholding days) → the app computes the clear-date and raises an unmissable alert everywhere it matters until it passes.
  - acceptance: withholding end = treatment date + days, computed at read time; active withholdings show as a red banner on the dashboard listing cow + clear date; the cow's milk-log row is visually flagged; alert disappears automatically once the date passes.
  - depends on: `treatments`, `cows` · `/treatments` routes · Health page, Dashboard

- **Breeding & calving countdown** [P0]
  - what: record inseminations; due date auto-computed at +283 days (overridable); upcoming calvings surface as countdowns.
  - acceptance: insemination saved → due date computed and shown; calvings within 30 days appear on dashboard with days-remaining; recording a calving creates the calf as a new cow in one step.
  - depends on: `breedings`, `cows` · `/breeding` routes · Breeding page, Dashboard

- **Dashboard with yield-drop detection** [P0]
  - what: today's totals, 14-day production trend (server-rendered SVG), active alerts (withholding, calving ≤30d, yield drops), herd counts.
  - acceptance: totals and trend computed from real logs; a cow whose latest daily total is >20% below her own trailing 7-day average is flagged; empty DB shows a helpful onboarding state, not zeros.
  - depends on: all entities · `/` · Dashboard page

- **iCal reminder feed** [P0]
  - what: `/calendar.ics` serving withholding-end, calving-due, and dry-off events; farmer subscribes once in any calendar app.
  - acceptance: feed is valid ICS (parses in a calendar app); contains one event per active withholding clear-date and expected calving; URL works unauthenticated for calendar-app polling.
  - depends on: `treatments`, `breedings` · `/calendar.ics`

- **Milk sales log** [P0]
  - what: record collections (date, litres, price/litre) → monthly revenue and price trend.
  - acceptance: collection saved → month's revenue total updates; sales page shows recent collections and a monthly summary.
  - depends on: `sales` · `/sales` routes · Sales page

- **CSV export** [P0]
  - what: every table downloadable as CSV.
  - acceptance: `/export/{table}.csv` returns well-formed CSV with headers for cows, milk_logs, treatments, breedings, sales.
  - depends on: all entities · `/export` routes

- **Command palette + dark mode** [P1]
  - what: Ctrl+K palette for jump-to-page and jump-to-cow; theme toggle persisted in localStorage.
  - acceptance: palette opens on Ctrl+K, filters as you type, Enter navigates; dark mode persists across reloads.

- **Demo seed data** [P1]
  - what: `--seed` path populating a realistic 12-cow herd with 3 weeks of logs so every screen demos meaningfully.
  - acceptance: fresh DB + seed → dashboard shows trend, one active withholding, one upcoming calving.

- **Auth, CSV import, printable monthly report** [P2 — tier_recommended items, deliberately deferred]

### Data model summary

- **cows** — the herd register; everything references `cow_id` (tag TEXT unique, name, breed, dob, status, notes)
- **milk_logs** — one row per cow/date/session(AM|PM) with litres REAL; UNIQUE(cow_id, log_date, session) so re-logging updates
- **treatments** — cow_id, drug, treated_on, withhold_days, notes; clear-date derived, never stored
- **breedings** — cow_id, inseminated_on, due_date (default +283d), outcome (open/confirmed/calved), calf_cow_id nullable
- **sales** — collected_on, litres, price_per_litre, notes

Indices that matter: `milk_logs(log_date)`, `milk_logs(cow_id, log_date)`, `treatments(treated_on)`. Migration strategy: `CREATE TABLE IF NOT EXISTS` at boot — adequate for V1's additive schema.

### API contract summary

Server-rendered pages + HTMX fragment endpoints (HTML in/out, form-encoded in — no JSON layer): `/` (dashboard) · `/cows` · `/milk` · `/treatments` · `/breeding` · `/sales` · `/export/{table}.csv` · `/calendar.ics` · `/roadmap` · `/healthz`. Errors: user-facing validation via inline fragment + `X-Toast` header (ASCII-only); 404 for missing entities; details logged server-side.

### NFR highlights

1. **Logging speed is the product:** milk-log row save p95 < 300 ms server-side; one tap + one number per cow.
2. **Withholding correctness:** computed at read time from dates; shown on dashboard AND milk-log rows; no cached/stale state.
3. **Barn-grade pages:** server-rendered, no CDN dependencies at runtime except Google Fonts (degrades gracefully); htmx bundled locally.
4. **Data ownership:** one SQLite file; CSV export of everything; nothing leaves the server.
5. **Deployment posture:** no auth ⇒ MUST be firewalled/VPN'd; stated in README and ops runbook.

### Open questions

Carried from SOW with assumed defaults: litres (metric) · single-user/no-auth · fresh start, no import · flat price per collection · English UI, hardcoded.

### What's NOT in V1 (deliberate)

- Authentication and user accounts — deployment-posture note instead; first V2 item
- Multi-farm/multi-tenant — one instance per farm
- Parlour/milk-meter hardware integration — manual entry is the scope
- Feed/cost accounting — revenue side only
- Push/SMS notifications — the iCal feed is the notification system
