# Gap Analysis — Barnboard Platform (2026-09-08)

Internal, builders-facing. Sources: open leaves in both phasedoc arcs
(barnboard v1: P6.4, P6.5; data arc: D6.1, D6.2-partial), the betadoc feature
matrix's honest Partial/Roadmap rows, and the technical debt recorded in
`docs/concepts.html` §16–18. Each gap is scored **Impact** (what breaks or is
lost if unaddressed) × **Complexity** (effort + risk to close), then sorted:
quadrant 1 (High Impact · Low Complexity) first — that ordering seeds the G-arc
buildplan in this directory.

## The 2×2

| | **Low Complexity** | **Med/High Complexity** |
|---|---|---|
| **High Impact** | Q1 — do first (G0/G1) | Q2 — schedule (G2/G3) |
| **Med/Low Impact** | Q3 — batch in (fits G0–G3) | Q4 — backlog (G4) |

## Q1 — High Impact · Low Complexity (do first)

| # | Gap | Why it matters (impact) | Why it's cheap (complexity) |
|---|-----|--------------------------|------------------------------|
| 1 | **API token auth is broken on the hosted twin.** `feed_token` is generated randomly per lambda instance, so `/api/v1/*?token=` works only by luck of instance routing on barnboard-app-v2. | The public demo advertises machine-readable contracts that machines can't reliably call — the interoperability story fails exactly where prospects test it. | Stabilize the token from an env secret when `STATELESS_SESSIONS`/serverless mode is active (same pattern as SESSION_SECRET). ~10 lines + tests. |
| 2 | **Session cookie lacks the Secure flag on Vercel.** `SECURE_COOKIES` defaults to 0 and was never set for the HTTPS twin. | Session token can leak over an http:// downgrade attempt; basic hygiene for a public deployment. | One env var + redeploy + a curl header check. |
| 3 | **Nothing survives a reboot.** `pm2 save` is done but `pm2 startup` (one sudo command) was never run — all five local services die with the machine. | Whole local platform (app + 2 cockpits + 2 betadocs) offline after any power cycle; silent until someone notices. | User runs the printed sudo command once; verify with a `pm2 resurrect` drill. |
| 4 | **Backups exist as a tool, not a habit.** `tools/backup_db.py` passes its drill but nothing schedules it; no retention, no restore rehearsal cadence (v1 arc leaf P6.5, still open). | The farm database is one file on one disk. This is the largest data-loss exposure in the system. | Cron/pm2 schedule of the existing tool + dated copies + one rehearsed restore. |
| 5 | **No CI.** 23 tests + a baseline-gated trainer exist, but nothing runs them on push. | Regressions land silently; the acceptance-test culture stops at the laptop. | One GitHub Actions workflow: pytest + `train_models.py` exit-code gate. |
| 6 | **Models go stale by design.** Training is manual; new milk logs never reach the forecast until someone re-runs the pipeline chain. | The headline feature (forecast panel) decays daily; "trained_through" drifts behind reality. | Schedule the existing chain (make_sources → spine → enrich → train) nightly under pm2/cron; alert on baseline-gate failure. |

## Q2 — High Impact · Medium Complexity (schedule next)

| # | Gap | Impact | Complexity notes |
|---|-----|--------|------------------|
| 7 | **Semantic layer unreachable by API.** Governed metrics + receipts exist only as pipeline artifacts; consumers can't ask `/api/v1/metrics/avg_daily_yield_per_cow`. | The platform's best idea (answers with receipts) isn't part of the open contract. | New read-only endpoints serving metric defs + computed values from gold; auth reuse; ~1 day incl. tests. |
| 8 | **Hosted-twin forecast dates are stale.** Bundled artifact says `trained_through 2026-09-03` while the seeded herd is dated "today" — visible credibility wart on the public demo. | Demo audience sees a "next 7 days" that starts in the past. | Retrain-at-cold-start on the seeded /tmp data (trainer is stdlib and fast) or date-shift the artifact at seed time. |
| 9 | **Docker lane unverified** (data-arc leaf D6.1, blocked: no Docker on this host). | "Every platform" claim is roadmap-grade until an image actually runs. | Needs a Docker-capable machine or user installs Docker (sudo); the Dockerfile itself is ready. |
| 10 | **No TLS on local/LAN lanes** (v1 arc leaf P6.4). Betadocs bind 0.0.0.0 over plain HTTP. | LAN sniffing exposes PINs/sessions; also blocks Secure-cookie hygiene locally. | Caddy/nginx front or tunnel with certs; moderate ops work on this box. |

## Q3 — Medium Impact · Low Complexity (batch into the arc)

| # | Gap | Notes |
|---|-----|-------|
| 11 | **New UI strings aren't translated.** The forecast panel's labels fall back to English in Telugu mode — dents the "native to an Indian dairy" promise. Add the `te` keys to i18n.py. |
| 12 | **PIN is published, so the gate is informational.** Fine if intentional — but record the policy (or rotate PIN + unpublish for a real client). A decision leaf, not a code leaf. |
| 13 | **Registry/docs drift risk.** Port registry updates rely on memory/discipline; add a check that flags pm2 ports missing from the registry (small script, runs in CI). |

## Q4 — Backlog (High Complexity or lower impact; tracked, not scheduled)

| # | Gap | Why backlog |
|---|-----|-------------|
| 14 | **Milk-price forecasting** from USDA/market series (verified sources ready in data-research.md). | New model + ingestion; medium-high complexity, medium impact for an Indian farm (USDA ≠ local mandi prices; FAOSTAT is annual). |
| 15 | **Lactation-curve priors** (Wood/Wilmink seeded from breed benchmarks) to replace flat Holt levels as history grows. | Real data-science iteration; needs more than 3 weeks of data to evaluate honestly. |
| 16 | **Heat-detection rules model** (21-day cycle + deviation signals, literature-validated). | Domain-sensitive; open datasets scarce (documented in data-research.md). |
| 17 | **Demo video in betadoc heroes** (both betadocs shipped without one; the skill prescribes it). | Recording + narration + ffmpeg pipeline; polish, not function. |
| 18 | **Serverless rate limiting is per-instance** (each lambda has its own window) and **stateless sessions can't be revoked** before expiry. | Both are accepted trade-offs for a demo twin; fixing properly needs shared state (KV/DB) — revisit only if the twin ever holds real data. |
| 19 | **Known perf cliffs**: N+1 in `yield_drop_alerts`, no-cache dashboard. | Correct at 12 cows; the batch rewrite is documented in concepts.html §18 for when a large herd arrives. |
| 20 | **Multi-farm / co-op analytics.** | ~~The strategic horizon~~ **Descoped 2026-09-08 by owner decision** — removed from the arc; the design draft is parked at `docs/coop-design.md` for whenever it returns. |

## Sorted priority → arc mapping

Q1 (#1–6) → **G0 Contract & security quick wins** + **G1 Continuity**.
Q2 (#7–10) → **G2 Freshness & reach** + **G3 Platform proof**.
Q3 (#11–13) → folded into G0/G1 where they touch the same files.
Q4 (#14–19) → **G4 Backlog**, honestly open, no dates. (#20 descoped 2026-09-08.)

Tracking: `phasedoc-gaps/` (this arc), cockpit on **port 6793**, one leaf per
gap with a runnable acceptance test. Ticks only after the test runs.
