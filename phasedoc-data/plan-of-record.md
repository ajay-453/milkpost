# Barnboard Data Platform — Plan of Record

Internal, builders-facing. This arc turns barnboard's farm records into an
interoperable, extensible data platform with trained models and served
inference, runnable on every environment and platform we target (bare metal
under PM2, containers via Docker, and a laptop with nothing but Python 3.12).
The arc is governed by the data-team skill's eight-role pipeline; the
role-by-role fit assessment lives in [roles-vs-needs.md](roles-vs-needs.md)
and the free-data research in [data-research.md](data-research.md).

## D0 — Data pipeline foundation

The data-team spine (Data Architect → Data Engineer → Data Designer → Data
Analyst) has been run over barnboard's five domain tables (cows, milk logs,
treatments, breedings, sales — authentication tables were deliberately
excluded as personally identifiable information). That run produced a typed
bronze layer, cleaned silver, modeled gold, a first semantic layer, and a
governance envelope with lineage. This phase makes that run repeatable: a
stdlib-only source exporter, a committed pipeline configuration, and this
plan's two reports landed in the repository.

## D1 — Interoperability: open data contracts

Today the app exports CSV and nothing else machine-readable. This phase adds
the contracts that make the data usable by any other system: a whitelisted
read-only JSON API with a versioned envelope, CSV import so export/import
round-trips (data can leave and come back), a versioned schema endpoint that
any consumer can program against, and a rehearsed SQLite online-backup drill
proving the single-file database is genuinely portable.

## D2 — Extensibility: the governed semantic layer

The pipeline auto-synthesized placeholder metrics, one of which sums a ratio —
exactly what the governance guard exists to prevent. This phase replaces them
with properly authored metrics (average daily yield per cow, yield by breed,
sales revenue, average price per litre), documents the extension path so a new
metric is a JSON definition with zero engine changes, and proves the pipeline
is idempotent (re-runs produce identical numbers).

## D3 — Free web data: research and acquisition

Free, openly licensed web data is researched and inventoried with licenses,
formats, and the model use-case each source serves (yield forecasting,
breeding outcomes, health-risk signals, milk-price series, breed benchmarks —
including desi breeds: Gir, Sahiwal, Murrah buffalo). Selected datasets are
fetched by a checksummed fetcher into a local reference store, so training and
inference never depend on a website staying up.

## D4 — Models: train and evaluate on gold

Three small, fully reproducible models trained on the gold layer: a per-cow
seven-day milk-yield forecast, anomaly scoring that flags yield drops against
the forecast (must catch the seeded decliner with zero false positives), and a
month-end revenue projection. Every model is standard-library Python with
versioned parameters, and each must beat its naive baseline on a holdout
window before it counts — the evaluation report is a committed artifact.

## D5 — Inference: serve predictions everywhere

The models go live: a forecast API endpoint in the app, a forecast panel on
the dashboard, and versioned model artifacts that hot-reload — bumping a
version file changes served numbers with no code changes. Inference runs
wherever the app runs, with no extra dependencies.

## D6 — Every environment, every platform

The same stack proven on each target: Docker image (build currently blocked on
this host — no Docker installed — honestly tracked as open until run on a
Docker-capable machine), bare-metal PM2 with reboot persistence for the app
and both phasedoc cockpits, an automated pytest suite over the contracts and
models, and the whole arc living on GitHub with the buildplan mirror committed
on every tick.
