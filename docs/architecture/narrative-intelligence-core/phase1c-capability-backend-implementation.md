# Phase 1C Capability Backend Implementation

Change: `CHG-20260723-023`  
Agent: H  
Branch: `feature/narrative-phase1c-capability-backend`  
Baseline: `a275e837a392a1d21a11040cc71670548b1160ef`

## Scope delivered

| Component | Path |
|-----------|------|
| CapabilityService | `apps/api/app/narrative_core/services/capability_service.py` |
| Quota skeleton | `apps/api/app/narrative_core/services/quota_service.py` |
| API payloads | `apps/api/app/narrative_core/services/capability_api_payloads.py` |
| HTTP router | `apps/api/app/routers/capabilities.py` |
| Run permission guard | `apps/api/app/narrative_core/services/run_permission_guard.py` |
| License compat adapter | `apps/api/app/services/entitlement.py` (`can_use_feature`) |
| Tests | `apps/api/tests/test_narrative_phase1c_capability_backend.py` |

## CapabilityService

Implements Protocol methods:

- `evaluate_capability` / `require_capability`
- `list_capabilities` / `get_capability_metadata`
- `evaluate_mode`
- `evaluate_quota` / `reserve_usage` / `release_usage` / `commit_usage`

Decision priority:

1. Unknown key → `CAPABILITY_UNKNOWN`
2. `shipped=false` → `CAPABILITY_NOT_SHIPPED` (preview_visible ≠ usable)
3. License missing / expired / invalid
4. Quota exceeded
5. Available / preview-only

Backend recomputes `allowed`; frontend-supplied `allowed` is stripped from context.

## Metadata

Uses frozen `CAPABILITY_REGISTRY` (Phase 1C-P). Tests may inject `metadata_overrides` / `license_state` / quota policy overrides without touching production registry or SQLite commercial tables.

`PRO_CAPABILITIES_SHIPPED` remains `false`. Registry `shipped` flags remain `false`.

## API

- `GET /api/v1/capabilities`
- `GET /api/v1/capabilities/{key}`

Returns Decision + Metadata DTOs. No license secrets. `run_creation_enabled=false`. Whole-book run creation is not registered.

Internal preflight helper exists in `run_permission_guard.preflight_whole_book_run` (DTO only; HTTP deferred to Integration).

## Explicit non-goals

Engine, Prompt, model calls, frontend, payment DB, Quota DB tables, schema edits, VERSION bump, publish/push.
