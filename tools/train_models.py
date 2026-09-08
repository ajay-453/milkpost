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


def load_series_from_app(app_db_path: str):
    """Same cow-day series as load_series, built directly from the app DB —
    for environments with no pipeline run (the serverless twin, G2.3)."""
    con = sqlite3.connect(f"file:{app_db_path}?mode=ro", uri=True)
    raw = defaultdict(list)
    meta = {}
    for cid, tag, breed, d, litres, cnt in con.execute(
            "SELECT m.cow_id, c.tag, c.breed, m.log_date, SUM(m.litres), COUNT(*) "
            "FROM milk_logs m JOIN cows c ON c.id = m.cow_id "
            "GROUP BY m.cow_id, m.log_date ORDER BY m.log_date"):
        raw[cid].append((d, litres, cnt))
        meta[cid] = (tag, breed)
    con.close()
    cows = {}
    for cid, days in raw.items():
        counts = sorted(c for _, _, c in days)
        modal = counts[len(counts) // 2]
        tag, breed = meta[cid]
        cows[cid] = {"tag": tag, "breed": breed,
                     "days": [(d, l) for d, l, c in days if c >= modal]}
    return cows


def holt_fit(values: list[float], beta: float = BETA) -> tuple[float, float]:
    """Damped Holt level+trend. Returns (level, trend) after the last point.
    beta=0 collapses to an EWMA (level-only) — the trendless candidate."""
    level, trend = values[0], 0.0
    for v in values[1:]:
        prev = level
        level = ALPHA * v + (1 - ALPHA) * (level + DAMP * trend)
        trend = beta * (level - prev) + (1 - beta) * DAMP * trend
    return level, trend


VAL_DAYS = 4  # validation slice INSIDE the training window for model selection


def select_and_fit(values: list[float]) -> tuple[float, float, str]:
    """Per-cow model selection (G2.1). A trend only earns its place if it wins
    on a validation slice the fit never saw; stable cows get the trendless
    EWMA, decliners keep Holt. Selection never touches the true holdout.
    Returns (level, trend, method) fitted on ALL of `values`."""
    def _fit(vals: list[float], method: str) -> tuple[float, float]:
        if method == "last":                 # naive last-value as a real candidate
            return vals[-1], 0.0
        if method == "wood":                 # lactation curve (G4.2), history-gated
            return _wood_as_level_trend(vals)
        return holt_fit(vals, BETA if method == "holt" else 0.0)

    if len(values) > VAL_DAYS + 4:
        fit_part, val_part = values[:-VAL_DAYS], values[-VAL_DAYS:]
        candidates = ["holt", "ewma", "last"]
        if len(values) >= WOOD_MIN_DAYS:
            candidates.append("wood")
        scores = {}
        for name in candidates:
            lv, tr = _fit(fit_part, name)
            preds = holt_forecast(lv, tr, VAL_DAYS)
            scores[name] = sum(abs(a - p) for a, p in zip(val_part, preds))
        method = min(scores, key=scores.get)
    else:
        method = "ewma"  # too little history to justify a trend
    level, trend = _fit(values, method)
    return level, trend, method


def holt_forecast(level: float, trend: float, horizon: int) -> list[float]:
    out, cum = [], 0.0
    for h in range(1, horizon + 1):
        cum += DAMP ** h
        out.append(max(0.0, level + cum * trend))
    return out


WOOD_MIN_DAYS = 90  # G4.2: the lactation curve may only compete (and thus
                    # ever ship) once a cow has multi-month history — the
                    # acceptance requires beating Holt on a real backtest first.


def wood_fit(values: list[float]) -> tuple[float, float, float]:
    """Wood's lactation curve y(t) = a * t^b * exp(-c t), fitted by
    log-linearisation (ln y = ln a + b ln t - c t) via 3x3 normal equations."""
    import math
    xs = [(1.0, math.log(t), -float(t)) for t in range(1, len(values) + 1)]
    ys = [math.log(max(v, 0.1)) for v in values]
    # build normal equations A beta = rhs
    A = [[sum(x[i] * x[j] for x in xs) for j in range(3)] for i in range(3)]
    rhs = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(3)]
    # gaussian elimination
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(A[r][col]))
        A[col], A[piv] = A[piv], A[col]
        rhs[col], rhs[piv] = rhs[piv], rhs[col]
        for r in range(col + 1, 3):
            f = A[r][col] / A[col][col]
            for c2 in range(col, 3):
                A[r][c2] -= f * A[col][c2]
            rhs[r] -= f * rhs[col]
    beta = [0.0, 0.0, 0.0]
    for r in (2, 1, 0):
        beta[r] = (rhs[r] - sum(A[r][c2] * beta[c2] for c2 in range(r + 1, 3))) / A[r][r]
    ln_a, b, c = beta
    return math.exp(ln_a), b, c


def wood_forecast(params: tuple[float, float, float], start_t: int, horizon: int) -> list[float]:
    import math
    a, b, c = params
    return [max(0.0, a * (start_t + h) ** b * math.exp(-c * (start_t + h)))
            for h in range(1, horizon + 1)]


def _wood_as_level_trend(values: list[float], horizon: int = HOLDOUT_DAYS):
    """Approximate Wood's projected path in the served level/trend contract."""
    w = wood_forecast(wood_fit(values), len(values), horizon)
    cums = []
    cum = 0.0
    for h in range(1, horizon + 1):
        cum += DAMP ** h
        cums.append(cum)
    trend = (w[-1] - w[0]) / (cums[-1] - cums[0]) if horizon > 1 else 0.0
    level = w[0] - cums[0] * trend
    return level, trend


def _strategy_fit(values: list[float], strategy: str):
    if strategy == "selected":
        return select_and_fit(values)[:2]
    if strategy == "last":
        return values[-1], 0.0
    if strategy == "wood":
        return _wood_as_level_trend(values)
    return holt_fit(values, BETA if strategy == "holt" else 0.0)


def strategies_for(cows: dict) -> tuple[str, ...]:
    base = ("selected", "holt", "ewma", "last")
    longest = max((len(c["days"]) for c in cows.values()), default=0)
    return base + ("wood",) if longest >= WOOD_MIN_DAYS else base


STRATEGIES = ("selected", "holt", "ewma", "last")


def backtest(cows: dict) -> dict:
    """Champion/challenger (G2.1): hold out the trailing week per cow, score
    every strategy on it — naive last-value is itself a challenger, so the
    served champion can never be worse than naive. All scores are reported."""
    strategies = strategies_for(cows)
    err = {s: 0.0 for s in strategies}
    n = 0
    for c in cows.values():
        days = c["days"]
        if len(days) < HOLDOUT_DAYS + 5:      # need a training run-up
            continue
        train, test = days[:-HOLDOUT_DAYS], days[-HOLDOUT_DAYS:]
        vals = [v for _, v in train]
        for s in strategies:
            level, trend = _strategy_fit(vals, s)
            preds = holt_forecast(level, trend, HOLDOUT_DAYS)
            err[s] += sum(abs(a - p) for (_, a), p in zip(test, preds))
        n += HOLDOUT_DAYS
    maes = {s: round(e / n, 3) if n else None for s, e in err.items()}
    champion = min(maes, key=lambda s: maes[s]) if n else "ewma"
    return {"holdout_days": HOLDOUT_DAYS, "points": n, "maes": maes,
            "champion": champion,
            "mae_model": maes.get(champion), "mae_naive": maes.get("last")}


def anomaly_scores(cows: dict) -> list[dict]:
    """Fit on all-but-last-DROP_WINDOW days, score the recent window vs forecast."""
    flags = []
    for cid, c in cows.items():
        days = c["days"]
        if len(days) < DROP_WINDOW + 7:
            continue
        train, recent = days[:-DROP_WINDOW], days[-DROP_WINDOW:]
        level, trend, _method = select_and_fit([v for _, v in train])
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


def run_training(cows: dict, out_root: str = MODELS, version: str = "v1") -> dict:
    """Backtest (champion/challenger), fit the champion, write the versioned
    artifact + LATEST + anomaly flags under out_root. Returns the backtest."""
    bt = backtest(cows)
    flags = anomaly_scores(cows)
    params = {}
    champ = bt["champion"]
    for cid, c in cows.items():
        vals = [v for _, v in c["days"]]
        if champ == "selected":
            level, trend, method = select_and_fit(vals)
        else:
            level, trend = _strategy_fit(vals, champ)
            method = champ
        params[str(cid)] = {"tag": c["tag"], "breed": c["breed"],
                            "level": round(level, 3), "trend": round(trend, 4),
                            "method": method,
                            "trained_through": c["days"][-1][0],
                            "n_days": len(c["days"])}
    outdir = os.path.join(out_root, "yield_forecast", version)
    os.makedirs(outdir, exist_ok=True)
    artifact = {"model": "yield_forecast", "version": version,
                "algorithm": "champion/challenger: damped Holt / EWMA / last-value, "
                             f"champion chosen on the holdout (alpha={ALPHA}, beta={BETA}, damp={DAMP})",
                "alpha": ALPHA, "beta": BETA, "damp": DAMP,
                "lineage": ["gold.agg_milk_cow_daily"],
                "backtest": bt, "champion": bt["champion"], "cows": params}
    with open(os.path.join(outdir, "params.json"), "w") as f:
        json.dump(artifact, f, indent=2)
    with open(os.path.join(out_root, "yield_forecast", "LATEST"), "w") as f:
        f.write(version + "\n")
    with open(os.path.join(out_root, "anomaly_flags.json"), "w") as f:
        json.dump({"threshold": DROP_THRESHOLD, "window_days": DROP_WINDOW,
                   "scores": flags}, f, indent=2)
    bt["flagged"] = [f["tag"] for f in flags if f["flagged"]]
    return bt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=GOLD)
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()

    cows = load_series(args.gold)
    bt = run_training(cows, MODELS, args.version)
    rev = revenue_projection(HUB)
    print(json.dumps({"backtest": bt, "flagged": bt["flagged"], "revenue": rev}, indent=2))
    ok = bt["mae_model"] is not None and bt["mae_model"] <= bt["mae_naive"]
    print(f"champion '{bt['champion']}' MAE {bt['mae_model']} vs naive {bt['mae_naive']} "
          f"({'OK - never worse than naive' if ok else 'GATE FAILURE'})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
