# Phase 2B-R1 Private Lab Runtime Verification (Agent V / CHG-047)

## Directed test

```text
D:\Dstorylens\.venv\Scripts\python.exe -m pytest
  apps/api/tests/test_narrative_phase2br1_private_lab_runtime.py -q
```

Result (Agent V): **26 passed**

## Coverage map (task §十八)

| # | Topic | Covered by |
|---|-------|------------|
| 1–5 | Auth / disabled / production / loopback / marker | `test_*rejected`, `test_private_lab_default_false` |
| 6–11 | Port rejects + zero DB | `test_*_reject_zero_runs`, `test_precreate_failure_zero_candidates` |
| 12–18 | Run/10 stages/skip/registry/concurrency/idempotency/metadata | `test_create_*`, `test_task_registry_*`, `test_concurrency_*`, `test_create_idempotency` |
| 19–24 | Four modules sequential / partial | `test_sequential_four_modules_executor`, `test_partial_result_on_cancel` |
| 25–34 | Persistence flags / dedupe / no canonical | `test_phase1b_sink_*`, `test_duplicate_dedupe_*` |
| 35–38 | Cancel / resume / retry / recovery | `test_cancel_resume_retry_recovery` |
| 39–42 | Result API / secrets absent | `test_result_api_readable_and_safe` |
| 43–47 | No HTTP/model; formal disabled; default false; no migration | `test_no_http_*`, `test_production_openapi_*`, `test_version_unchanged` |

HTTP surface also covered by `test_http_api_create_get_stages` (preflight/estimate/create/get/stages).

## Gates (public)

```text
scripts/check_project.py
scripts/version_manager.py check
scripts/change_registry.py check
scripts/check_capability_keys.py
git diff --check
```

## Non-goals verified

- No live Provider HTTP
- No Credential store reads
- No formal Prompt bodies in public docs/tests
- No `main.py` / shared Settings edits by Agent V
- VERSION remains 1.0.5
