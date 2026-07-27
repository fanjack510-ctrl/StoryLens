# Phase 1C Capability Contract

Unified canonical capability keys replacing scattered Pro / VIP strings.

## Canonical keys (`CapabilityKey`)

| Key | Shipped (1C) | preview_visible | License | Pro-gated run |
|-----|--------------|-----------------|---------|---------------|
| `whole_book_analysis` | false | **true** (availability=preview) | yes | **yes** |
| `narrative_asset_library` | false | false | no | **no** (foundation storage) |
| `story_lab` | false | false | yes | yes |
| `cross_book_search` | false | false | yes | yes |
| `advanced_export` | false | false | yes | yes |

Aligns with backend `CANONICAL_FEATURES` / desktop `PRO_FEATURE_KEYS`.
`preview_visible=true` does **not** imply `allowed=true`. Default Decision remains
`CAPABILITY_NOT_SHIPPED` / `allowed=false`.

Unsupported analysis mode uses `CAPABILITY_MODE_NOT_SUPPORTED` (not
`CAPABILITY_UNKNOWN`). Unknown capability keys still use `CAPABILITY_UNKNOWN`.
Modes are never CapabilityKeys.

## Service Protocol (`CapabilityService`)

`evaluate_capability`, `require_capability`, `list_capabilities`, `get_capability_metadata`, `evaluate_mode`, `evaluate_quota`, `reserve_usage`, `release_usage`, `commit_usage`.

## Decision types

- `CapabilityMetadata` — frozen registry row
- `CapabilityDecision` — pre-evaluated gate passed to engine
- `evaluate_from_metadata()` — pure helper for contract tests

## Asset API boundary

Public narrative entity/asset/relation APIs **must not** call Pro gating. Only `whole_book_analysis` *runs* require capability evaluation. See `is_pro_gated_capability()` and `NARRATIVE_FOUNDATION_CAPABILITY_KEYS`.

Registry: `apps/api/app/narrative_core/capability_registry.py`.
