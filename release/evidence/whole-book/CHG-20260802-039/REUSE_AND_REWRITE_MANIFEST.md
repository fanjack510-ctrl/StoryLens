# REUSE AND REWRITE MANIFEST — WB-2.2

**Rule:** No whole-branch merge of Lab/Pro. No novel-specific ports. Classify before coding.

## Public

| Artifact | Class | Impl note |
|---|---|---|
| `AssetType.chapter_function` | REUSE | Persist Free V2 via existing asset type |
| Free Run/Stage/Provider Unit machinery | REUSE | Add stage + unit codes only |
| Evidence Deep Link APIs | REUSE | Exact citations |
| `CHAPTER_FUNCTIONS_SPEC` | REUSE + amend | Point product path at V2；Lab may keep V1 schema ref |
| `ChapterFunctionsResultDto` | LAB_ONLY | Keep；adapter from V2；not Free SoT |
| Free product API / capability available | MISSING → NEW | Agent1 |
| `ChapterFunctionsResultV2` | MISSING → NEW | Agent1 |
| Stage `synthesize_chapter_functions` | MISSING → NEW | Public + Private constants |
| WB-2.1 FakeHttp / empty-policy pattern | REUSE pattern | Port pattern, not structure files |
| PlannedModulePanel shell | REUSE shell | Agent2 replaces with real panel |
| Pro Insights ChapterFunctionsResultV1 | PRO_DIFFERENT | DO_NOT_PORT as Free |

## Private

| Artifact | Class | Impl note |
|---|---|---|
| `ChapterFunctionsRunner` | REWRITE | Emit V2 shape；drop meta-labels primary/secondary from enum |
| `GENERAL_LABELS` | REUSE base | Remove primary/secondary；match freeze |
| `normalize_function_labels` | MISSING → NEW | Implement repair rule |
| prompt pack | REWRITE | Align V2 + controlled labels；no novel hooks |
| `max_chapters_per_batch=8` | REUSE | Keep |
| Pro insights contracts | DO_NOT_PORT | — |

## Counts

| Class | Count |
|---|---|
| REUSE | 8+ patterns/assets |
| REWRITE | 3（runner, prompts, validators） |
| MISSING→NEW | 5（V2, Free API, stage, normalize, fixtures） |
| LAB_ONLY | 1 DTO lineage |
| PRO_DIFFERENT | 1 |
| DO_NOT_PORT | Pro Insights as Free SoT |

## Port review gate

Reject any hunk with book titles, sample chapter counts as hard gates, or keyword detectors for specific novels → **DO_NOT_PORT**.
