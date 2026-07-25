# Contract Amendment — STEP 2.2 Walking Skeleton Gate

**Change:** CHG-20260725-003
**Step:** STEP-2.2
**Amends:** `storylens-1.1.0-native-overview-contract.md` (gate semantics only)
**Does not amend:** DTO field shapes, Migration 011, Enum wire values, Error code identifiers, Fixture `combined_sha256`.

## Amendment

1. `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=True` **remains** for the legacy whole-book analysis production create path and Phase 2A/2B static gates.
2. Native Overview walking skeleton APIs (`preflight` extensions for native mode, `POST .../whole-book-runs`, `GET .../whole-book-runs/{id}`, `GET .../overview`) are gated by **`PRO_NATIVE_OVERVIEW_ENABLED`** (env; default **false**).
3. Backend must enforce the flag independently of any frontend presentation.
4. When enabled, Create Run must bind Fixture Engine identity:

   - `engine_id = fixture-native-overview-v1`
   - `engine_version = walking-skeleton-1`
   - `prompt_version = fixture-no-prompt`

5. Responses / preflight must warn that Fixture execution does not call a provider. Do not describe results as production AI analysis.
6. Walking-skeleton metadata is expressed via engine identity + warnings — **no** new DB columns for `engine_mode` / `walking_skeleton` / `production_ready`.
7. STEP 2.5 real Provider work may not default-enable this flag.

## Code anchors

- `apps/api/app/narrative_core/contracts/pro_native_overview_flags.py`
