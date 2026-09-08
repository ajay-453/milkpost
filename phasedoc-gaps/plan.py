#!/usr/bin/env python3
"""Barnboard Gap-Closure (G) arc — plan script + task database.

Arc: close the gaps found in gap-analysis.md, in strict priority order —
High Impact / Low Complexity first (G0/G1), then scheduled Q2 work (G2/G3),
with the backlog (G4) tracked honestly and unscheduled.

Every leaf carries a runnable acceptance test and is ticked ONLY after that
test has actually run. Parents roll up. tick/part/add regenerate the committed
buildplan mirror. All leaves start open — nothing is pre-ticked in this arc.

Verbs:  init | tick <id> | part <id> | note <id> <text> | add | tree | components | mirror
Env:    PHASEDOC_DB (default ./tasks.db), PHASEDOC_MIRROR (default ./buildplan.md)
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("PHASEDOC_DB", os.path.join(HERE, "tasks.db"))
MIRROR_PATH = os.environ.get("PHASEDOC_MIRROR", os.path.join(HERE, "buildplan.md"))

# (id, parent, title, acceptance, component, status) — gap numbers reference gap-analysis.md
TASKS = [
    # ── G0 Contract & security quick wins (Q1 gaps 1,2,11,12) ──
    ("G0", "", "Contract & security quick wins", "", "", "open"),
    ("G0.1", "G0", "Stable API feed token on serverless (gap #1)",
     "with FEED_TOKEN env set, two curls against the live twin's /api/v1/cows.json?token=... return 200 "
     "regardless of instance; without env (local), per-install token behavior unchanged", "contracts", "open"),
    ("G0.2", "G0", "Secure flag on session cookie over HTTPS (gap #2)",
     "live /login response Set-Cookie for bb_session includes Secure; local http lane unchanged", "security", "open"),
    ("G0.3", "G0", "Telugu strings for the forecast panel (gap #11)",
     "/lang/te then GET /: forecast card title renders in Telugu; English fallback intact for missing keys", "app", "open"),
    ("G0.4", "G0", "Demo-gate policy recorded (gap #12)",
     "a committed note states the published-PIN policy (informational gate) and the rotate procedure for real clients", "security", "open"),

    # ── G1 Continuity (Q1 gaps 3,4,5,13) ──
    ("G1", "", "Continuity — survive reboots, regressions, and disks", "", "", "open"),
    ("G1.1", "G1", "Reboot persistence via pm2 startup (gap #3)",
     "pm2 startup unit installed (user sudo); 'pm2 kill && pm2 resurrect' brings all six processes online", "continuity", "open"),
    ("G1.2", "G1", "Scheduled nightly DB backup + restore rehearsal (gap #4)",
     "a scheduler entry runs tools/backup_db.py nightly to dated files; latest backup passes integrity_check; "
     "one restore into a scratch app has been rehearsed", "continuity", "open"),
    ("G1.3", "G1", "CI: tests + model baseline gate on push (gap #5)",
     "GitHub Actions workflow runs pytest (23+) and train_models.py on push; latest run green on main", "continuity", "open"),
    ("G1.4", "G1", "Port-registry drift check (gap #13)",
     "a check script fails when a listening pm2 port is absent from the registry (proven with a fake), passes on real state; wired into CI", "continuity", "open"),

    # ── G2 Freshness & reach (Q2 gaps 6,7,8) ──
    ("G2", "", "Freshness & reach — data that stays current, contracts that reach further", "", "", "open"),
    ("G2.1", "G2", "Nightly pipeline + retrain schedule (gap #6)",
     "scheduled chain (make_sources -> spine -> enrich_gold -> train_models) runs unattended; models/LATEST params "
     "trained_through advances after new milk logs; baseline-gate failure is surfaced, not swallowed", "freshness", "open"),
    ("G2.2", "G2", "Governed metrics API (gap #7)",
     "/api/v1/metrics lists metric ids+versions; /api/v1/metrics/{id} returns value + receipt (SQL, lineage, owner) "
     "matching the pipeline report to 2 decimals; non-existent id -> 404", "contracts", "open"),
    ("G2.3", "G2", "Fresh forecast dates on the hosted twin (gap #8)",
     "live /api/v1/predict/yield/1 forecast[0].date == (seeded herd's last complete day)+1, not a stale bundled date", "freshness", "open"),

    # ── G3 Platform proof (Q2 gaps 9,10; Q4 #18 as decision) ──
    ("G3", "", "Platform proof — the claims become verified", "", "", "open"),
    ("G3.1", "G3", "Container lane verified (gap #9)",
     "docker build + run serves / with 200 on a Docker-capable host (blocked on this host until Docker exists)", "platform", "open"),
    ("G3.2", "G3", "TLS for LAN-exposed lanes (gap #10)",
     "betadoc ports served via HTTPS (proxy or tunnel); browser padlock + Secure cookies on the LAN lane", "platform", "open"),
    ("G3.3", "G3", "Serverless limits recorded as decisions (gap #18)",
     "technical reference gains a 'accepted serverless trade-offs' note (per-instance rate limit, no pre-expiry "
     "revocation) with the revisit trigger stated", "security", "open"),

    # ── G4 Backlog (Q4 gaps 14,15,16,17,20) — tracked, unscheduled ──
    ("G4", "", "Backlog — tracked honestly, not scheduled", "", "", "open"),
    ("G4.1", "G4", "Milk-price outlook from open market data (gap #14)",
     "a price series ingests from a verified source in data-research.md and renders an outlook next to revenue; "
     "evaluated against a holdout period", "backlog", "open"),
    ("G4.2", "G4", "Lactation-curve priors from breed benchmarks (gap #15)",
     "curve-based forecaster beats damped Holt on a multi-month backtest before it ships", "backlog", "open"),
    ("G4.3", "G4", "Heat-detection rules model (gap #16)",
     "21-day-cycle + deviation rules flag seeded heat events with zero false positives on stable cows", "backlog", "open"),
    ("G4.4", "G4", "Narrated demo videos for both betadoc heroes (gap #17)",
     "hero videos stream (byte-range 206) on :6790, :6792 and the hosted twin", "backlog", "open"),
    ("G4.5", "G4", "Multi-farm / co-op analytics design (gap #20)",
     "a design doc covers auth partitioning, per-farm data isolation, and governed rollups; reviewed before any code", "backlog", "open"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  parent TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL,
  acceptance TEXT NOT NULL DEFAULT '',
  component TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  ticked_at TEXT,
  note TEXT NOT NULL DEFAULT ''
);
"""


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def is_leaf(con, tid: str) -> bool:
    return con.execute("SELECT 1 FROM tasks WHERE parent = ? LIMIT 1", (tid,)).fetchone() is None


def rollup(con, tid: str) -> dict:
    leaves = con.execute(
        "SELECT status FROM tasks WHERE (id = ? OR id LIKE ?) AND id NOT IN "
        "(SELECT DISTINCT parent FROM tasks WHERE parent != '')",
        (tid, tid + ".%")).fetchall()
    total = len(leaves)
    done = sum(1 for r in leaves if r["status"] == "done")
    part = sum(1 for r in leaves if r["status"] == "part")
    return {"total": total, "done": done, "part": part, "open": total - done - part}


def state_of(con, tid: str) -> str:
    if is_leaf(con, tid):
        return con.execute("SELECT status FROM tasks WHERE id = ?", (tid,)).fetchone()["status"]
    r = rollup(con, tid)
    if r["total"] and r["done"] == r["total"]:
        return "done"
    if r["done"] or r["part"]:
        return "part"
    return "open"


def cmd_init(_args):
    seeded = os.path.exists(DB_PATH)
    con = db()
    con.executescript(SCHEMA)
    con.execute("DELETE FROM tasks")
    stamp = now()
    for tid, parent, title, acc, comp, status in TASKS:
        ticked = stamp if status == "done" else None
        con.execute(
            "INSERT INTO tasks (id, parent, title, acceptance, component, status, ticked_at) "
            "VALUES (?,?,?,?,?,?,?)", (tid, parent, title, acc, comp, status, ticked))
    con.commit()
    leaves = [t for t in TASKS if not any(o[1] == t[0] for o in TASKS)]
    print(f"{'Re-seeded' if seeded else 'Seeded'} {len(TASKS)} tasks ({len(leaves)} leaves) into {DB_PATH}")
    _write_mirror(con)
    con.close()


def _set_status(tid: str, status: str):
    con = db()
    row = con.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
    if not row:
        print(f"No such task: {tid}", file=sys.stderr); sys.exit(1)
    if not is_leaf(con, tid):
        print(f"{tid} is a parent — its state rolls up from leaves; tick its leaves instead.",
              file=sys.stderr); sys.exit(1)
    con.execute("UPDATE tasks SET status = ?, ticked_at = ? WHERE id = ?",
                (status, now() if status == "done" else row["ticked_at"], tid))
    con.commit()
    print(f"{tid} -> {status}")
    _write_mirror(con)
    con.close()


def cmd_tick(args):
    if not args:
        print("usage: tick <id>  (only after its acceptance test has run)", file=sys.stderr); sys.exit(2)
    _set_status(args[0], "done")


def cmd_part(args):
    if not args:
        print("usage: part <id>", file=sys.stderr); sys.exit(2)
    _set_status(args[0], "part")


def cmd_note(args):
    if len(args) < 2:
        print("usage: note <id> <text>", file=sys.stderr); sys.exit(2)
    tid, text = args[0], " ".join(args[1:])
    con = db()
    if not con.execute("SELECT 1 FROM tasks WHERE id = ?", (tid,)).fetchone():
        print(f"No such task: {tid}", file=sys.stderr); sys.exit(1)
    con.execute("UPDATE tasks SET note = ? WHERE id = ?", (text, tid))
    con.commit(); print(f"noted {tid}"); _write_mirror(con); con.close()


def cmd_add(args):
    if len(args) < 4:
        print("usage: add <id> <parent> <component> <title...>", file=sys.stderr); sys.exit(2)
    tid, parent, comp = args[0], args[1], args[2]
    title = " ".join(args[3:])
    con = db()
    con.execute("INSERT INTO tasks (id, parent, title, component, status) VALUES (?,?,?,?, 'open')",
                (tid, parent, title, comp))
    con.commit(); print(f"added {tid} under {parent}"); _write_mirror(con); con.close()


def cmd_tree(_args):
    con = db()
    rows = con.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    glyph = {"done": "[x]", "part": "[~]", "open": "[ ]"}
    for r in rows:
        depth = r["id"].count(".")
        st = state_of(con, r["id"])
        indent = "  " * depth
        if is_leaf(con, r["id"]):
            print(f"{indent}{glyph[st]} {r['id']} {r['title']}  <{r['component']}>")
        else:
            ru = rollup(con, r["id"])
            print(f"{indent}{glyph[st]} {r['id']} {r['title']}  ({ru['done']}/{ru['total']})")
    con.close()


def cmd_components(_args):
    con = db()
    comps = {}
    for r in con.execute("SELECT component, status FROM tasks WHERE component != '' AND id NOT IN "
                         "(SELECT DISTINCT parent FROM tasks WHERE parent != '')"):
        c = comps.setdefault(r["component"], {"total": 0, "done": 0, "part": 0})
        c["total"] += 1
        if r["status"] == "done": c["done"] += 1
        elif r["status"] == "part": c["part"] += 1
    for k in sorted(comps):
        c = comps[k]
        color = "green" if c["done"] == c["total"] else ("amber" if (c["done"] or c["part"]) else "grey")
        print(f"  comp-{k:<10} {c['done']}/{c['total']}  {color}")
    con.close()


def _write_mirror(con):
    lines = ["# Barnboard Gap-Closure (G) arc — buildplan mirror", "",
             f"_Generated by plan.py on {now()}. Do not edit by hand — regenerated on every tick._",
             "", "> Ordering IS the gap analysis: G0/G1 = High Impact - Low Complexity quadrant,",
             "> G2/G3 = scheduled Q2 work, G4 = backlog. See gap-analysis.md for scoring.", ""]
    all_leaves = con.execute(
        "SELECT status FROM tasks WHERE id NOT IN (SELECT DISTINCT parent FROM tasks WHERE parent != '')"
    ).fetchall()
    tot = len(all_leaves); dn = sum(1 for r in all_leaves if r["status"] == "done")
    pct = round(100 * dn / tot) if tot else 0
    lines.append(f"**Overall: {dn}/{tot} leaves done ({pct}%).**  `[x]` done · `[~]` partial · `[ ]` open")
    lines.append("")
    glyph = {"done": "[x]", "part": "[~]", "open": "[ ]"}
    for r in con.execute("SELECT * FROM tasks ORDER BY id"):
        if r["parent"] == "":
            ru = rollup(con, r["id"])
            lines.append(f"\n## {glyph[state_of(con, r['id'])]} {r['id']} — {r['title']}  ({ru['done']}/{ru['total']})")
        else:
            st = state_of(con, r["id"])
            extra = f" — _{r['note']}_" if r["note"] else ""
            lines.append(f"- {glyph[st]} **{r['id']}** {r['title']}  "
                         f"<`{r['component']}`>{extra}")
            if r["acceptance"]:
                lines.append(f"    - _accept:_ {r['acceptance']}")
    with open(MIRROR_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")


def cmd_mirror(_args):
    con = db(); _write_mirror(con); con.close()
    print(f"mirror -> {MIRROR_PATH}")


VERBS = {"init": cmd_init, "tick": cmd_tick, "part": cmd_part, "note": cmd_note,
         "add": cmd_add, "tree": cmd_tree, "components": cmd_components, "mirror": cmd_mirror}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in VERBS:
        print("verbs: " + " | ".join(VERBS), file=sys.stderr); sys.exit(2)
    VERBS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
