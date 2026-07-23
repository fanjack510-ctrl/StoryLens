# Phase 1D Known Limitations

1. **Real whole-book Run create** remains disabled (`WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`).  
2. **No production Engine** (`PRODUCTION_DEFAULT_ENGINE_ID=None`); Mock ≠ production.  
3. **Review write HTTP** (`POST /api/v1/narrative-review-actions`) not registered — Phase 2E.  
4. **No formal whole-book result page / product navigation** — lab/isolation only.  
5. **Module Envelope payloads** are projection stubs; not real literary analysis.  
6. **Structure Map** is a projection prototype; no graph DB / FTS5 / vector store.  
7. **Pro capabilities** not shipped (`PRO_CAPABILITIES_SHIPPED=false`).  
8. **Pattern tables** not created; dual FE dirs `narrativePattern` + `structureMap` during transition.  
9. **No migrations** in Phase 1D Integration.  
10. Phase 2 inputs: open Review write carefully, deepen module projections, formal result IA, optional Engine registration behind capability gates.
