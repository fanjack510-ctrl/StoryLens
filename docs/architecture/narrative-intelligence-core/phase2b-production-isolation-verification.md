# Phase 2B Production Isolation Verification

**Change:** CHG-20260723-040
**Tests:** `test_scenario_production_isolation`, `test_version_and_gates_locked`, `test_runtime_composition_aliases_and_schema` in `test_narrative_phase2b_integration.py`

## Gates still closed (evidence)

| Gate | Expected | Verified by |
|------|----------|-------------|
| `PRO_CAPABILITIES_SHIPPED` | `false` | unchanged from Phase 1C/2A |
| `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED` | `true` | contract constant + integration assert |
| `PRODUCTION_DEFAULT_ENGINE_ID` | `None` | registry constant + integration assert |
| `WHOLE_BOOK_MOCK_LAB_ENABLED` | default `false` | contract constant + integration assert |
| Fake runtime in production | forbidden | `create_private_whole_book_analysis_runtime(production=True)` raises |
| Fake engine in production loader | refused | `assert_production_isolation` loads fake id with `production=True` |
| Fake prompt pack in production | rejected | `reject_fake_prompt_pack_in_production` |
| Formal Run create | disabled | no new whole-book run endpoint in Integration |
| Pattern tables | none | `narrative_pattern` absent after E2E |
| VERSION | `1.0.5` | `test_version_and_gates_locked` |
| Migrations | none added | Integration composition + tests only |

## `assert_production_isolation()` checks

When `package_root` prepared:

1. Production engine loader must not load `fake.signed.private_engine`
2. Fake prompt pack rejected under `production=True`
3. Factory with `production=True` raises
4. Gate constants match closed values

Returns `{ ok, errors, production_default_engine_id, ... }`.

## What Integration added without opening production

- Injectable Fake composition root for tests/dev
- Fake Provider E2E across Context → Evidence → Module → Candidate
- Signed Fake engine/prompt pack write path (test package root only)
- Integration documentation (CHG-040)

## What Integration did not do

- Enable formal whole-book Run create
- Register real Engine or model Provider for production
- Ship Pro capabilities
- Add migrations or Pattern schema
- Bump VERSION / build / publish / push

See [phase2a-production-isolation-verification.md](./phase2a-production-isolation-verification.md) and [phase1c-mock-production-isolation.md](./phase1c-mock-production-isolation.md) for prior baselines; Phase 2B Private Engine path inherits closed gates.
