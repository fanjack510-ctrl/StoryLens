# WB-2.2 DATABASE DECISION（planning）

## Audit

| Question | Finding |
|---|---|
| Reuse Narrative Asset? | **YES intent** — `AssetType.CHAPTER_FUNCTION = "chapter_function"` already in `enums.py` |
| Existing chapter_function assets in Free pipeline? | Lab/Fake only；Free product pipeline **not wired** |
| New Asset Type needed? | Likely **NO** if reuse `chapter_function` |
| Migration required? | **UNRESOLVED** — stage_code strings are free; may need no schema migration if asset JSON versioned in payload |
| Per-chapter index / pagination tables? | **UNRESOLVED** — may be API-only pagination over assets |
| Old DB openable? | Target YES if additive |
| Run / Stage / Provider Unit impact? | Will need new stage code + provider units（runtime rows, not necessarily DDL） |
| Evidence tables? | Reuse existing Evidence |
| Conflict / confirmed no-overwrite? | **REQUIRED** reuse WB-1.10 path |

## Verdict

**DATABASE CHANGE：UNRESOLVED**  
**MIGRATION REQUIRED：UNRESOLVED**

Freeze must decide NOT REQUIRED vs REQUIRED before coding. Prefer NOT REQUIRED (asset reuse) unless pagination forces tables.
