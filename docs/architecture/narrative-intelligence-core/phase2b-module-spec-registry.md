# Phase 2B Module Spec Registry

Authority: `WholeBookModuleExecutionSpec` (Phase 2B-P freeze).

## API

`register` · `get` · `list` · `validate` · `planning_stages` · `producer_stages` · `result_dependencies` · `supported_modules` · `export_legacy_compatibility_views`

## Frozen first-four

`book_overview` · `structure_stages` · `chapter_functions` · `storylines`

## Rules

1. Module key unique; module version required.
2. Stage keys must be catalog-legal.
3. Producer ⊆ planning (`required_stage_keys`).
4. Result dependencies are legal stages; first-four stay consistent with legacy ENGINE/PRODUCT maps via `validate_first_four_consistent_with_legacy_maps()`.
5. Compatibility adapters export derived maps — no fourth FE mapping table.
6. Registry does not access ORM or Provider.
