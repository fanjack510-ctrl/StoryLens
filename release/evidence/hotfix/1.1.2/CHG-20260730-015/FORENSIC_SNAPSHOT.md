# FORENSIC SNAPSHOT — INC-20260730-007

## Identity

| Field | Value |
|---|---|
| Incident | INC-20260730-007 |
| Change | CHG-20260730-015 |
| RC | 1.1.2-rc.4 |
| Captured at (UTC) | 2026-07-30T04:57:22Z |
| Public base HEAD | `678e0b1aff1ca827a48520474d2f8a3fc660dacc` |
| Formal DB path | `C:\Users\msi\AppData\Local\StoryLens\database\storylens.db` |
| Formal install | `C:\Users\msi\AppData\Local\StoryLens\` |
| Sidecar listen | `127.0.0.1:59281` |
| Desktop PID | 29132 |
| Formal API PIDs | 24984, 8128 |

## Binary hashes (formal install)

| File | Size | SHA-256 |
|---|---:|---|
| storylens-api.exe | 39691772 | `AF51B8FBD386BB967E79DBEE76BCB77E2AE934EBA956F2F2DFCCE6E46CD474F4` |
| storylens-desktop.exe | 13107200 | `46260FB461F7A63E9EE1D2B212932CFF2A8904F63CAFC204…` (see hashes/formal_binaries.json) |

Sidecar SHA matches RC.4 build sidecar. RC.4 installer archive **not** modified this round.

## Database copy

| Item | Value |
|---|---|
| Consistent backup | `database/storylens.db` |
| Backup SHA-256 | `7B016F389BE641C5EA9281383188E39059A7A7CB9A1A52C10BBF3E20D5B91865` |
| Raw wal/shm | `database/raw/` |
| Formal DB writes this round | **0** |

## Failed task identifiers

| Field | Value |
|---|---|
| book_id | 2 |
| chapter_id | **1304** |
| analysis_run_id | **7** |
| journey_run_id | **5** |
| confirmed_revision_id | **13** |
| scene_revision_no | 3 |
| client_request_id | `auto-chapter-journey:7:rev:13` |
| confirmed scenes | **68, 69, 70** (ordinals 1–3) |
| journey status | `failed` |
| journey current_stage | `reader_journey_scene_profiles` |
| completed_scene_count | **0 / 3** |
| root_error_code | `PIPELINE_UNEXPECTED_ERROR` |
| root_error_message | `SCENE_ANALYSIS_INCOMPLETE` |
| failed_stage | `pipeline` |
| retryable | 1 |
| startup claimed_at | `2026-07-30T04:52:38.935022+00:00` |
| journey failed_at | `2026-07-30 04:52:38.959051` |

## Provider invocations (analysis_run 7)

Boundary + scene_analysis only. **No** `reader_journey_scene` / synthesis invocations for journey 5.

| id | task_type | status | created_at (UTC) | tokens in/out | finish_reason |
|---:|---|---|---|---|---|
| 187 | scene_boundary | succeeded | 04:50:31 | 1373/688 | stop |
| 188 | scene_boundary | succeeded | 04:50:37 | 1033/228 | stop |
| 189 | scene_boundary_adjudication | succeeded | 04:50:40 | 1300/58 | stop |
| 190 | scene_analysis | succeeded | 04:52:00 | 987/442 | stop | → artifact scene **66** |
| 191 | scene_analysis | succeeded | 04:52:09 | 1038/469 | stop | → artifact scene **67** |
| 192 | scene_analysis | succeeded | 04:53:04 | 898/571 | stop | → artifact scene **68** |
| 193 | scene_analysis | succeeded | 04:53:14 | 942/444 | stop | → artifact scene **69** |
| 194 | scene_analysis | succeeded | 04:53:23 | 953/430 | stop | → artifact scene **70** |

Actual Provider HTTP calls for this chapter run: **8** (all HTTP 200 / status succeeded).  
Journey-stage Provider calls: **0**.

## Scene rematerialize vs journey fail

| Scene id | created_at (UTC) | artifact at |
|---:|---|---|
| 66 | 04:51:50 | 04:52:00 |
| 67 | 04:51:50 | 04:52:09 |
| **68** | **04:52:38.899** | **04:53:04** |
| **69** | **04:52:38.902** | **04:53:14** |
| **70** | **04:52:38.903** | **04:53:23** |

Journey 5 failed at **04:52:38.959** — **before** artifacts for 68/69/70 existed.

## Logs

- Copied: `logs/sidecar.log`, `logs/sidecar-stderr.log`
- Key line: `2026-07-30 12:52:38,961 ERROR ... reader_journey_v2_failed journey_run_id=5` + `ValueError: SCENE_ANALYSIS_INCOMPLETE`
- Same pattern historically on journey_run_id=3 and =4 (later recovered).

## Safety

- No formal DB mutation
- No formal retry / continue
- No API keys in this document
- REAL PROVIDER CALLS THIS ROUND: **0** (forensics only)
