# Phase 1D-P Conflict Center Contract

`ConflictCenterItemDto` + supported user actions. Blocking conflicts are **never** auto-resolved.

## ConflictCenterItemDto

| Field | Notes |
|-------|-------|
| `conflict_id` | |
| `conflict_type` | |
| `severity` | |
| `status` | open / resolved / dismissed / deferred … |
| `left_ref` | left Asset/Relation/Version ref |
| `right_ref` | right ref |
| `description` | user-readable |
| `affected_modules` | module keys |
| `affected_chapters` | |
| `evidence_refs` | `WholeBookEvidenceRefDto[]` |
| `created_at` | |
| `resolution` | optional resolution payload |
| `allowed_actions` | backend-authored |

## Supported actions

| Action | Behavior |
|--------|----------|
| View both versions | Compare left/right refs |
| Compare Evidence | Via evidence_refs |
| Keep old canonical | Explicit user choice |
| Confirm new version | Via review action + versioning |
| Create corrected version | `correct` → new Version |
| Dismiss | Soft dismiss; auditable |
| Defer | Delay handling |

## Hard rules

1. **Blocking conflicts MUST NOT be auto-resolved by the system.**
2. Resolve requires schema/version on resolution payload (see Review Contract).
3. Frontend does not write `is_canonical` directly.
4. Conflict ≠ module `failed`; surface conflict tip on results + Conflict Center.
5. Reuses Phase 1B `analysis_conflicts` / relation-asset conflict semantics — no second conflict store.

See [phase1d-evidence-review-contract.md](./phase1d-evidence-review-contract.md), [phase1b-relation-contract.md](./phase1b-relation-contract.md).
