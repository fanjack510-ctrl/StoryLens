# MEDIUM_RUN — CHG-20260807-055

DATE：2026-08-07

## Environment

| Item | Value |
|---|---|
| DATABASE | `C:\Users\msi\AppData\Local\Temp\storylens-v120-l3-medium\storylens_l3_medium.db` |
| Provider | aliyun_qwen_plus |
| Model | qwen3.7-plus |
| Fixture / Fake | **NO** |
| Formal user DB writes | **0** |

## Identifiers

| Field | Value |
|---|---|
| MEDIUM RUN ID | 1 |
| SNAPSHOT ID | 1 |
| REVISION | `c047c09ac3abd08231dca4a3000f11893e0875deea846963866e3bf926497fb3` |
| ESTIMATE ID | 2 |
| CONSENT ID | 1 |
| result_origin | formal |
| run_status | completed |
| elapsed_sec | 262.13 |

## Consent binding

Consent bound to book_id + estimate_id + snapshot/revision path via formal create.
No Fixture create; no Fake Provider; Cost Estimate not bypassed.

## Module results

| Module | Result |
|---|---|
| overview | PASS |
| characters_events | PASS |
| structure | PASS |
| chapter_functions | PASS |
| project_result | PASS |

## Notes

- Actual window count at runtime：**9**（estimate listed 8）.
- Actual provider units/calls：**17**（below estimate 22；repair reserve unused）.
- Machine log：`MEDIUM_RUN.json`、`l3b_medium_real_run.txt`.
