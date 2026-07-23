# Phase 1B Known Limitations

## Out of scope (by design)

- No Phase 2 whole-book analysis engine or model invocation
- No Narrative Pattern data tables (`narrative_patterns`, etc.)
- No Pattern Map product API routes or Pro navigation
- No automatic Asset/Relation merge when entities merge
- No UI for user-authored Assets without evidence (tracked limitation)
- No graph database or pattern recognition engine

## Caller responsibilities

- **`identity_fingerprint`** for Relations (and Assets) must be stable and meaningful; empty fingerprint falls back to random UUID (independent relation)
- **`attributes_json.entity_ids` / `storyline_ids`** are optional; Pattern projection reads them but does not validate Entity/Asset FKs
- Entity merge does **not** rewrite Asset `attributes_json` entity references

## Evidence / snapshot

- User-origin Versions may omit snapshot in candidate creation (soft gate); canonical path still requires completed snapshot + support evidence
- Evidence text is always recovered via Snapshot APIs, not stored inline

## Migration / schema

- Revised unpublished migration 006 checksum differs from earliest Agent D draft — expected for dev-period integration
- No automatic backfill of legacy characters into `narrative_entities`

## Pattern projection

- `build_pattern_projection_input` is internal-only; maps to future Pattern Map DTOs in Phase 1D
- `userStatus` / edge UI taxonomy mapping not implemented in 1B
