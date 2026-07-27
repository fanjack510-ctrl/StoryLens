# Phase 1B — Relation / Conflict Verification (Agent F)

**Change:** CHG-20260723-019  
**Worktree:** `D:\Dstorylens-wt-narrative-relations`  
**Branch:** `feature/narrative-phase1b-relations`

## Directed commands

```powershell
$env:PYTHONPATH = "D:\Dstorylens-wt-narrative-relations\apps\api"
D:\Dstorylens\.venv\Scripts\python.exe -m pytest `
  apps/api/tests/test_narrative_relation_service.py `
  apps/api/tests/test_narrative_conflict_service.py -q --tb=short

D:\Dstorylens\.venv\Scripts\python.exe scripts/version_manager.py check
D:\Dstorylens\.venv\Scripts\python.exe scripts/change_registry.py check
git diff --check
```

## Coverage map

| # | Case | Test |
|---|------|------|
| 1–2 | Migration 009/010 + idempotent checksum | `test_migration_009_010_and_idempotent` |
| 3 | Old DB upgrade | `test_upgrade_old_db_then_009_010` |
| 4 | Create candidate | `test_create_candidate_not_auto_canonical` |
| 5–6 | Book mismatch endpoints / relation book_id | `test_source_target_book_mismatch_fails`, `test_relation_book_id_mismatch_fails` |
| 7 | Direction key stable | `test_direction_key_stable_and_asymmetric` |
| 8 | Candidate not auto canonical | same as #4 |
| 9–11 | Confirm/correct/reject/one canonical | `test_confirm_correct_rejected_canonical_rules`, `test_at_most_one_canonical_and_concurrent_confirm` |
| 12–13 | Lock blocks model; allows candidate | `test_locked_blocks_model_canonical_allows_candidate` |
| 14 | Canonical needs support Evidence | `test_canonical_requires_support_not_context_alone` |
| 15–18 | Evidence valid / snapshot / hash / offset | `test_relation_evidence_valid_and_invalid_cases` |
| 19 | Stale / supersede | `test_stale_and_supersede` |
| 20–25 | Conflict open/resolve/dismiss/schema/blocking | `test_narrative_conflict_service.py` |
| 26 | Errors omit body text | asserted in mismatch/evidence tests |
| 27–28 | SQLite FK + canonical integrity | `test_sqlite_fk_and_integrity_canonical` |
| 29–31 | version_manager / change_registry / git diff --check | run in verification |

## Explicitly not run

- Full pytest suite
- Release publish / build gates
- `check_project.py` full release mode
