# MilkPost: TestForge before/after

Before: `scans/before-2026-10-12.json` (2026-10-12T06:38:59.979Z)  
After: `scans/after2-2026-10-12.md` (2026-10-12T10:06:09.855Z)

| Dimension | Before | After |
| --- | --- | --- |
| security | 3 findings | 100 |
| kubernetes | 0 | N/A |
| owasp | 80 | 80 |
| supplyChain | 58 | 100 |
| license | 89 | 89 |
| unit | 0 | 71 |
| mutation | 39 | 40 |
| propertyBased | 50 | 50 |
| edgeCases | 58 | 68 |
| contract | 96 | 96 |
| predictive | 100 | 100 |
| nPlusOne | 71 | 71 |
| deadCode | 100 | 100 |
| load | 63 | 68 |
| chaos | 100 | 100 |
| agentic | 83 | 91 |
| accessibility | 100 | N/A |
| visualRegression | 100 | 100 |
| vision | 80 | 81 |
| scope | 0 | 100 |
| stack | 75 | 80 |
| dora | 30 | 65 |

Findings: 49 before, 37 after.

## Findings still present

| Dimension | Severity | Finding | Verdict |
| --- | --- | --- | --- |
| security | medium | Missing Rate Limiting | false positive: rule only looks for a dependency named *rate-limit*/*ratelimit*; POST /login has an in-code per-IP limiter. Newly visible because F1.5 mirrored requirements.txt (fastapi detected) |
| owasp | low | OWASP Top 10 analyzer coverage: 80% (8/10) | note about the analyzer itself |
| supplyChain | low | No package-lock.json found | analyzer looks only for package-lock.json; requirements.lock added (F1.4) |
| license | low | License audit could not run — no node_modules/ found | not applicable: no node_modules in a Python app |
| mutation | high | Estimated mutation score: ~40% (heuristic) | false positive: analyzer counts only JS assertions |
| mutation | low | Mutation testing tool not configured | false positive: analyzer counts only JS assertions |
| propertyBased | medium | No property-based testing framework detected | not applicable: JS-only check |
| edgeCases | medium | int coercion unchecked (tools/train_models.py:147) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (api/index.py:83) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (api/index.py:269) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (api/index.py:276) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/check_coverage.py:18) | real, very low: CI-only script; a malformed coverage.xml fails with a traceback instead of a message (F4.5) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/main.py:130) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/main.py:131) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/main.py:47) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/main.py:1212) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/main.py:46) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/main.py:50) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/main.py:926) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/db.py:317) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/db.py:452) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/db.py:510) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/db.py:231) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/db.py:232) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | medium | int coercion unchecked (aina-out/barnboard/app/app/db.py:233) | false positive: env defaults, time.time(), hex-digest slices, typed Form(int), internal metric config (all re-checked on the after scan) |
| edgeCases | low | loose equality (aina-out/barnboard/app/static/js/htmx.min.js:1) | false positive: vendored htmx.min.js |
| contract | medium | 42 FastAPI endpoint(s) without response_model | real, low: the 6 JSON routes are documented (F2.3); HTML routes left alone |
| nPlusOne | high | Potential N+1 Query in while | false positive: vendored htmx.min.js |
| nPlusOne | high | Potential N+1 Query in while | false positive: vendored htmx.min.js |
| agentic | high | Auth Endpoints Not Rate Limited | false positive: POST /login has a per-IP window |
| visualRegression | low | No UI files for visual regression | not applicable: JS-only check |
| vision | high | No observability stack detected | declined for now (F2.4 decision) |
| vision | medium | No feature-flag platform | not applicable: solo demo |
| vision | high | No product analytics dependency | not applicable: solo demo |
| dora | medium | No observability dependency detected | declined for now (F2.4 decision) |
| dora | low | No feature-flag platform detected | not applicable: solo demo |
| dora | low | No CODEOWNERS file detected | not applicable: solo demo |
