#!/usr/bin/env python3
"""Barnboard Data Platform phasedoc — plan script + task database.

Arc: make the barnboard data stack interoperable, extensible, and useful on
every environment/platform; research free web data for models; train and serve
inference — measured against the data-team skill's eight roles (see
roles-vs-needs.md).

The task tree lives in SQLite. Each leaf carries a concrete, runnable
acceptance test and is ticked ONLY after that test has actually been run.
Parents roll up from their leaves. `tick`/`part`/`add` regenerate the committed
buildplan mirror so git and the database never drift.

Seeding note: D0.1 (the data-team spine run) was executed and verified on
2026-09-07 before this window was minted; its tick timestamp is the seeding
date. Everything else starts honestly open.

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

# ── The authored task list ─────────────────────────────────────────────────
# (id, parent, title, acceptance, component, status)
TASKS = [
    # ── D0 Pipeline foundation ──
    ("D0", "", "Data pipeline foundation", "", "", "open"),
    ("D0.1", "D0", "data-team spine run (architect→engineer→designer→analyst) over barnboard data",
     "data-team-out/barnboard/manifest.json exists; bronze/silver/gold/semantic/reports all populated", "pipeline", "done"),
    ("D0.2", "D0", "Repeatable source export (make_sources.py, stdlib-only)",
     "python3 tools/make_sources.py regenerates 5 headed CSVs whose row counts match the live tables", "pipeline", "open"),
    ("D0.3", "D0", "Committed pipeline config (data-team.yaml)",
     "data-team.yaml parses and names slug/sources/stages/questions used by the run", "pipeline", "open"),
    ("D0.4", "D0", "Roles-vs-needs report + plan of record committed",
     "phasedoc-data/roles-vs-needs.md and plan-of-record.md exist in the repo and are linked from cockpit Resources", "pipeline", "open"),

    # ── D1 Interoperability ──
    ("D1", "", "Interoperability — open data contracts", "", "", "open"),
    ("D1.1", "D1", "Read-only JSON API (/api/v1/<table>.json, whitelisted)",
     "curl /api/v1/milk_logs.json returns a JSON envelope {schema_version, table, rows}; non-whitelisted table -> 404", "contracts", "open"),
    ("D1.2", "D1", "CSV import (round-trip with export)",
     "export -> import into a fresh test DB -> row counts and spot values match the original", "contracts", "open"),
    ("D1.3", "D1", "Versioned data contract endpoint (/api/v1/schema)",
     "curl /api/v1/schema returns version + column names/types for all 5 domain tables, matching PRAGMA table_info", "contracts", "open"),
    ("D1.4", "D1", "SQLite portability: online backup + integrity drill",
     "sqlite3 .backup copy passes PRAGMA integrity_check and opens on a second machine/python", "contracts", "open"),

    # ── D2 Extensibility — governed semantic layer ──
    ("D2", "", "Extensibility — governed semantic layer", "", "", "open"),
    ("D2.1", "D2", "Author real governed metrics (yield/cow/day, yield by breed, revenue, avg price)",
     "designer conformance passes and analyst answers match hand-written SQL over silver to 2 decimals", "semantic", "open"),
    ("D2.2", "D2", "Metric extension path documented (add a metric with zero engine changes)",
     "a new metric added as a JSON def alone appears in the next analyst report", "semantic", "open"),
    ("D2.3", "D2", "Pipeline idempotency",
     "re-running the spine yields identical gold row counts and identical metric values", "semantic", "open"),

    # ── D3 Data research & acquisition ──
    ("D3", "", "Free web data — research & acquisition", "", "", "open"),
    ("D3.1", "D3", "Verified free-data inventory (licenses, formats, use-cases)",
     "data-research.md lists 8+ sources with URL, publisher, license, format, and use-case mapping", "research", "open"),
    ("D3.2", "D3", "Reference dataset store with fetcher + checksums",
     "python3 tools/fetch_reference.py downloads 2+ free datasets into data/reference/ and records sha256 sums", "datasets", "open"),
    ("D3.3", "D3", "Breed benchmark table from open data (incl. desi breeds)",
     "data/reference/breed_benchmarks.csv has 5+ breeds incl. Gir/Sahiwal/Murrah with cited sources and loads into gold", "datasets", "open"),

    # ── D4 Models ──
    ("D4", "", "Models — train & evaluate on gold", "", "", "open"),
    ("D4.1", "D4", "Per-cow 7-day yield forecast (stdlib, versioned params)",
     "backtest on the last 7 held-out days: model MAE beats the naive last-value baseline; numbers in eval report", "models", "open"),
    ("D4.2", "D4", "Yield-drop anomaly scoring against forecast",
     "seeded decliner (#102) flagged; zero false positives among stable cows on the same window", "models", "open"),
    ("D4.3", "D4", "Month-end revenue projection",
     "holdout projection of month-to-date revenue within 15% of actual; recorded in eval report", "models", "open"),
    ("D4.4", "D4", "Model evaluation report",
     "models/eval.md committed with per-model metrics, baselines, and training-data lineage", "models", "open"),

    # ── D5 Inference serving ──
    ("D5", "", "Inference — serve predictions everywhere", "", "", "open"),
    ("D5.1", "D5", "Forecast API (/api/v1/predict/yield/<cow_id>)",
     "curl returns 7-day JSON forecast with model version; unknown cow -> 404", "serving", "open"),
    ("D5.2", "D5", "Dashboard forecast panel in barnboard",
     "GET / renders the forecast panel; headless walk shows it with 0 console errors", "app", "open"),
    ("D5.3", "D5", "Versioned, hot-reloadable model artifacts",
     "models/ holds versioned JSON params; bumping the version serves new numbers without code changes", "serving", "open"),

    # ── D6 Cross-platform ops ──
    ("D6", "", "Every environment, every platform", "", "", "open"),
    ("D6.1", "D6", "Container path verified (Docker image builds, serves / 200)",
     "docker build + docker run on a Docker-capable host returns 200 on /; blocked on this host (no Docker) until then", "ops", "open"),
    ("D6.2", "D6", "Bare-metal path: PM2 app + both cockpits, reboot-persistent",
     "pm2 ls shows barnboard, phasedoc-barnboard, phasedoc-dataarc online; pm2 save done", "ops", "open"),
    ("D6.3", "D6", "Automated test suite over API + models",
     "pytest covers contracts (D1) and models (D4) and passes clean", "ops", "open"),
    ("D6.4", "D6", "Arc lives on GitHub, mirror committed with every tick",
     "git log shows buildplan.md updated in tick commits; repo pushed", "ops", "open"),
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


# ── verbs ───────────────────────────────────────────────────────────────────

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
    lines = ["# Barnboard Data Platform — buildplan mirror", "",
             f"_Generated by plan.py on {now()}. Do not edit by hand — regenerated on every tick._",
             "", "> D0.1 was seeded retrospectively (the data-team spine run was executed and",
             "> verified 2026-09-07, before this window was minted). All other leaves start open.", ""]
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
