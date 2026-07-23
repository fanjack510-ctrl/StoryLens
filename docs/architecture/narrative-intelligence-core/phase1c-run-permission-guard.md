# Phase 1C Run Permission Guard

## Entry

`require_whole_book_run_permission(...)` in  
`apps/api/app/narrative_core/services/run_permission_guard.py`

`preflight_whole_book_run(...)` returns `WholeBookPreflightDTO` with  
`notes.run_creation_enabled=false` (internal only; HTTP not wired).

## Production default

`WHOLE_BOOK_RUNS_ENDPOINT_DISABLED = True`  
→ Guard denies with `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED`.

Formal `POST` whole-book-runs remains unregistered.

## Test override (explicit only)

- Context: `allow_endpoint_for_test=True`
- Or env: `STORYLENS_ALLOW_WHOLE_BOOK_RUNS_FOR_TEST=1|true|yes`

Even with override, unshipped capability still denies. Override never enables live Engine/model.

## Check order

1. Endpoint disabled (unless override)
2. Capability (shipped → license → …)
3. Mode vs metadata `supported_modes`
4. Quota
5. Snapshot status == `completed` (when provided)
6. Optional cloud budget checker (combinable; separate subsystem)

## Side-effect rules

On Guard failure:

- Do **not** create AnalysisRun
- Do **not** create Snapshot
- Do **not** call Engine
- Do **not** reserve cloud budget

`run_factory` / `snapshot_factory` / `engine_invoker` parameters are accepted only so tests can assert they are never invoked; production callers must not pass creators into a deny path expecting execution.

## Phase 1C result

`run_creation_enabled` stays `false` even when all checks would pass under a test override. Integration owns live route enablement later.
