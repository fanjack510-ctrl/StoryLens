# PUBLIC / PRIVATE CONTRACT FREEZE

**Status:** FROZEN  
**Canonical product SoT:** `ChapterFunctionsResultV2`（Public product contract）

## Boundary

| Layer | Owns | Must not own |
|---|---|---|
| Public product | V2 wire DTO/schema；API envelope；Asset materialization；Evidence binding；capability；Free stage orchestration | Prompt bodies；provider model choice；raw provider JSON as SoT |
| Private engine | Runner；prompt pack；controlled label normalize/repair；batch context；provider unit payloads → V2-shaped structured output | Free HTTP routes；SQLite schema；Desktop UI；capability registry |
| Lab | Adapter from Private → Lab `ChapterFunctionsResultDto` V1 | Free product SoT |
| Pro Insights | `ChapterFunctionsResultV1` insights contract（different） | Free SoT / Free assets |

## Shared identifiers（must match）

| Item | Freeze value |
|---|---|
| Module key | `chapter_functions` |
| Asset type | `chapter_function` |
| Stage code | `synthesize_chapter_functions` |
| Provider unit | `chapter_functions` |
| Contract version wire | `v2` |
| Label policy | CONTROLLED（see FUNCTION_LABEL_POLICY_FREEZE） |

## Mapping rule

```
Private structured output
  → Public V2 validator / mapper
  → Narrative Asset (chapter_function)
  → GET .../chapter-functions
```

Lab V1 DTO remains for Lab results path only（adapter）.  
`function_labels[]` Lab shape may be **derived** from V2 `primary_function` + `secondary_functions` for compatibility；**never** reverse Free SoT.

## Sync obligation

Private `WHOLE_BOOK_STAGE_CODES_V1`（or equivalent）must include `synthesize_chapter_functions` in the same Change that wires Public Free stage — Agent1 owns both worktrees.
