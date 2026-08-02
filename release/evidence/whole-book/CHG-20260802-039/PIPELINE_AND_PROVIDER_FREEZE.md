# PIPELINE AND PROVIDER UNIT FREEZE

## Stage code

```
PIPELINE STAGE：synthesize_chapter_functions
```

Insert into Free product stage list:

```
… → synthesize_overview
  → synthesize_structure_stages
  → synthesize_chapter_functions
  → project_result
  → finalize
```

## Provider unit

```
PROVIDER UNIT：chapter_functions
Kinds：
  - chapter_functions_initial
  - chapter_functions_contract_repair
```

## Execution rules

| Topic | Freeze |
|---|---|
| State machine | Reuse whole-book Run/Stage — **no second machine** |
| Pause / resume / cancel | Same semantics as overview/structure |
| Cost estimate | MUST include `chapter_functions` when capability available |
| Batching | `max_chapters_per_batch = 8`（Private strategy evidence） |
| Resume dedupe | Checkpoint per batch / chapter set；duplicate resume → **0** extra provider calls |
| Structure absent | Still execute（see WB21_CONTEXT_BOUNDARY_FREEZE） |
| Legal insufficient | completed |
| Illegal after repair | failed |
| Asset dedupe | no duplicate canonical create on resume |

## Private / Public sync note

Private `WHOLE_BOOK_STAGE_CODES_V1` currently lags Public structure stage — implementation must align **both** worktrees to include `synthesize_chapter_functions` without inventing a second contract.
