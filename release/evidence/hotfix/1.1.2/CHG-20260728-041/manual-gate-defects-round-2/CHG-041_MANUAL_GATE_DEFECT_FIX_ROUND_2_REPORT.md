# CHG-041 MANUAL GATE DEFECT FIX ROUND 2 REPORT

**Status:** Round 2 automatic verification COMPLETE (not formally marking CHG-041 verified)  
**Public HEAD (committed):** `8d410c5f1d9a2557f3246cd07d83f402bb4936c5`  
**Working tree:** additional Round 2 hardening uncommitted on `fix/1.1.2-manual-scene-boundary-review`  
**Mode:** Fake only (`STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1`), no real Provider  
**Isolated DB:** `%TEMP%\storylens-mg-chg041\database\storylens-mg-chg041.db` (fresh reseed)

---

## Verdict

Round 2 defect loop is closed in automatic verification:

| # | Requirement | Result |
|---|-------------|--------|
| 1 | Old succeeded Journey not reused across / beside revision-scoped Confirm+Start | PASS — new `auto-…:rev:{id}`; old fixture `result_status=superseded` |
| 2 | After confirm `awaiting_confirmation=false` | PASS |
| 3 | Journey `scene_revision_id` / `boundary_hash` / `chapter_text_hash` match confirmed revision | PASS |
| 4 | Confirm+Start returns new `journey_run_id` + frontend can auto-route | PASS — `journey_started=true`, status `queued`, route includes `journeyRun=` |
| 5 | Same draft reconfirm does not add Revision | PASS — no-change collapses; confirmed rows = 1 |
| 6 | Same Confirm+Start retry does not add Journey Task | PASS — same `journey_run_id`; auto rows = 1 |
| 7 | Auto tests + baseline contrast | PASS (CHG-041 + subset); collect errors PRE_EXISTING |
| 8 | Fresh isolated DB + fixture | PASS |
| 9 | This report | PASS |
| 10 | New API / FE URL + PID | See runtime below |

---

## Root causes fixed in Round 2

1. **Succeeded Journey reuse**  
   Explicit revision bind (`scene_revision_id` set) no longer steals an unrelated succeeded row (including same-revision fixture with different `client_request_id`). Only `auto-{run}:rev:{revision_id}` is reused.

2. **`awaiting_confirmation` stuck true**  
   Overview treats model+hold correctly; confirm clears hold via `mark_scenes_complete_awaiting_journey`.

3. **No-change reconfirm creating new Revision**  
   Draft with identical hashes collapses onto existing confirmed revision (`already_confirmed=true`).

4. **Confirm+Start blocked / not routable**  
   Confirm+Start queues the journey and schedules `execute_reader_journey` in `BackgroundTasks` (same pattern as create), so the HTTP response returns `journey_started=true` with a new `journey_run_id` for frontend routing.

5. **Idempotent bind wiping progress**  
   `bind_journey_to_revision` no longer resets counters when already bound to the same revision hashes.

6. **Fake MG provider eligibility**  
   Smoke Fake readiness override applied in `ProviderRuntimeService.resolve_for_run`; fixture seeds `cloud_enabled` + `ProviderConfiguration(aliyun_qwen_plus)`.

---

## Automatic verification

### Unit / UI

- `pytest tests/test_chg041_scene_boundary_manual_review.py` → **16 passed**
- Vitest (resolveSceneJourneyGate + SceneBoundary* chg041) → **26 passed**
- `tsc --noEmit` → **passed**
- `scripts/check_project.py` → **FAILED** (hotfix registry drift / VERSION mismatch — **PRE_EXISTING**, not introduced by Round 2 logic)

### Baseline collect contrast

Issue branch and `hotfix/1.1.2` integration both: **9 collect errors**, identical set (canary fixtures / phase2br1 / native-overview plugin). Classification: **PRE_EXISTING**. Evidence: `BASELINE_CONTRAST.json`.

### HTTP E2E (fresh DB)

Evidence: `E2E_CONFIRM_START_VERIFY.json`

- Confirm+Start → `journey_run_id=2`, `journey_started=true`, `journey_status=queued`
- Overview → `awaiting_confirmation=false`
- Journey bound to confirmed revision #2 hashes
- Retry Confirm+Start → same `journey_run_id=2`
- No-change draft confirm → same revision id, confirmed count remains 1
- Old fixture journey #1 → `superseded`

---

## Runtime (current)

| Item | Value |
|------|-------|
| API | http://127.0.0.1:18041 |
| Frontend | http://127.0.0.1:1421 |
| API PID | 32804 |
| Frontend PID | 33060 |
| Deep link | http://127.0.0.1:1421/books/1 |
| Scene review | http://127.0.0.1:1421/books/1?view=scene-boundary-review&chapter=1&analysisRun=1 |
| Post Confirm+Start route hint | http://127.0.0.1:1421/books/1?view=result&tab=reader-journey&chapter=1&analysisRun=1&journeyRun=2 |
| Database | `C:\Users\msi\AppData\Local\Temp\storylens-mg-chg041\database\storylens-mg-chg041.db` |
| Fake | true |
| Real Provider | false |
| Formal AppData DB | not touched |

Start/stop: `%TEMP%\storylens-mg-chg041\start_chg041_full_local.ps1` / `stop_chg041_full_local.ps1`

---

## Uncommitted hardening (on top of `8d410c5`)

- `chapter_analysis_completion.py` — revision-scoped ensure never steals foreign succeeded rows; supersedes other current journeys
- `scene_boundary_manual_review.py` — idempotent bind; failed-status error propagation after sync execute
- `scene_boundaries.py` — Confirm+Start queues + background execute
- `provider_runtime_service.py` — Smoke Fake eligibility override for journey path
- `chapter_analysis_smoke_fake_transport.py` — stronger numeric `scene_id` pairing for journey profiles
- `test_chg041_scene_boundary_manual_review.py` — awaiting / reuse / retry coverage
- MG seed script (temp) — `aliyun_qwen_plus` + cloud/provider fixture rows

---

## Boundaries (unchanged)

- No VERSION bump / Build / Push / Merge / Forward Port
- CHG-041 not marked verified
- No real Provider calls
- No formal AppData database use
