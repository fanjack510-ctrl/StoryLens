# WB-0.2 Test Results

**STEP:** WB-0.2-DATA-CONTRACTS  
**CHANGE:** CHG-20260728-003  
**Date:** 2026-07-28

## Public (`apps/api/tests/test_whole_book_contract_v1.py`)

```
31 passed
```

Coverage includes: extra-field forbid, SHA/UTC/confidence validation, native/enhanced input_usage, snapshot/run/stage/window/coverage rules, evidence locator valid/stale/unresolved, candidate cross-refs, confirmed-asset protection, overview claim evidence rules, fixture origin, schema determinism, persistence mapping presence, no DB writes in validators.

## Private (`tests/test_whole_book_contract_v1.py`)

```
10 passed
```

Coverage includes: Public/Private schema hash identity, window/synthesis round-trips, response cross-refs, legacy adapter degrade, no available without evidence, fixture≠formal, provider_calls=0, db_writes=0.

## Schema export identity

```
PUBLIC_SCHEMA_SHA=515f08a06e1ce7a02e526b46d3a96fda4ef78c3cc82d5703fa1bbaf50c8766d1
PRIVATE_SCHEMA_SHA=515f08a06e1ce7a02e526b46d3a96fda4ef78c3cc82d5703fa1bbaf50c8766d1
IDENTITY=PASS
```

## v1.1.1 regression smoke

```
tests/test_narrative_phase1c_capability_backend.py
tests/test_reader_journey_v2_local.py
→ 53 passed, 1 skipped
```

## Side effects

| Check | Result |
|---|---|
| Real Provider calls | 0 |
| Formal DB writes | 0 |
| Migrations | 0 |
| Whole-book product entry enabled | NO |
| Existing API response changes | NO (contract package additive only) |
