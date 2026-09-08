# Barnboard Gap-Closure (G) arc — Plan of Record

Internal, builders-facing. This arc exists to close the gaps enumerated and
scored in [gap-analysis.md](gap-analysis.md). Its ordering rule is the whole
strategy: **High Impact / Low Complexity first** (G0, G1), then the scheduled
medium-complexity work (G2, G3), with the backlog (G4) tracked honestly and
deliberately unscheduled. Nothing in this arc is pre-ticked.

## G0 — Contract & security quick wins

Four small fixes with outsized payoff. The hosted twin's API token is
stabilized from an environment secret so machine consumers can actually use
the advertised contracts (today the token is random per serverless instance —
the interoperability story fails exactly where a prospect would test it). The
session cookie gains its Secure flag over HTTPS. The forecast panel learns
Telugu, keeping the "native to an Indian dairy" promise. And the published-PIN
policy is written down as a decision rather than left ambiguous.

## G1 — Continuity

The platform learns to survive: reboots (the one-time `pm2 startup` unit,
then a rehearsed `pm2 resurrect` drill), disk loss (the existing backup tool
becomes a nightly schedule with a rehearsed restore), regressions (the 23-test
suite and the model baseline gate run in CI on every push), and human drift
(a check that fails when a listening port is missing from the registry).

## G2 — Freshness & reach

The data platform stops decaying. The pipeline-and-retrain chain runs
nightly, so new milk logs reach the forecast without anyone remembering to
run five commands; a failed baseline gate is surfaced, never swallowed. The
governed semantic layer — the platform's best idea — becomes part of the open
contract via a metrics API that returns values *with receipts*. The hosted
twin retrains on its own seeded data so its "next 7 days" starts tomorrow,
not last week.

## G3 — Platform proof

Claims become verified facts: the Docker image built and served on a
Docker-capable host (honestly blocked on this machine until then), TLS in
front of the LAN-exposed betadoc lanes, and the accepted serverless
trade-offs (per-instance rate limiting, no pre-expiry session revocation)
recorded in the technical reference with an explicit revisit trigger.

## G4 — Backlog

Tracked, not scheduled: the milk-price outlook, lactation-curve priors (only
if they beat damped Holt on a real multi-month backtest), the heat-detection
rules model, narrated demo videos for both betadoc heroes, and the co-op
multi-farm design. Each has an acceptance test written now so scope is honest
when its day comes.
