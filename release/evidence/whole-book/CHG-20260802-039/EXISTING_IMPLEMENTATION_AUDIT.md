# EXISTING CHAPTER FUNCTIONS IMPLEMENTATION AUDIT

## Classification legend

`REUSE` · `LAB_ONLY` · `PRO_DIFFERENT` · `DEPRECATED` · `MISSING` · `EXPERIMENTAL` · `REWRITE`

## Public

| Artifact | Path | Class |
|---|---|---|
| CHAPTER_FUNCTIONS_SPEC | `private_engine_contract/module_spec.py` L117–139 | REUSE（intent） |
| ChapterFunctionsResultDto | `product_contract/module_results.py` L287–297 | LAB_ONLY → product SoT becomes **V2**（REWRITE mapping） |
| AssetType.chapter_function | `enums.py` L142 | REUSE |
| WHOLE_BOOK_STAGE_CODES_V1 | `constants.py` L12–21 | MISSING stage（add in impl） |
| Lab results API | `GET .../whole-book-runs/{id}/results/chapter_functions` | LAB_ONLY（preserve） |
| Free product API | — | MISSING |
| Capability planned | `whole_book_product_capability_v1.py` | REUSE → available in impl |
| PlannedModulePanel | Desktop Free page | REUSE shell → replace in Agent2 |
| Desktop DTO | `features/wholeBook/contracts/moduleResults.ts` | LAB_ONLY（adapter after V2） |
| Fixture/replay suite | structure-like | MISSING for Free |
| normalize_function_labels | manifest only | MISSING implementation |

## Private

| Artifact | Path | Class |
|---|---|---|
| ChapterFunctionsRunner | `modules/chapter_functions/runner.py` | REUSE + harden（CONTROLLED labels） |
| GENERAL_LABELS | runner.py L13–28 | REUSE as wire enum base（freeze adjusts） |
| prompt pack | `prompt_packs/chapter_functions/` | LAB_ONLY → rewrite prompts under freeze labels（impl） |
| max_chapters_per_batch=8 | `context/strategy.py` | REUSE |
| module_extra validation | labels list-only | REWRITE（full V2 validator） |
| repair normalize_function_labels | declared, not coded | MISSING → REQUIRED in impl |
| Pro ChapterFunctionsResultV1 | `whole_book_insights/contracts.py` | **PRO_DIFFERENT** — never Free SoT |

## Forbidden reuse

- Pro Insights aggregation as Free product payload  
- Novel-specific label branches  
- Treating structure `narrative_function` as chapter_functions taxonomy  
