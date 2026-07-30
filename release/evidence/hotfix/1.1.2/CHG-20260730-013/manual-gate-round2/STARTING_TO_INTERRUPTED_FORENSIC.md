# STARTING_TO_INTERRUPTED_FORENSIC — Manual Gate Round 2

- Change: CHG-20260730-013
- Incident: INC-20260730-006
- Public HEAD: `1f00c4ab6477863fd5c1a29c5ef6755e20fc548b`
- Captured: 2026-07-30 (local)
- Live DB (frozen copy): `release/evidence/hotfix/1.1.2/CHG-20260730-013/manual-gate-round2/database/storylens-mg-chg013.db`
- Failure URL: `http://127.0.0.1:1427/books/1?chapter=1&analysisRun=1&view=scene-boundary-review` → after confirm `journeyRun=3`
- Formal DB writes during forensics: **0**
- Real Provider calls: **0**

## Verdict (classification)

**A. FAKE_WORKER_NOT_RUNNING** (environment) — more precisely:

> Worker **did** run after the intentional 4s delay, but the MG gateway has **no provider named `fake`**.  
> Execution fails with `ProviderNotFoundError: fake` → persisted `status=failed` / `root_error_code=PIPELINE_UNEXPECTED_ERROR`.  
> UI maps that failed retryable journey to「阅读旅程已中断 / 阅读旅程生成失败」.

**Not** product bug `I. RECOVERY_JOB_MARKED_STARTING_AS_INTERRUPTED` for this failure.

- Unclaimed `starting` was **not** force-interrupted by recovery in this trace.
- Journey 3 shows durable `worker_claim` + `startup_intent.claimed=true` before failure.
- 4s ≈ MG launcher `STORYLENS_MG_WORKER_CLAIM_DELAY_SECONDS=4`, **not** `JOURNEY_STALE_THRESHOLD` (120s).

## Timeline (Journey Run 3 / Analysis Run 1)

Times from DB + `logs/api.out.log` (UTC-naive DB stamps = local wall clock used by process).

| # | Event | Evidence |
|---|---|---|
| 1 | User confirm click | `POST .../draft/2/confirm` → 200 (`api.out.log`) |
| 2 | Revision confirmed | `boundary_revisions` id=2 bound as `scene_revision_id=2` on journey 3; client_request_id `auto-chapter-journey:1:rev:2` |
| 3 | Startup intent | `failure_details.startup_intent.at = 2026-07-30T03:42:43.247605+00:00` |
| 4 | Analysis Run | Reused `analysis_runs.id=1` (created at seed `03:31:17`); not recreated |
| 5 | Journey Run created | `reader_journey_runs.id=3` `created_at=2026-07-30 03:42:43.244606` |
| 6 | Task / BackgroundTask | Confirm handler `background.add_task(execute_reader_journey, ...)` |
| 7 | workflow starting | Confirm response path sets `workflow_state=starting`; intent written at create |
| 8 | API response | Immediate 200 on confirm (before delayed worker finishes) |
| 9 | Frontend first poll | `GET /reader-journeys/3` + `/reader-journey-runs/3/progress` right after confirm |
| 10–11 | Worker scan / claim | After ~4s delay wrapper; claim metadata present (`claimed_at` on resume path `03:43:27.689792`; first fail logged shortly after confirm+delay) |
| 12–13 | lease / heartbeat | Claim encoded in `failure_details.worker_claim` (no separate lease table) |
| 14 | Failed persisted | `status=failed`, `root_error_code=PIPELINE_UNEXPECTED_ERROR`, `completed_at=2026-07-30 03:43:27.692798` (includes later recover retry) |
| 15 | interruption_reason | **Not** `JOURNEY_INTERRUPTED`. Log: `ProviderNotFoundError: fake` |
| 16 | Code path | `execute_reader_journey` → claim → `execute_reader_journey_v2` → `ProviderRuntimeService.resolve_for_run` → `gateway.get(run.provider)` with `provider=fake` |
| 17 | status_version | Analysis run `status_version=0` (unchanged); journey status transitions starting/queued → claimed → failed |
| 18 | UI state source | Progress/result poll of **journey 3** failed payload; presentation shows interrupt/fail copy for retryable pipeline failure |

## Required answers

| Question | Answer |
|---|---|
| Worker claim Journey 3? | **Yes** (`startup_intent.claimed` / `worker_claim.claimed_at`) |
| If unclaimed, why? | N/A — claimed |
| If claimed, why interrupted UI? | Claim succeeded then **provider resolve failed**; UI treats failed retryable journey as 中断/失败 — **not** unclaimed-starting interrupt |
| 4s == stale/lease threshold? | **No**. Equals MG delay env `STORYLENS_MG_WORKER_CLAIM_DELAY_SECONDS=4`. Stale threshold remains 120s |
| Interrupted backend or FE infer? | **Backend persisted `failed`**; FE displays failure/interrupt presentation from that status |
| Journey 3 bound correct revision? | **Yes** `scene_revision_id=2` / `auto-chapter-journey:1:rev:2` |
| Old failed run selected? | **No** — new journey id=3 for analysis_run=1 |
| Multiple recoverers? | Recover POST later re-entered same journey 3; still failed on same missing `fake` provider. Startup recovery did not mark unclaimed starting as interrupted here |

## Log excerpt (smoking gun)

```text
POST /api/v1/chapters/1/scene-boundaries/draft/2/confirm HTTP/1.1" 200
...
reader_journey_v2_failed journey_run_id=3
KeyError: 'fake'
ProviderNotFoundError: fake
```

## Environment root cause

1. Seed sets `analysis_runs.provider = "fake"` / journey `provider_name = "fake"`.
2. MG API launcher enabled `STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1` but did **not** register `tests.fakes.FakeProvider` into `ModelGateway`.
3. Smoke Fake only intercepts OpenAI-compatible HTTP; it does not invent a gateway entry named `fake`.
4. After the intentional 4s delay, worker claims → resolve_for_run(`fake`) → boom → failed UI.

## Corrective action (this round)

Environment-only (TEMP scripts under `%TEMP%\storylens-mg-chg013-confirm-start\scripts\`):

1. Register runnable Fake path via **Smoke Fake** + `analysis_runs.provider=aliyun_qwen_plus` (gateway entry exists).
2. Enable `STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1`, `STORYLENS_JOURNEY_FAKE_MODE=success`, `STORYLENS_APP_ENV=development`.
3. Keep intentional worker claim delay = 4s via launcher monkeypatch.
4. Seed paragraph IDs must match Smoke Fake regex `B\d+-C\d+-P\d+` (use `B0001` / `B0002` / `B0003`, not `B00A1`).

Post-fix Fixture C auto-precheck: confirm → `starting` during delay → **`succeeded` 3/3** after worker (no ProviderNotFound / no false JOURNEY_INTERRUPTED).

- Do **not** change product interrupt rules for this defect class.
- Do not mark verified / build RC.4 / push.
