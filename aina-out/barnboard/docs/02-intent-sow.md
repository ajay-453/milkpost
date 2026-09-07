# Barnboard — Intent & Statement of Work

*Stage 2 of the AiNa App Factory pipeline · engine: local Claude*

## Domain analysis

**Domain:** small-holder dairy farming (owner-operated, 30–150 milking head).

**Dynamics that shape the build:**
- The workday is anchored by two immovable events — morning and evening milking. Any tool must fit *inside* those windows, not add a third one.
- The costliest errors are **omissions**, not mistakes: milk from a treated cow reaching the tank, a missed dry-off, an unnoticed yield decline. The product's value is in *warnings*, not records.
- Data entry happens standing in a barn with wet or gloved hands on a phone; the evening desk session is for review, not entry.
- Milk withholding after antibiotic treatment is a regulated food-safety obligation everywhere; the *rules* vary by country and drug, but the *mechanism* (a per-treatment withholding window) is universal.
- Cash flow is simple and rhythmic: a collection tanker arrives every 1–3 days; price per litre is known at collection.

**What downstream stages must honor:** speed-of-logging is existential (beat the notebook or die), and the withholding alert must be impossible to miss.

## Scope of work

**Executive summary:** Build a single-service, server-rendered web app that is the farm's daily command center: herd register, twice-daily milk logging, treatment/withholding tracking, breeding countdowns, milk sales, and a calendar feed for reminders. One Docker container, one SQLite file, zero external services.

**Impact case:** Primary beneficiary is the owner-operator — one prevented tanker contamination (four-figure loss) or one early-caught mastitis case pays for the tool many times over; ~2 hrs/week of bookkeeping eliminated. Secondary: the milk buyer (fewer quality incidents) and the vet (a clean treatment history on arrival). Post-launch success metrics: milk logged ≥ 12 of 14 sessions/week; zero withholding incidents; alerts acknowledged within a day.

**Longevity verdict: GREEN.** Dairy farming is not being disrupted in 36 months; the domain's digitization gap is chronic. Defensibility is low (it's a CRUD app) but irrelevant for a self-hosted internal tool. Kill criteria: if logging takes >15 s/cow in practice, or the farmer reverts to the notebook within a month, rescope the entry flow before adding anything else.

**Dependencies:** none external — no APIs, no vendors, no PII beyond the farm's own operational data (GDPR-trivial: self-hosted, farmer owns the file). Distribution = the farmer's own server/VPS. Critical path: nothing blocks; the only customer input needed is answers to the braindoc's open questions (defaults assumed).

## Variants

### Variant 1: Lean (tier_lean)

**Budget band (USD):** 0 – 500
**Engineer-weeks:** 1
**Ops complexity:** low
**Recommended stack family:** fastapi+sqlite
**Target scale:** single farm, 1–3 users, 30–150 cows

**Tradeoffs:**
- Ships everything in the braindoc's V1 scope: herd, milk, treatments + withholding alerts, breeding countdowns, sales, iCal feed, CSV export
- No login (deploy behind LAN/VPN/firewall); auth documented as the first V2 item
- SQLite + one container = trivial ops, one-file backup
- Gives up: multi-farm, hardware integration, notifications beyond the calendar feed

**Kill criteria:**
- The farm must be internet-exposed to untrusted users on day one (needs auth → Recommended)
- More than ~5 concurrent staff logging simultaneously

### Variant 2: Recommended (tier_recommended)

**Budget band (USD):** 500 – 2,000
**Engineer-weeks:** 2–3
**Ops complexity:** low
**Recommended stack family:** fastapi+sqlite
**Target scale:** single farm, up to 10 users

**Tradeoffs:**
- Everything in Lean, plus session-cookie auth with per-person accounts, CSV *import* for existing records, automated nightly DB backup, and a printable monthly report
- Still one container + SQLite; ops stays trivial
- Gives up: multi-farm, parlour hardware integration

**Kill criteria:**
- Farm grows past ~300 head or adds a second site (needs Postgres + multi-tenant → Hardened)

### Variant 3: Hardened (tier_hardened)

**Budget band (USD):** 5,000 – 15,000
**Engineer-weeks:** 6–8
**Ops complexity:** medium
**Recommended stack family:** fastapi + managed Postgres
**Target scale:** multi-farm co-op, 10–50 users

**Tradeoffs:**
- Multi-tenant, role-based access, audit log, milk-meter CSV ingestion, co-op reporting
- Requires managed Postgres, real observability, and a support commitment
- Gives up: the one-afternoon deployability that makes Lean attractive

**Kill criteria:**
- No second farm actually committed — building multi-tenant for one farm is pure waste
- Budget under $5k

### Recommended variant: tier_lean

This build is executing autonomously with no stated budget; Lean delivers every high-impact feature in the braindoc within the AiNa session itself, and its omissions (auth, import) are cleanly additive later.

### Open questions / risks

- Litres assumed; confirm unit before deployment in a gallon market
- No auth in Lean — the deployment MUST sit behind a firewall/VPN; this is documented, not optional
- Withholding days are user-entered per treatment; the app deliberately does not encode drug rules
- Existing records: starting fresh assumed; export exists from day one
- Adoption hinges entirely on the milk-log screen's speed — treat it as the product
