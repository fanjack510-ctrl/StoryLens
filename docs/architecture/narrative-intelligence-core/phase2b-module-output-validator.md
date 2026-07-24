# Phase 2B Module Output Validator

Class: `DefaultModuleOutputValidator`

## Order

Schema Parse → Module DTO → Reference → Evidence → Book/Snapshot → Duplicate → Conflict → Accepted

## Behaviors

- Invalid schema rejected; unknown fields follow `unknown_field_policy` (`reject` default).
- Asset/entity/storyline/chapter refs must exist in `ReferenceResolver` when resolver sets are non-empty.
- Evidence targets validated via `EvidenceValidator` Protocol (Fake/Contract fixture until Agent Q merges).
- Cross-book / cross-snapshot rejected.
- Insufficient evidence → not accepted.
- Duplicate / conflict summaries explicit.
- Retry recommendation gated by policy + error code.
- No full raw response retention; no DB writes.
- `fake=true` without `force_accept` → `accepted=false`.
