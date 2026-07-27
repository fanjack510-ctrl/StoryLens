# Phase 2B-R1 Private Lab Runtime Limitations (Agent V / CHG-047)

## Deferred to Integration (CHG-048)

1. Shared `apps/api/app/main.py` composition of Lab router + Settings.
2. Wire Fake Ports → Agent U Preflight / Estimate / Consent / Bailian live payload.
3. Live Smoke harness (real credential, real estimate, four-module live).
4. Optional deepen of `PrivateWholeBookAnalysisRuntime` composition root (I-owned).

## Deferred / Schema notes

1. Evidence tables still lack `run_id` column — provenance via parent Version /
   `attributes_json` / artifact payload (documented; no Migration in R1).
2. Agent U estimate/consent services are not imported (parallel branch); V uses
   Ports + Fakes until Integration merges.
3. Executor default path uses Fake Provider Port; full Phase1B ORM persist during
   Lab HTTP auto-start is optional via `runtime_factory` injection.
4. Resume fingerprint mismatch requires re-confirm — silent Prompt/Model swap
   forbidden; UI re-confirm flow is Integration/product.

## Explicit non-goals (unchanged)

- No production default Lab enablement
- No formal `POST /api/v1/books/{book_id}/whole-book-runs`
- No `PRO_CAPABILITIES_SHIPPED` / `PRODUCTION_DEFAULT_ENGINE_ID` flips
- No auto canonical / confirm / lock
- No VERSION / tag / build / publish / push
