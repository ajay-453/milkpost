#!/usr/bin/env python3
"""Data-Scientist stage, in-repo (D4): train and evaluate the three models on
the gold layer. Stdlib-only; parameters land as versioned JSON artifacts under
models/ so inference anywhere needs no extra dependencies.

Models
  1. yield_forecast  — per-cow damped level+trend (Holt-style) on cow-day gold;
                       backtested against a naive last-value baseline (D4.1)
  2. yield_anomaly   — deviation of recent actuals vs forecast; flags sustained
                       drops (D4.2)
  3. revenue_projection — month-end revenue from month-to-date rate (D4.3)

Every number in models/eval.md comes from this script's holdout runs (D4.4).

Usage: python3 tools/train_models.py [--gold PATH] [--version v1]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
HUB = os.path.dirname(HERE)
GOLD = os.path.join(HUB, "data-team-out/barnboard/gold/gold.db")
MODELS = os.path.join(HUB, "models")

ALPHA, BETA, DAMP = 0.35, 0.15, 0.92   # Holt smoothing + trend damping
HOLDOUT_DAYS = 7
DROP_THRESHOLD = -0.20                 # 20% below forecast, sustained
DROP_WINDOW = 3


def load_series(gold_path: str):
    """cow_id -> {'tag','breed', 'days': [(date, litres)...] sorted}.

    Incomplete cow-days (fewer sessions logged than the cow's usual count —
    e.g. an AM entered but the PM not yet) are excluded: a half-logged day
    looks like a 50% yield crash and poisons both forecasts and anomaly flags.
    """
    con = sqlite3.connect(f"file:{gold_path}?mode=ro", uri=True)
    raw = defaultdict(list)
    meta = {}
    for cid, tag, breed, d, litres, cnt in con.execute(
            "SELECT cow_id, tag, breed, log_date_day, litres, milk_logs_count "
            "FROM agg_milk_cow_daily ORDER BY log_date_day"):
        raw[cid].append((d, litres, cnt))
        meta[cid] = (tag, breed)
    con.close()
    cows = {}
    for cid, days in raw.items():
        counts = sorted(c for _, _, c in days)
        modal = counts[len(counts) // 2]          # median session count
        tag, breed = meta[cid]
        cows[cid] = {"tag": tag, "breed": breed,
                     "days": [(d, l) for d, l, c in days if c >= modal]}
    return cows


def holt_fit(values: list[float]) -> tuple[float, float]:
    """Damped Holt level+trend. Returns (level, trend) after the last point."""
    level, trend = values[0], 0.0
    for v in values[1:]:
        prev = level
        level = ALPHA * v + (1 - ALPHA) * (level + DAMP * trend)
        trend = BETA * (level - prev) + (1 - BETA) * DAMP * trend
    return level, trend


def holt_forecast(level: float, trend: float, horizon: int) -> list[float]:
    out, cum = [], 0.0
    for h in range(1, horizon + 1):
        cum += DAMP ** h
        out.append(max(0.0, level + cum * trend))
    return out


def backtest(cows: dict) -> dict:
    """Hold out the trailing HOLDOUT_DAYS per cow; compare vs naive last-value."""
    abs_err_model, abs_err_naive, n = 0.0, 0.0, 0
    for c in cows.values():
        days = c["days"]
        if len(days) < HOLDOUT_DAYS + 5:      # need a training run-up
            continue
        train, test = days[:-HOLDOUT_DAYS], days[-HOLDOUT_DAYS:]
        level, trend = holt_fit([v for _, v in train])
        preds = holt_forecast(level, trend, HOLDOUT_DAYS)
        naive = train[-1][1]
        for (d, actual), pred in zip(test, preds):
            abs_err_model += abs(actual - pred)
            abs_err_naive += abs(actual - naive)
            n += 1
    return {"holdout_days": HOLDOUT_DAYS, "points": n,
            "mae_model": round(abs_err_model / n, 3) if n else None,
            "mae_naive": round(abs_err_naive / n, 3) if n else None}


def anomaly_scores(cows: dict) -> list[dict]:
    """Fit on all-but-last-DROP_WINDOW days, score the recent window vs forecast."""
    flags = []
    for cid, c in cows.items():
        days = c["days"]
        if len(days) < DROP_WINDOW + 7:
            continue
        train, recent = days[:-DROP_WINDOW], days[-DROP_WINDOW:]
        level, trend = holt_fit([v for _, v in train])
        preds = holt_forecast(level, trend, DROP_WINDOW)
        devs = [(a - p) / p for (_, a), p in zip(recent, preds) if p > 0]
        mean_dev = sum(devs) / len(devs) if devs else 0.0
        flags.append({"cow_id": cid, "tag": c["tag"], "breed": c["breed"],
                      "mean_deviation": round(mean_dev, 3),
                      "flagged": mean_dev <= DROP_THRESHOLD})
    return sorted(flags, key=lambda f: f["mean_deviation"])


def revenue_projection(hub: str) -> dict:
    """Project August month-end revenue from the first-half rate; compare to
    actual (holdout: the second half of August was hidden from the estimate)."""
    con = sqlite3.connect(f"file:{os.path.join(hub, 'data-team-out/barnboard/silver/silver.db')}?mode=ro", uri=True)
    rows = con.execute("SELECT collected_on, litres, price_per_litre FROM sales "
                       "WHERE collected_on LIKE '2026-08%' ORDER BY collected_on").fetchall()
    con.close()
    if not rows:
        return {"error": "no august sales"}
    cutoff = "2026-08-24"
    seen = [(d, l, p) for d, l, p in rows if d <= cutoff]
    first_day = date.fromisoformat(rows[0][0])
    days_elapsed = (date.fromisoformat(cutoff) - first_day).days + 1
    days_total = (date(2026, 8, 31) - first_day).days + 1
    mtd = sum(l * p for _, l, p in seen)
    projected = mtd / days_elapsed * days_total
    actual = sum(l * p for _, l, p in rows)
    return {"cutoff": cutoff, "mtd_revenue": round(mtd, 2),
            "projected_month_end": round(projected, 2),
            "actual_month_end": round(actual, 2),
            "abs_pct_error": round(abs(projected - actual) / actual * 100, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=GOLD)
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()

    cows = load_series(args.gold)
    bt = backtest(cows)
    flags = anomaly_scores(cows)
    rev = revenue_projection(HUB)

    # final fit on ALL days -> the served artifact
    params = {}
    for cid, c in cows.items():
        level, trend = holt_fit([v for _, v in c["days"]])
        params[str(cid)] = {"tag": c["tag"], "breed": c["breed"],
                            "level": round(level, 3), "trend": round(trend, 4),
                            "trained_through": c["days"][-1][0],
                            "n_days": len(c["days"])}
    outdir = os.path.join(MODELS, "yield_forecast", args.version)
    os.makedirs(outdir, exist_ok=True)
    artifact = {"model": "yield_forecast", "version": args.version,
                "algorithm": f"damped Holt (alpha={ALPHA}, beta={BETA}, damp={DAMP})",
                "alpha": ALPHA, "beta": BETA, "damp": DAMP,
                "lineage": ["gold.agg_milk_cow_daily"],
                "backtest": bt, "cows": params}
    with open(os.path.join(outdir, "params.json"), "w") as f:
        json.dump(artifact, f, indent=2)
    with open(os.path.join(MODELS, "yield_forecast", "LATEST"), "w") as f:
        f.write(args.version + "\n")

    with open(os.path.join(MODELS, "anomaly_flags.json"), "w") as f:
        json.dump({"threshold": DROP_THRESHOLD, "window_days": DROP_WINDOW,
                   "scores": flags}, f, indent=2)

    print(json.dumps({"backtest": bt,
                      "flagged": [f["tag"] for f in flags if f["flagged"]],
                      "revenue": rev}, indent=2))
    beats = bt["mae_model"] is not None and bt["mae_model"] < bt["mae_naive"]
    print(f"model {'BEATS' if beats else 'DOES NOT BEAT'} naive baseline; artifact -> {outdir}/params.json")
    return 0 if beats else 1


if __name__ == "__main__":
    sys.exit(main())
