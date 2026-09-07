# Data-team roles vs. project needs — assessment report (D0.4)

Internal, builders-facing. Written 2026-09-07 at the start of the Barnboard
Data Platform arc. This report measures each of the data-team skill's eight
roles against what this project actually needs, records what the first
pipeline run proved, and grounds the phase plan (see
[plan-of-record.md](plan-of-record.md), tracked live in the cockpit).

## 1. The project and its needs

velocity-hub's product is **barnboard**: a FastAPI + HTMX + SQLite herd
management app for an Indian smallholder dairy (12-cow demo herd, desi and
crossbred breeds, INR pricing). The user's mandate for this arc:

1. **Interoperable** — the data must be usable by other systems, in open
   formats, with stable contracts.
2. **Extensible** — new metrics, datasets, and models must be addable without
   engine changes.
3. **Utility on every environment/platform** — laptop, bare-metal VPS (PM2),
   containers; no dependency the smallest target can't carry.
4. **Model-ready data, properly researched** — free web data inventoried,
   licensed, and stored locally for training and inference.

What already exists (baseline audit): whitelisted CSV export; a Dockerfile
honoring `$PORT`; a Vercel serverless entry; PM2 supervision; four pinned
Python dependencies. What is missing: any JSON/machine-readable API, data
import, a versioned schema contract, reference datasets, models, and served
inference.

## 2. The first pipeline run (evidence)

The data-team spine ran 2026-09-07 over the five domain tables (auth tables
excluded as PII — the Architect's disposition): `data-team-out/barnboard/`
holds bronze/silver/gold, a semantic layer, reports, lineage, and a governance
envelope. Applying the analyst's judgment over gold/silver produced real
answers the auto-metrics could not:

- Top producer #104 (HF cross, 27.5 L/day); bottom #107 (Red Sindhi, 17.5).
- Herd daily average slipped ~5% across the 22-day window (237.0 → 225.2 L).
- Breed ranking: HF cross 26.6 > Murrah buffalo 25.0 > Jersey cross 21.5 >
  Gir 21.2 > Sahiwal 18.7 > Red Sindhi 17.5 L/cow/day.
- Sales: ₹196,135 over 4,643 L at an average ₹42.24/L.

The run also exposed the gap that shapes phase D2: the auto-synthesized
semantic layer summed `price_per_litre` (a ratio) — precisely what the
skill's own governance guard forbids. Metrics must be authored, not inferred.

## 3. Role-by-role: fit, verdict, and where it lands in the plan

| # | Role | Project need | Verdict | Phase |
|---|------|--------------|---------|-------|
| 1 | Data Architect | High — typed landing of app tables + reference datasets, PII disposition, catalog | **Adopt (ran)** — bronze + catalog produced; PII exclusion recorded | D0, D3 |
| 2 | Data Engineer | High — clean silver, modeled gold, lineage the models train on | **Adopt (ran)** — medallion built; idempotency to prove | D0, D2.3 |
| 3 | Data Designer | High — the auto-metrics are placeholders and one violates the governance guard | **Adopt, with authored metrics** — this is where extensibility is won | D2 |
| 4 | Data Analyst | High — management questions answered with receipts; feeds the farmer-facing story | **Adopt (ran, judgment applied)** | D0, D2 |
| 5 | BI Engineer | Low–medium — barnboard's own dashboard *is* the BI surface (server-rendered, role-scoped via owner/helper auth); a second dashboard stack would duplicate it | **Defer** — revisit only if multi-farm aggregation arrives | — |
| 6 | Data Scientist | High — yield forecasting, anomaly scoring, revenue projection are the arc's core value | **Adopt (in-repo)** — the plugin's `scientist` stage resolves but is not yet runnable in v1, so models are built in-repo on gold, honoring the same contracts | D4 |
| 7 | ML Engineer | High — models must serve inside the app on every platform with versioned, hot-reloadable artifacts | **Adopt (in-repo)** — same v1 caveat as scientist; serving lands in the app itself, no new service | D5 |
| 8 | Data SRE | Medium — k3s/k8s (the role's native habitat) is oversized for a single-file-DB farm app | **Right-size** — PM2 bare-metal + Docker image + pytest + GitHub; no Kubernetes | D6 |

Governance is not a row because it is not a stage: every phase inherits the
cross-cutting plane (lineage recorded per run, PII flags honored, the
never-sum-a-ratio guard enforced in D2, licenses tracked per dataset in D3).

## 4. Interoperability & platform assessment

**Contracts (D1).** The single biggest interoperability gap is that data can
leave only as CSV and can never come back. The arc adds: a whitelisted
read-only JSON API with a versioned envelope, CSV import completing the
round-trip, `/api/v1/schema` as the programmable contract, and a rehearsed
SQLite online-backup drill. SQLite's single-file format is itself the
portability workhorse — it opens identically on every OS and platform we
target.

**Platforms (D6).** One codebase, three proven paths: bare metal (Python
3.12 + four pinned deps under PM2), container (existing Dockerfile, build
honestly blocked until a Docker-capable host runs it), serverless (Vercel
entry exists; note SQLite writes don't persist there — documented as a
read-only/demo path, not hidden). Models are standard-library Python with
JSON parameter files, so inference adds **zero** dependencies anywhere.

**Extensibility (D2, D5).** A new metric = one JSON definition (no engine
change); a new dataset = one fetcher entry with a checksum; a new model
version = one versioned params file, hot-reloaded. Each claim has an
acceptance test in the buildplan.

## 5. Data readiness (summary of [data-research.md](data-research.md))

Sixteen free sources inventoried with licenses; top picks: Dryad Braunvieh
per-cow records (lactation curves), Dryad UK Holstein 396k-cow dataset
(calving outcomes), Mendeley IoT mastitis set (health labels), USDA NASS
Quick Stats API (price series), CDCB/ICAR/FAOSTAT (breed benchmarks incl.
India). Honest gaps recorded: no open per-cow desi-breed dataset exists, so
Gir/Sahiwal/Murrah benchmarks come from ICAR/FAOSTAT aggregates with per-row
citations; open estrus-event data is scarce, so heat timing ships as a
literature-validated rules model. Selected datasets are stored locally with
checksums (D3.2) so inference never depends on a remote site.

## 6. Verdict

The spine (architect → engineer → designer → analyst) is adopted as the
project's data backbone and has already run once end-to-end. The scientist and
ml roles are adopted as in-repo implementations over the same gold layer until
the plugin ships them natively. BI is deferred as duplicative; SRE is
right-sized to PM2 + Docker + tests. The plan of record's phases D0–D6 map
one-to-one onto this verdict, every leaf carries a runnable acceptance test,
and the cockpit reports honestly below 100% until each test has actually run.
