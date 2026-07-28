# CHG-041 Manual Gate Environment Repair Round 4

## Change

- Primary: CHG-20260728-041
- Related: CHG-20260728-042

## Public baseline

- Expected Production HEAD at Round 4 start: `d31258df32aa00acf65f77e75056f59026d33ecd`
- Investigation evidence tip present on branch: `690506d`
- Round 4 Start HEAD (actual): `690506d4a79244199175014337999c2057118a38`

## What was repaired

1. Smoke Fake Journey success fixture
   - Per-scene evidence uses that scene’s first in-range paragraph_id
   - Default mode `STORYLENS_JOURNEY_FAKE_MODE=success`
   - `repair_failure` separated for CHG-042 local repro only
2. Structural Repair Fake returns all `expected_scene_ids` (no fixed `[1]`)
3. `validate_manual_gate_journey_fixture_v1()` preflight
4. Unified UI mapping `mapReaderJourneyStatusToUi`
   - `failed` → 阅读旅程生成失败 (never 分析已暂停)
5. UTC serialization (`ensure_utc_aware`) + frontend `parseBackendUtcTimestamp`
6. Elapsed uses selected Journey Run timestamps (naive legacy treated as UTC)

## CHG-042 boundary

- LOCAL REPRO ROOT CAUSE: confirmed (`FAKE_FIXTURE_INVALID`)
- PRODUCTION INCIDENT ROOT CAUSE: unconfirmed
- CHG-042 STATUS: investigated
- READY FOR PRODUCTION CORE FIX: NO

## Manual Gate R4 environment

- Root: `%TEMP%\storylens-mg-chg041-r4-final\`
- DB: `%TEMP%\storylens-mg-chg041-r4-final\database\storylens-mg-chg041-r4-final.db`
- API: `http://127.0.0.1:18041`
- Frontend: `http://127.0.0.1:1421`
- Scene review:
  `http://127.0.0.1:1421/books/1?view=scene-boundary-review&chapter=1&analysisRun=1`
- Post Confirm+Start (HTTP E2E):
  `http://127.0.0.1:1421/books/1?view=result&tab=reader-journey&chapter=1&analysisRun=1&journeyRun=1`

## HTTP E2E (agent)

- Confirm+Start → `journey_run_id=1` → Fake Journey **succeeded** (4/4 profiles)
- Evidence in-scene: P0001 / P0006 / P0011 / P0016
- API timestamps end with `Z`
- Elapsed ≈ 0.4s
- See `HTTP_E2E_R4.json`

## Constraints honored

- REAL PROVIDER CALLS: 0
- FORMAL DATABASE WRITES: 0
- BUILD / PUSH / MERGE / VERSION: NO
- CHG-041 not marked verified
- CHG-042 not marked resolved
