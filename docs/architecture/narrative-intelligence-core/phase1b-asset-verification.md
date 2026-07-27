# Phase 1B Agent E — Asset Verification

**Change:** CHG-20260723-018  
**Status:** tested (directed; not full suite / not publish)

## Directed tests run

```text
.\.venv\Scripts\python.exe -m pytest `
  apps/api/tests/test_narrative_asset_service.py `
  apps/api/tests/test_narrative_asset_evidence.py -q
```

**Result:** 24 passed

### Coverage checklist

| # | Case | Status |
|---|------|--------|
| 1 | Migration 007/008 order | pass |
| 2 | 007/008 idempotent + stable checksum | pass |
| 3 | Legacy DB upgrade | pass |
| 4 | Create candidate Asset | pass |
| 5 | Add Version | pass |
| 6 | Candidate not auto-canonical | pass |
| 7 | Confirm sets canonical | pass |
| 8 | Correct creates new Version | pass |
| 9 | Rejected cannot be canonical | pass |
| 10 | At most one canonical / asset | pass |
| 11 | Model does not overwrite user confirmed canonical | pass |
| 12 | Locked blocks model canonical switch | pass |
| 13 | Locked still allows new candidate | pass |
| 14 | Stale mark / clear | pass |
| 15 | Supersede (+ list exclude) | pass |
| 16 | Asset Key stable | pass |
| 17 | book_id isolation | pass |
| 18 | COMPLETED Snapshot evidence OK | pass |
| 19 | BUILDING/FAILED/INVALID rejected | pass |
| 20 | Snapshot book mismatch | pass |
| 21 | Paragraph hash mismatch | pass |
| 22 | Offset OOB | pass |
| 23 | Evidence role validation | pass |
| 24 | Old Snapshot evidence reproducible | pass |
| 25 | SQLite FK | pass |
| 26 | SQLite integrity (unique key / canonical) | pass |

## Gates

```text
python scripts/version_manager.py check   # passed (VERSION 1.0.5)
python scripts/change_registry.py check   # passed
git diff --check                          # passed
```

Also re-ran `test_narrative_phase1bp_contract.py` — passed (no regression).

## Explicitly not run

- Full Pytest / Vitest suite
- Production build / publish / push
- Pattern Map product wiring
- AnalysisConflict table service (Agent F)

## Integration hand-off

- `AssetCanonicalConflictRequest` must be persisted by Agent F / Integration as `analysis_conflicts`.
- Relation migrations 009/010 and Entity 006 are out of this Change.
- Do not dual-write old Reader Journey / Hook / Scene JSON.
