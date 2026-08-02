# WB-2.2 API AND PIPELINE DECISION（planning）

## Pipeline（current facts）

| Item | Current | Target (to freeze) |
|---|---|---|
| Free stage codes | No `synthesize_chapter_functions` | Likely add after `synthesize_structure_stages`, before `project_result` — **UNRESOLVED** if structure-independent |
| Provider unit | ABSENT | Likely `chapter_functions` + initial/repair kinds — **UNRESOLVED** |
| Lab order | overview → structure_stages → chapter_functions → storylines | Reference only |
| Pause/resume/cancel | Reuse whole-book run controls | REQUIRED |
| Cost estimate | Must include new unit when available | REQUIRED |
| Second state machine | Forbidden | Forbidden |
| Resume dedupe | Per-chapter / per-unit checkpoint | REQUIRED design |

**PIPELINE STAGE：** UNRESOLVED（candidate `synthesize_chapter_functions`）  
**PROVIDER UNIT：** UNRESOLVED（candidate `chapter_functions`）

## Product API（candidates — not frozen）

| Concern | Candidate | Status |
|---|---|---|
| Result list | `GET /api/v1/whole-book/runs/{run_id}/chapter-functions` | Proposed |
| Pagination | `?cursor=&limit=` or `?offset=&limit=` | **UNRESOLVED**（YES likely for long books） |
| Single chapter | `GET .../chapter-functions/{chapter_id}` or query filter | **UNRESOLVED** |
| Evidence source | Reuse existing evidence deep-link APIs | REQUIRED reuse |
| States | available / insufficient / failed / canceled / conflict / absent | REQUIRED parity with structure |
| 404 | Absent ≠ hard failure（UI） | REQUIRED |
| Lab API | Keep `.../results/chapter_functions` | PRESERVE |
| Prepare dual path | Keep `/whole-book/prepare` + `/free/prepare` | PRESERVE |

**PRODUCT RESULT API：** UNRESOLVED（must freeze unique path in Pre-Implementation Freeze）  
**PAGINATION REQUIRED：** UNRESOLVED（lean YES for long books）

## Contract

**CANONICAL CONTRACT：** Lab `ChapterFunctionsResultDto` exists；**product SoT unresolved** — likely need **ChapterFunctionsResultV2** aligned with structure V2 evidence model, or explicitly adopt adapted V1. Freeze must choose.
