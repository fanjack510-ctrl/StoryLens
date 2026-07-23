# Phase 1C Mock / Production Isolation

## Mock markers

- Engine id: `mock_whole_book_v0`
- Outputs: `mock=true`, `synthetic=true`, `non_production=true`
- Artifact envelope carries the same flags
- Candidates never canonical / never locked

## Production refusal

- `PRODUCTION_DEFAULT_ENGINE_ID = None`
- `DefaultWholeBookEngineFactory(production_mode=True)` refuses Mock
- Production registry does not register Mock by default
- Preflight never reports Mock as production-ready
- Run creation remains disabled (`WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`)
- `shipped=false` for whole_book_analysis
- Mock results must not feed formal user analysis pages

## Stage Artifact Contract

- `artifact_type`: `whole_book_stage_result`
- Schema: `whole_book_stage_artifact` / version `1`
- Refs + structured summary only (no novel body / full evidence text)
- Reuses `analysis_artifacts` — no new table / migration
- Does not become a Narrative Asset
