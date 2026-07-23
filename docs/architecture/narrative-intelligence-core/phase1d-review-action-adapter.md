# Phase 1D Review Action Adapter (Agent L)

Change: `CHG-20260723-029`  
Service: `apps/api/app/narrative_core/services/review_action_adapter.py`

## API

| Method | Purpose |
|--------|---------|
| `build_review_action_request` | Construct validated `NarrativeReviewActionRequest` |
| `validate_review_action` | Contract gates (idempotency, actor, no `is_canonical`) |
| `submit_review_action` | Dispatch to Phase 1B Asset / Relation / Conflict services |

## Actions

`confirm` · `correct` · `reject` · `lock` · `unlock` · `mark_stale` · `resolve_conflict` · `dismiss_conflict`

## Rules

1. `expected_version` concurrency guard (adapter-local `REVIEW_EXPECTED_VERSION_MISMATCH`).
2. `idempotency_key` replay returns prior result.
3. `correct` creates a **new** Version; copies base Evidence by default; never overwrites prior row.
4. `confirm` requires support Evidence.
5. `reject` is soft (row retained).
6. `lock` / `unlock` are explicit on stable Asset/Relation.
7. Frontend must not set `is_canonical` (rejected in payload).
8. Audit contract excludes paragraph body fields.
9. Conflict resolve normalizes `schema=analysis_conflict_resolution`.

## Production routes

**Not opened.** Formal `POST /api/v1/narrative-review-actions` remains Integration-owned.

### Integration Issue

- **II-REVIEW-ROUTE-001**: Wire `NarrativeReviewActionAdapter` to contract route without Pro gating; keep Run create disabled.
