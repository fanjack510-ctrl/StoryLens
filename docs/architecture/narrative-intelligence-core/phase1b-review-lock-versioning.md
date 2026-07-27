# Phase 1B-P — Review / Lock / Versioning Semantics

## A. Stable Identity

`NarrativeEntity.id`, `NarrativeAsset.id`, `NarrativeRelation.id` are durable identities.

## B. Version

`NarrativeAssetVersion` / `NarrativeRelationVersion` are one analysis or user-edit interpretation.

## C. Canonical

Canonical = currently adopted interpretation for a stable id.

- At most one canonical version per stable id (SQLite partial unique index).
- Transactional switch: clear previous `is_canonical`, set new, commit together.
- No circular FK `asset → version → asset`.

## D. Review Status

| Value | Meaning |
|-------|---------|
| `candidate` | Model proposal; not yet accepted |
| `confirmed` | User accepts a model version |
| `corrected` | User-created correction version (prior rows kept) |
| `rejected` | Explicitly refused |

## E. Lock

`is_locked` lives on the **stable** row, independent of `review_status`.

When locked:

- Model must not replace canonical.
- Model may still create candidate versions.
- Candidate vs locked canonical → `analysis_conflicts`.
- User may unlock explicitly.

## F. Superseded

`lifecycle_status=superseded` + `superseded_by_*_id` means the **stable identity** is replaced by another stable identity.  
This is **not** the same as keeping an older version of the same identity.

## G. Stale

`stale_at` / `stale_reason` mark that evidence or snapshot context may no longer match live book expectations; old Snapshot still reproduces historical evidence.
