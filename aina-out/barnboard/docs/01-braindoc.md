# Barnboard — Braindoc

*Stage 1 of the AiNa App Factory pipeline · 2026-09-03 · engine: local Claude*

### Summary

Barnboard is a self-hosted web app that runs a small dairy farm's daily operations: the herd register, twice-daily milk logging, health treatments with milk-withholding safety alerts, breeding/calving countdowns, and milk sales — all from a phone in the barn. It replaces the paper notebook + Excel + memory combination that loses small farms real money through forgotten withdrawal periods, missed calvings, and undetected yield drops.

### The problem

The owner-operator of a 30–150 cow dairy farm tracks everything in a pocket notebook and a weekend Excel session. The costs are concrete: milk from a cow under antibiotic treatment accidentally reaching the bulk tank can cause an entire tanker load to be rejected (a four-figure loss and a contract strike); a missed dry-off or calving date risks cow and calf health; a gradual per-cow yield drop — the earliest signal of mastitis or lameness — is invisible in a notebook. Nothing they use warns them about anything.

### Users

**Primary user:** Owner-operator of a small/mid dairy farm (30–150 milking cows), no office staff. JTBD: "record what happened in the barn in under 10 seconds, and be warned before something costs me money." Context: phone with wet/gloved hands in the barn twice daily; laptop occasionally in the evening. Success signal: stops carrying the notebook; checks the dashboard before letting milk into the tank.

**Secondary user:** Family member or single farmhand who logs milking when the owner is away. Same interface, no separate role system needed.

**Anti-personas:**
- Industrial dairy operations (1,000+ head) — they need parlour-hardware integration and ERP; building for them adds integration complexity that kills the 10-second logging flow.
- Dairy co-op administrators — multi-farm aggregation is a different product.
- Veterinary practices — they need clinical records depth, not farm ops.

### V1 scope

**In:**
- Register and manage cattle (tag, name, breed, DOB, status: calf/heifer/milking/dry/sold) — the spine every other feature hangs on
- Log milk per cow, AM/PM, via a one-screen tap-through flow — the daily habit; must beat the notebook on speed
- Record health treatments with a withholding period → a loud, unmissable "DO NOT TANK" banner until the withdrawal date passes — the highest-impact feature in the app
- Record inseminations → auto-computed due date (~283 days) with calving countdown alerts
- Dashboard: today's milk total, 14-day trend chart, active alerts, per-cow yield-drop detection (7-day average falling >20%)
- Subscribable iCal feed (`/calendar.ics`) — withdrawal-end, calving-due, and dry-off reminders appear in the farmer's own phone calendar with zero notification infrastructure
- Record milk collections/sales (litres, price) → monthly revenue view
- CSV export of every table — the farmer's data is the farmer's data

**Out:**
- Multi-farm / multi-tenant support — single farm per instance; V2 if traction
- Parlour hardware / milk-meter integration — industrial-tier complexity
- Feed and cost accounting — a separate discipline; revenue-side only in V1
- Native mobile app — a responsive PWA-style web app covers barn usage
- SMS/push notifications — the iCal feed delivers reminders through the phone's own calendar at zero complexity and zero cost

### Economics

- **Build:** 1–2 engineer-weeks for V1 as scoped · fits a small-tool budget: **YES** (single service, SQLite, no third-party APIs)
- **Monthly infra:** €4–6 VPS or free on an existing home server; no external services, so that is the total
- **Value:** one prevented tanker rejection pays for years of hosting; ~2 hrs/week of Excel bookkeeping eliminated; early mastitis detection via yield-drop alerts protects the highest-value assets in the business
- **Payback:** first month of use, realistically the first prevented mistake

### Risks & dependencies

- Farmer's existing records live in a notebook/inconsistent Excel — mitigate with CSV import kept simple and optional; starting fresh from today is acceptable
- Barn connectivity is patchy — mitigate with a server-rendered, sub-50KB-per-page app that works on 2G-grade signal; no SPA bundle to download
- Withholding-period rules vary by drug and country — the app records what the vet/label says (days input by user) rather than encoding a drug database; a wrong hardcoded rule would be worse than none
- Adoption risk: if logging is slower than the notebook, the app dies — mitigate by making the milk-log screen the most optimized flow in the app (big tap targets, remembers last values, no page reloads)

### DevOps & Deployment

- **Hosting target:** any VPS or home server via the bundled Dockerfile (classifier profile: vps); `deploy_target=none` for this build — code + docs are the deliverable
- **Runtime + framework:** Python 3.12 · FastAPI · Jinja2 · HTMX (server-rendered)
- **Database & persistence:** SQLite single file (`barnboard.db`); backup = copy one file, cron-friendly
- **Secrets & config:** `APP_NAME`, `PORT`, `DB_PATH` — no auth keys or third-party secrets in V1
- **Observability:** uvicorn access/error logs to stdout (Docker captures them); `/healthz` endpoint for uptime checks; plan: add exception logging to file in Phase 2
- **CI/CD:** none required for V1 — `docker build && docker run`; git history is the release record
- **Rollback story:** re-run the previous image tag; DB is append-mostly so old code reads new data safely
- **Scaling envelope:** one farm's traffic (tens of requests/day) — SQLite + one uvicorn worker is comfortable to ~10k req/day, far beyond need

### Delivery

- **Phase 1 — Herd + Milk (days 1–3):** cattle CRUD, AM/PM milk logging, dashboard totals. *The farmer can retire the notebook by end of phase.*
- **Phase 2 — Safety + Breeding (days 4–6):** treatments with withholding alerts, insemination/calving tracking, iCal feed, yield-drop detection. *The farmer gets warned before a costly mistake by end of phase.*
- **Phase 3 — Money + Polish (days 7–10):** milk sales/revenue, CSV export, dark mode, command palette, roadmap page. *The farmer sees what the herd earns by end of phase.*

**Definition of done:** a cow can go register → milk logs → treatment → withholding alert → alert clears on date; dashboard shows real computed numbers; iCal feed validates in a calendar app; every page renders on a phone; app boots via `uvicorn` and passes `/healthz`.

### Open questions

- Q: Litres or gallons? — display unit affects every screen. *Assumed litres (metric); configurable constant in code.*
- Q: Single shared login or per-person accounts? — *Assumed single-user, no auth in V1 (LAN/VPS with firewall); auth is a documented V2 item.*
- Q: Existing data to import? — *Assumed starting fresh; CSV export exists from day one so data is never locked in.*
- Q: Milk pricing model (flat per litre vs. quality-adjusted)? — *Assumed flat price per collection, entered at logging time.*

### Assumptions made

- Herd size 30–150; single farm; single implicit user; metric units; English UI
- Withholding days are entered per treatment (from the vet/drug label), not derived from a drug database
- 283-day gestation default for calving date estimates (user can override)
- Phone-first usage; server-rendered pages acceptable everywhere
