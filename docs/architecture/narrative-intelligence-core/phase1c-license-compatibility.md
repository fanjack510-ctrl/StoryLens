# Phase 1C License Compatibility

## Principle

Do **not** create a second License system. Reuse `app.services.entitlement` + `license_crypto` + `LocalLicense` SQLite rows.

## Adapter path

```
legacy / desktop caller
  → entitlement.can_use_feature(session, feature_key)
    → resolve_capability_key (canonical | legacy map)
      → DefaultCapabilityService.evaluate_capability
        → decision_to_compat_gate (legacy response shape)
```

## Legacy key map

Central table: `apps/api/app/narrative_core/capability_legacy.py` (`LEGACY_TO_CAPABILITY`).

| Legacy VIP key | Canonical CapabilityKey |
|----------------|-------------------------|
| batch_analysis | whole_book_analysis |
| novel_rhythm_map | whole_book_analysis |
| character_arc | whole_book_analysis |
| foreshadow_tracking | whole_book_analysis |
| novel_comparison | cross_book_search |
| advanced_report | advanced_export |
| inspiration_center | story_lab |

Unknown strings → `FEATURE_UNKNOWN` / `CAPABILITY_UNKNOWN`. Never silently authorized.

Analysis modes `whole_book_native` / `whole_book_enhanced` are **not** feature keys.

## Compat semantics for `enabled`

Historical `can_use_feature` answers “does this machine hold a Pro license for the feature?”, not “is the capability shipped and runnable?”.

When CapabilityService returns `CAPABILITY_NOT_SHIPPED` but edition is `pro`, the adapter still returns `enabled=True` so activation UX and existing tests keep working. Full run gates use `evaluate_capability` / `require_whole_book_run_permission` instead.

## Call sites

| Site | Status |
|------|--------|
| `entitlement.can_use_feature` | Adapter → CapabilityService |
| `desktop.get_feature_entitlement` | Still calls `can_use_feature` (compat entry) |

Recorded as `UNMIGRATED_CAN_USE_FEATURE_CALL_SITES` in `capability_service.py` until desktop migrates to Capability API DTOs.

## Forbidden

- New VIP checks in pages/APIs outside CapabilityService
- Separate Pro boolean forests
- Writing API keys / signed licenses into Capability API responses
