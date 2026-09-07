# Extending the semantic layer (D2.2)

Adding a metric requires **zero engine changes**. The engine (the data-team
skill's `designer.py`/`analyst.py`) is never edited; a metric is one JSON file
in this directory.

## The recipe

1. **Write one JSON file** here, named `<metric_id>.json`:
   - `metric` (id), `label`, `description` — the label is also how the analyst
     matches questions, so write it the way you'd say it.
   - `aggregation`: `sum`/`count`/`min`/`max` (additive), `avg`/`ratio`
     (recomputed, never summed up a grain), `count_distinct` (not summable),
     or `derived` with an `expression` over the rollup table's columns.
   - `rollups.daily`: the gold table it binds to (`gold.<table>`).
   - `dimensions`: gold columns it may be broken down by (`"by <dim>"` in a
     question).
   - `owner`, `unit`, `round`, `version`, `changelog` — governance metadata.
2. **Re-run designer + analyst** (config in `data-team.yaml`):
   ```
   python3 tools/make_sources.py
   python3 "$SKILL_SCRIPTS/run_pipeline.py" --slug barnboard --sources data-team-sources/*.csv
   python3 tools/enrich_gold.py               # cow-day grain gold fact
   PYTHONPATH=$SKILL_SCRIPTS python3 $SKILL_SCRIPTS/designer.py --run-root . --slug barnboard --metrics-dir semantic-metrics
   PYTHONPATH=$SKILL_SCRIPTS python3 $SKILL_SCRIPTS/analyst.py  --run-root . --slug barnboard --ask "..."
   ```
   where `SKILL_SCRIPTS=~/.claude/plugins/cache/claude-data-skills/data-team/0.1.0/skills/run/scripts`.
3. The metric appears versioned in `data-team-out/barnboard/semantic/metrics/`,
   conformance-checked in `semantic/conformance.json`, and answerable by the
   analyst when a question contains its id or label.

## Rules the guard enforces

- An authored metric with the same id as an auto-proposed one **overrides** it
  (see `price_per_litre.json`, which replaced a governance-violating sum).
- Ratio/average/derived metrics are **recomputed** at every grain — the guard
  blocks naive rollups; never work around it by pre-summing a ratio column.
- Metrics needing a grain the gold layer lacks get a new gold fact first
  (engineer-role work — see `tools/enrich_gold.py`), then bind to it.

Worked example: `cow_days_recorded.json` in this directory was added exactly
this way and appears in the analyst report with no engine edits.
