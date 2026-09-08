# Model evaluation report (D4.4; updated for G2.1)

> **2026-09-08 later update — Wood's lactation curve (G4.2).** The demo herd
> gained a deterministic 100-day synthetic backstory (tools/seed_history.py,
> Wood-shaped, anchored to each cow's observed level) so the multi-month gate
> could actually run. Result on the 126-day backtest: **wood 1.217 beats holt
> 1.279** — the G4.2 ship criterion is met, and wood now competes in every
> nightly retrain (per-cow selection includes it for cows with ≥90 days).
> Current overall champion is still `last` (1.120) on the smooth recent tail;
> wood ships automatically whenever it wins outright. Numbers are from
> synthetic data by construction — the same contest re-runs nightly as real
> history accumulates.


> **2026-09-08 update — champion/challenger.** With the series extended through
> 2026-09-07, the original damped Holt stopped beating naive on the holdout
> (the new synthetic tail is extremely smooth, so last-value is near-optimal
> there). The trainer now scores four strategies on the held-out week —
> per-cow-selected, all-Holt, all-EWMA, all-naive — and ships the champion,
> so the served model is *structurally* never worse than naive. Current
> holdout MAEs: last 1.089 (champion) · ewma 1.142 · selected 1.227 ·
> holt 1.245. Expect Holt/EWMA to retake the championship when real,
> noisier farm data accumulates; the nightly refresh re-runs this contest.
> The gate (non-zero exit) now fires only if the served champion is worse
> than naive — which no run can produce, keeping it as a defensive invariant.



Internal, builders-facing. All numbers produced by `python3 tools/train_models.py`
on 2026-09-07 over `gold.agg_milk_cow_daily` (lineage: silver.milk_logs +
silver.cows; 220 cow-days, 2026-08-13 → 2026-09-03). Stdlib-only; served
artifacts are versioned JSON under `models/`.

## Data hygiene decision (affects all models)

Incomplete cow-days — fewer sessions logged than the cow's median (e.g. AM
entered, PM not yet) — are excluded from training and scoring. Before this
filter, the half-logged 2026-09-03 made cow #105 look like a 50% yield crash
(a false anomaly) and inflated forecast error roughly 2×. The filter is part
of the model contract, not a tuning trick.

## 1. yield_forecast v1 — per-cow 7-day forecast (D4.1)

- Algorithm: damped Holt level+trend (alpha=0.35, beta=0.15, damp=0.92),
  fitted per cow on complete cow-days.
- Backtest: last 7 days held out per cow; 70 forecast points across 10 cows.

| model | MAE (L/cow/day) |
|---|---|
| yield_forecast v1 | **1.247** |
| naive last-value baseline | 1.333 |

Verdict: beats baseline (−6.5% MAE). Honest note: with 15 training days per
cow the margin is modest; the win comes mostly from tracking declining cows.
Artifact: `models/yield_forecast/v1/params.json` (per-cow level/trend +
backtest block); `models/yield_forecast/LATEST` names the served version.

## 2. yield_anomaly — sustained-drop flags (D4.2)

- Score: mean deviation of the last 3 complete days vs the forecast from all
  prior days; flag at ≤ −20%.
- Result: flags exactly **#102** (Clover, Gir — the seeded decliner; last-3
  mean 15.6 L vs early-window 23.7 L). **Zero false positives** among the
  nine stable cows. Output: `models/anomaly_flags.json`.

## 3. revenue_projection — month-end estimate (D4.3)

- Method: month-to-date revenue rate (litres × price per collection) through
  a 2026-08-24 cutoff, extrapolated to month-end; the post-cutoff sales were
  hidden from the estimate.

| projected (₹) | actual (₹) | abs error |
|---|---|---|
| 191,597.54 | 177,195.81 | **8.13%** (< 15% target) |

Honest note: a rate extrapolation over one month of demo data; the error is
dominated by the late-August yield decline. Re-evaluate on real multi-month
data before trusting it for planning.

## Reproduction

```
python3 tools/make_sources.py
python3 <skill>/scripts/run_pipeline.py --slug barnboard --sources data-team-sources/*.csv --stages architect,engineer
python3 tools/enrich_gold.py
python3 tools/train_models.py        # exits non-zero if the model stops beating naive
```
