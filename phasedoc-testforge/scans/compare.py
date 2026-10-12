#!/usr/bin/env python3
"""Before/after comparison of two testforge.run reports (arc leaf F3.2).

Usage: python3 compare.py before.json after.json > compare.md

Prints each dimension's score before -> after, then every finding still present
in the after report with its triage verdict from the plan of record.
"""
from __future__ import annotations

import json
import sys

# Triage verdicts from plan-of-record.md, matched on finding title substrings.
VERDICTS = [
    ("SQL Injection", "false positive (whitelisted table), pattern removed in F0.3"),
    ("sql string interpolation", "false positive (hardcoded table list), pattern removed in F0.3/F0.4"),
    ("int coercion", "false positive: env defaults, hex digests, typed Form params"),
    ("loose equality", "false positive: vendored htmx.min.js"),
    ("N+1", "false positive: vendored htmx.min.js"),
    ("Mutation", "false positive: analyzer counts only JS assertions"),
    ("API versioning", "false positive: /api/v1 exists"),
    ("Auth Endpoints Not Rate Limited", "false positive: POST /login has a per-IP window"),
    ("No Caching", "partly addressed: Cache-Control on /api/v1 (F2.2)"),
    ("feature-flag", "not applicable: solo demo"),
    ("Feature-flag", "not applicable: solo demo"),
    ("product analytics", "not applicable: solo demo"),
    ("CODEOWNERS", "not applicable: solo demo"),
    ("observability", "declined for now (F2.4 decision)"),
    ("Observability", "declined for now (F2.4 decision)"),
    ("property-based", "not applicable: JS-only check"),
    ("visual regression", "not applicable: JS-only check"),
    ("License audit", "not applicable: no node_modules in a Python app"),
    ("OWASP Top 10 analyzer coverage", "note about the analyzer itself"),
    ("No README", "real: fixed by F1.1; should be gone after the re-mirror"),
    ("without response_model", "real, low: the 6 JSON routes are documented (F2.3); HTML routes left alone"),
    ("mutation score", "false positive: analyzer counts only JS assertions"),
    ("known vulnerabilit", "REAL: should be gone after F0.1; investigate"),
    ("No CI/CD", "real: fixed by F1.2; should be gone after the re-mirror"),
    ("A03:2021", "false positive (same SQL findings), pattern removed in F0.3"),
    ("package-lock.json", "analyzer looks only for package-lock.json; requirements.lock added (F1.4)"),
]


def score(dim: dict):
    for k in ("score", "coverage"):
        if isinstance(dim.get(k), (int, float)):
            return dim[k]
    if "findings" in dim and isinstance(dim["findings"], int):
        return f"{dim['findings']} findings"
    return None


def findings(dim: dict) -> list[dict]:
    for k in ("items", "findings"):
        v = dim.get(k)
        if isinstance(v, list):
            return [f for f in v if isinstance(f, dict)]
    return []


def verdict(title: str) -> str:
    for needle, v in VERDICTS:
        if needle in title:
            return v
    return "**not triaged: review**"


def main(before_path: str, after_path: str) -> None:
    before, after = json.load(open(before_path)), json.load(open(after_path))
    dims = [k for k, v in after.items() if isinstance(v, dict) and k != "codebase"]
    print("# MilkPost: TestForge before/after\n")
    print(f"Before: `{before_path}` ({before.get('analyzedAt', '?')})  ")
    print(f"After: `{after_path}` ({after.get('analyzedAt', '?')})\n")
    print("| Dimension | Before | After |\n| --- | --- | --- |")
    for d in dims:
        print(f"| {d} | {score(before.get(d, {}))} | {score(after[d])} |")
    nb = sum(len(findings(v)) for k, v in before.items() if isinstance(v, dict))
    na = sum(len(findings(after[d])) for d in dims)
    print(f"\nFindings: {nb} before, {na} after.\n")
    print("## Findings still present\n")
    print("| Dimension | Severity | Finding | Verdict |\n| --- | --- | --- | --- |")
    for d in dims:
        for f in findings(after[d]):
            t = (f.get("title") or "").replace("|", "/")
            print(f"| {d} | {f.get('severity', '')} | {t} | {verdict(t)} |")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: compare.py before.json after.json")
    main(sys.argv[1], sys.argv[2])
