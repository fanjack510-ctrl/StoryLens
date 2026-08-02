# WB-2.2 TEST MATRIX（planning）

## Backend

- Normal per-chapter functions  
- Multi-function chapter  
- Non-fixed taxonomy（no forced novel-specific labels）  
- No reliable primary function  
- Missing evidence  
- Truncation + repair  
- Repair failure  
- Short book / very long book  
- Non-contiguous chapter numbers  
- Empty chapter / duplicate chapter  
- Pause / Resume / Cancel  
- Duplicate Resume（no extra provider calls）  
- Confirmed no-overwrite  
- Conflict creation  
- Native Input Audit（chapter_analysis=0, journey=0, aggregate=0）

## UI

- available / multi-function / insufficient / failed / canceled / conflict / loading / absent  
- Evidence deep link（exact；return stays on chapter-functions）  
- Filter by function  
- Pagination or virtual list  
- Refresh / reentry  
- 1366 / 1920；no horizontal scroll  
- Structure regression；no purchase UI  

## Regression

- v1.1.2 Scene / Journey  
- Wave D overview + characters/events + prepare dual path + cost consent  
- WB-2.1 structure stages  
- CHG-031 layout  

## Commands（post-implementation）

```text
pytest apps/api/tests/test_whole_book_wb22_* -q
private: pytest tests/test_chapter_functions_* -q
cd apps/desktop && npm run typecheck && npm run test -- --run
npm run test:e2e  # wb22 config TBD
```
