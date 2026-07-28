# Legacy Whole-Book Overview Adapter Report

**Adapter:** `LegacyWholeBookOverviewV1Adapter`  
**Location (Private):** `src/storylens_private_engine/contracts/legacy_whole_book_overview_v1_adapter.py`  
**Input:** `WholeBookOverviewProjectionCandidateV1` (legacy `whole_book_overview_v1`)  
**Output:** `BookOverviewResultV1`

## Behavior

| Rule | Result |
|---|---|
| Only map explicitly present fields | YES |
| Missing fields → `insufficient_evidence` | YES |
| Missing/unmapped evidence → never `available` | YES |
| Fixture input → `result_origin=fixture` | YES |
| Formal without evidence → `partial` at best | YES |
| Does not invent `run_id` / `snapshot_id` | YES (caller supplies `run`) |
| Provider calls | 0 |
| DB writes | 0 |
| Product entry wiring | NO |
| Insights DTO treated as Native fact source | NO |

## Claim key mapping (legacy → V1)

| Legacy field | Claim key |
|---|---|
| novel_type / narrative_features | genre_and_narrative_features |
| core_setting | core_setting |
| protagonist | protagonist |
| protagonist_core_goal | protagonist_core_goal |
| primary_conflict | main_conflict |
| central_question | core_question |
| resolved_problem / ending_state | final_resolution |
| key_turning_points / climax | key_events |
| (none) | important_characters → insufficient_evidence |
| logline / synopsis | unmapped warning only |

## Tests

Private tests 06–10 cover degrade, no-available-without-evidence, fixture separation, provider=0, db=0.
