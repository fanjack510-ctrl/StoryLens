# Phase 2B Context Bundle Mapping

**Change:** CHG-20260723-040
**Module:** `apps/api/app/narrative_core/services/whole_book_context_bundle_mapper.py`

## Contract freeze

`ContextBundle` (private engine contract) is the cross-component transport shape. `WholeBookContextBundle` (runtime model) carries pipeline metadata, coverage, warnings, and mode — it must convert explicitly via `WholeBookContextBundleMapper`. No implicit field compatibility.

## Mapper API

| Method | Purpose |
|--------|---------|
| `to_contract(bundle)` | Runtime → contract; validates compatibility first |
| `from_contract(contract, ...)` | Contract → runtime; optional coverage/plan/mode injection |
| `validate_compatibility(bundle)` | Runtime bundle schema/version/units checks |
| `validate_contract(contract)` | Contract schema/version/units checks |
| `round_trip(bundle)` | `from_contract(to_contract(bundle))` for hash stability |

## Hash / fingerprint fields preserved

Round-trip and contract mapping preserve:

- `bundle_hash`
- `snapshot_content_hash`
- `chapter_hashes` / `paragraph_hashes`
- `configuration_fingerprint`
- `pipeline_version`
- `context_schema` / `context_schema_version`

Integration test `test_context_bundle_mapper_round_trip` asserts hash equality and no `full_text` in public dict serialization.

## Paragraph grouping interaction

`ParagraphGroupingPolicy` feeds `UnitBuildConfig.grouping` when session is bound. Defaults `max_paragraphs_per_group=40`, `overlap_paragraphs=2` are generic initial values (`defaults_are_initial_only=True` in grouping dict). Overrides via `with_overrides(provider_context_limit, quality_profile_key)` affect `configuration_fingerprint` and bundle hash — metamorphic tests prove fingerprint divergence on policy/limit change.

## Native vs Enhanced

| Mode | Builder path | Notes |
|------|--------------|-------|
| Native | `build_native_context_bundle` | Snapshot-only units |
| Enhanced | `build_enhanced_context_bundle` | `AuxiliaryContextSource.load_auxiliary`; degraded on stale/missing aux |

Enhanced path attaches aux inventory into coverage notes without embedding bodies. Scene ORM E2E not covered — fixtures use `FixtureAuxiliaryContextSource`.

## Runtime registration

After build, composition root registers contract bundles on:

- `runtime.contract_bundles[ref]` and `[bundle_hash]`
- Each module runner's `context_bundles` dict
- `InMemoryContextBundleCache` keyed by snapshot hash + module spec versions + fingerprint
