# Phase 1C Agent G — Mock Engine Boundary

**Change:** CHG-20260723-022  
**Engine id:** `mock_whole_book_v0`  
**Engine version:** `0.1.0-mock`

## Allowed

- Validate WholeBook requests (including injected CapabilityDecision)
- Build deterministic stage plans from the frozen catalog
- Return fixed structured stage results
- Simulate checkpoint / pause / resume / cancel / token / cost
- Write **candidate-only** synthetic Asset / Relation / Evidence via adapters
- Invoke ArtifactWriter / ConflictSink for verification

## Forbidden

- Local or cloud model calls
- Reading real novel body for analysis conclusions
- User-facing literary conclusions derived from a specific book
- Book-specific customization of outputs
- Auto-confirm / correct / lock assets
- Overwriting user canonical versions
- Serving as the production WholeBook run engine (`production_mode` factory refuses Mock)

## Output markers

Every mock artifact must be recognizable as non-production:

- Metrics / health: `mock=true`, `synthetic`, `non_production` / `production_ready=false`
- `origin_type=system`
- `source_fingerprint` contains `mock|synthetic|non-production`
- Asset / Relation versions remain `review_status=candidate` and `is_canonical=false`

## Health check

Returns at least: `engine_id`, `engine_version`, `available`, `supported_modes`, `supported_modules`, `mock`, `detail`, `checked_at` (plus `healthy` for Phase 1C-P compatibility).
