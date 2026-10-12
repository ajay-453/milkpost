#!/usr/bin/env python3
"""MilkPost TestForge-fix (F) arc — plan script + task database.

Arc: fix what the testforge.run scan of github.com/ajay-453/milkpost
(2026-10-12, scans/before-2026-10-12.json) found to be REAL, after triage
against the code. 2 real security findings (F0), 7 real low-risk gaps mostly
in how the mirror repo is packaged (F1), small runtime improvements (F2), and
a re-scan to prove it (F3). F4 (added 2026-10-12 after the re-scan,
scans/after-2026-10-12.md) takes the real items that scan surfaced: a CI
type-check, coverage to 60%, and the measured figure visible to the scanner.
The 41 false positives are listed in
plan-of-record.md and deliberately get no task.

Every leaf carries a runnable acceptance test and is ticked ONLY after that
test has actually run. Parents roll up. tick/part/note/add regenerate the
committed buildplan mirror. All leaves start open — nothing is pre-ticked.

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

# (id, parent, title, acceptance, component, status) — see plan-of-record.md for the triage behind each leaf
TASKS = [
    # ── F0 Security: the two real findings + the f-string SQL ──
    ("F0", "", "Security — upgrade vulnerable deps, remove f-string SQL", "", "", "open"),
    ("F0.1", "F0", "Upgrade jinja2 3.1.5 -> 3.1.6 and python-multipart 0.0.20 -> 0.0.32",
     "both hub/requirements.txt and aina-out/barnboard/app/requirements.txt pin jinja2==3.1.6 and "
     "python-multipart==0.0.32; 'pip-audit -r requirements.txt' reports no known vulnerabilities (any "
     "transitive hit, e.g. starlette, fixed by upgrading fastapi); 'python -m pytest -q' in "
     "aina-out/barnboard/app passes all tests", "deps", "open"),
    ("F0.2", "F0", "Ship the upgraded deps to the live twin",
     "'vercel --prod' from hub; curl https://milkpost.ajaykongala.online/healthz returns 200; a demo "
     "login POST /login sets the session cookie and GET / returns 200 (form parsing works on the new "
     "python-multipart)", "deps", "open"),
    ("F0.3", "F0", "main.py: literal queries per whitelisted table + pragma_table_info(?)",
     "grep -c 'execute(f' aina-out/barnboard/app/app/main.py == 0; TestClient: /export/cows.csv 200 with a "
     "header row, /export/users.csv 404, /api/v1/schema lists the 5 EXPORT_TABLES with columns, "
     "/api/v1/cows.json 200; pytest passes", "sql", "open"),
    ("F0.4", "F0", "backup.py: no f-string SQL",
     "grep -c 'execute(f' aina-out/barnboard/app/backup.py == 0; counts() on a copy of barnboard.db "
     "returns the same per-table numbers as before the change", "sql", "open"),

    # ── F1 Mirror repo hygiene (README, CI, coverage, lockfile) ──
    ("F1", "", "Mirror hygiene — the milkpost repo shows what the hub already has", "", "", "open"),
    ("F1.1", "F1", "Root README for the mirror",
     "docs/milkpost-README.md exists (what MilkPost is, layout, run locally, live URL); "
     "tools/mirror_repos.sh adds it to MILKPOST_PATHS with --path-rename to README.md; a local "
     "filter-repo dry run (throwaway clone) has README.md at its root", "mirror", "open"),
    ("F1.2", "F1", "MilkPost-only CI workflow",
     ".github/workflows/milkpost.yml runs MilkPost pytest + tools/train_models.py baseline gate, "
     "path-filtered to MilkPost folders, and is listed in MILKPOST_PATHS; latest run on hub Actions "
     "is green", "ci", "open"),
    ("F1.3", "F1", "Measure test coverage",
     "'python -m pytest --cov=app' in aina-out/barnboard/app prints a TOTAL line locally, and the "
     "same TOTAL line appears in the green CI log of both workflows", "ci", "open"),
    ("F1.4", "F1", "Hash-locked dependency file",
     "requirements.lock generated with hashes (uv pip compile --generate-hashes) from requirements.txt; "
     "in a fresh venv 'pip install --require-hashes -r requirements.lock' succeeds and pytest passes", "deps", "open"),
    ("F1.5", "F1", "This arc travels with the mirror",
     "phasedoc-testforge/ is in MILKPOST_PATHS (like phasedoc-data/ and phasedoc-gaps/)", "mirror", "open"),
    ("F1.6", "F1", "Re-mirror ajay-453/milkpost (user runs it)",
     "user runs '! tools/mirror_repos.sh milkpost' (classifier blocks Claude from git-filter-repo); "
     "github.com/ajay-453/milkpost shows README.md at root, .github/workflows/milkpost.yml, and a green "
     "Actions run", "mirror", "open"),

    # ── F2 Runtime improvements ──
    ("F2", "", "Runtime — compression, cache headers, documented JSON API", "", "", "open"),
    ("F2.1", "F2", "Gzip responses",
     "GZipMiddleware (minimum_size=1000) in main.py; TestClient GET of a logged-in page with "
     "Accept-Encoding: gzip returns content-encoding: gzip; pytest passes", "runtime", "open"),
    ("F2.2", "F2", "Cache-Control on the read-only API",
     "every /api/v1/* JSON response carries 'Cache-Control: private, max-age=30' (TestClient check on "
     "/api/v1/schema and /api/v1/cows.json)", "runtime", "open"),
    ("F2.3", "F2", "Response schemas for the 5 /api/v1 routes",
     "app.openapi() contains a non-empty 200 response schema for /api/v1/schema, /api/v1/{table}.json, "
     "/api/v1/metrics, /api/v1/metrics/{metric_id}, /api/v1/predict/yield/{cow_id}; payloads unchanged "
     "(existing tests pass)", "runtime", "open"),
    ("F2.4", "F2", "Error tracking: user decision",
     "user decides; EITHER sentry-sdk[fastapi] wired with DSN from env and a deliberate test exception "
     "appears in Sentry, OR plan-of-record records 'declined' with the reason", "ops", "open"),

    # ── F3 Close-out ──
    ("F3", "", "Close-out — prove it with a re-scan", "", "", "open"),
    ("F3.1", "F3", "Re-scan on testforge.run after re-mirror",
     "new report saved as scans/after-<date>.json; security.findings == 0, supplyChain.knownVulnerable "
     "== 0, scope README finding gone, dora CI finding gone", "verify", "open"),
    ("F3.2", "F3", "Before/after comparison written",
     "scans/compare.md lists every dimension score before -> after and names each finding still "
     "present with its triage verdict", "verify", "open"),

    # ── F4 Second-scan follow-ups (added 2026-10-12 from scans/after-2026-10-12.md) ──
    ("F4", "", "Second-scan follow-ups — type-check, coverage, measured report", "", "", "open"),
    ("F4.1", "F4", "Type-check step in CI (mypy)",
     "`mypy --ignore-missing-imports -p app` exits 0 in aina-out/barnboard/app (9 errors today); a mypy step "
     "in milkpost.yml and ci.yml; both Actions runs green; existing tests pass; if app code changed, "
     "vercel --prod and live /healthz 200", "ci", "open"),
    ("F4.2", "F4", "Coverage to 60%",
     "pytest --cov=app --cov-fail-under=60 passes locally (53% today) and the flag is in both workflows; "
     "both Actions runs green", "ci", "open"),
    ("F4.3", "F4", "Measured coverage visible to the scanner",
     "Cobertura report committed at aina-out/barnboard/app/coverage.xml and mirrored; CI fails when the "
     "committed line-rate differs from the fresh run by more than 1 point (stale guard, shown failing once "
     "then passing)", "mirror", "open"),
    ("F4.4", "F4", "Re-scan and refresh the comparison",
     "after a re-mirror, a new scan saved under scans/; no 'type-check' finding; Unit Tests reads Measured "
     ">= 60% from coverage.xml; SQL-injection and known-vulnerable still 0; scans/compare.md regenerated "
     "with no untriaged rows", "verify", "open"),    # added 2026-10-12 from the second re-scan (scans/after2-2026-10-12.md)
    ("F4.5", "F4", "check_coverage.py: clear error on a malformed report",
     "check_coverage.py exits 1 with a one-line message (no traceback) for a missing file, non-XML, and a "
     "root without line-rate; exits 0 on the real coverage.xml; both workflows green", "ci", "open"),
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
    lines = ["# MilkPost TestForge-fix (F) arc — buildplan mirror", "",
             f"_Generated by plan.py on {now()}. Do not edit by hand — regenerated on every tick._",
             "", "> Source: testforge.run scan 2026-10-12 (scans/before-2026-10-12.json), triaged in",
             "> plan-of-record.md: 2 real security findings, 7 real low-risk gaps, 41 false positives.", ""]
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
