# FAILURE ROOT CAUSE — CHG-042 / Journey Run 2

## Verdict

Journey Run 2 fails on the **structural repair validation** path after an initial
batch is rejected for **out-of-scene evidence**. Final code:

`JOURNEY_REPAIR_VALIDATION_FAILED`

Primary root-cause category: **H. FAKE_FIXTURE_INVALID** (Smoke Fake success fixture
is misconfigured for multi-scene batches).

Confidence: **CONFIRMED**

## Causal chain (Run 2)

1. Confirm+Start creates Journey Run 2 bound to revision 1 scenes `[1,2,3,4]`.
2. First batch requests profiles for scenes `[1,2]`.
3. Smoke Fake returns **correct scene_ids** `[1,2]` but attaches the **same**
   evidence paragraph chunk (`P0001`/`P0002`) to every profile.
4. Validator raises `JOURNEY_EVIDENCE_OUT_OF_SCENE`
   (`scene 2 evidence B0001-C0001-P0001 not in scene paragraphs`).
5. Structural repair is requested for expected scenes `[1,2]`.
6. Repair Fake/parsed output yields scene_ids `[1]` only.
7. Validator raises `JOURNEY_SCENE_ID_MISMATCH` (`expected [1, 2], got [1]`).
8. `generate_validated` wraps this as `JOURNEY_REPAIR_VALIDATION_FAILED`.

## Answers (section 五)

| # | Answer |
|---|--------|
| 1 Input scene IDs | `[1,2,3,4]` (Run 2 / rev 1). Confirmed rev 2 scenes are `[5,6,7,8]` (Run 3). |
| 2 Scene results exist? | No journey profiles persisted (`profile_count=0`). |
| 3 First failing batch | Scenes `[1,2]` (invocation 1). |
| 4 First Fake output IDs | Parsed `[1,2]` (IDs OK). |
| 5 First parsed IDs | `[1,2]` |
| 6 First missing IDs | Not ID-missing; evidence invalid for scene 2. |
| 7 Repair trigger | `JOURNEY_EVIDENCE_OUT_OF_SCENE` |
| 8 Repair required | `[1,2]` |
| 9 Repair raw empty? | Parsed payload non-empty (`parsed_len≈3369`), but incomplete IDs. |
| 10 Repair parsed IDs | `[1]` |
| 11 Repair merged IDs | Effectively `[1]` (mismatch fail before persist). |
| 12 Why final code | Repair still violates contract after OUT_OF_SCENE → wrap to `JOURNEY_REPAIR_VALIDATION_FAILED`. |
| 13 Same as INC-20260728-003? | **YES** same code path (`JOURNEY_SCENE_ID_MISMATCH` / expected…got… → repair validation failed). Exact INC file not in tree; message pattern matches. |
| 14 Deterministic? | **YES** (pipeline re-exec on disposable copy). |
| 15 Fake incomplete on purpose? | No fail-inject flag; intended success Fake. |
| 16 Who drops? | Fake evidence wiring + repair ID extraction; not real Provider. |

## Note on URL `journeyRun=2`

Frozen DB also has **Journey Run 3** (`result_status=current`, rev 2, scenes `[5,6,7,8]`)
with the **same failure class** (`expected [5,6], got [1]`). Run 2 is superseded.
UI deep-link to Run 2 still shows the same product defect class.
