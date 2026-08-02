# DATABASE DECISION — WB-2.2 FREEZE

## Verdict

```
DATABASE CHANGE：NOT REQUIRED
MIGRATION REQUIRED：NO
```

## Evidence

| Item | Finding |
|---|---|
| Asset type | `AssetType.CHAPTER_FUNCTION` already exists（`enums.py`） |
| Persistence | Reuse Narrative Asset + Version + Evidence（WB-1.x / WB-2.1 pattern） |
| Stage codes | Free string column — `synthesize_chapter_functions` needs **no** DDL |
| Provider units | Runtime rows — no schema migration |
| Pagination | API cursor/offset over assets — **no** new tables |
| Confirmed / conflict | Reuse WB-1.10 path |
| Old DB | Remains openable（additive runtime data only） |

## Explicit non-goals

- New `chapter_functions` SQL table  
- Graph DB  
- Per-novel schema forks  

If implementation discovers a hard schema gap, stop and open a new Change — do not silently migrate.
