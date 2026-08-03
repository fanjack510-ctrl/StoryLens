# IDEMPOTENCY_AUDIT — CHG-20260803-045

## Keys present

| Domain | Key / behavior | Status |
|---|---|---|
| Run | `book_id|snapshot_id|mode|client_request_id|contract` | ALREADY COMPLETE |
| Provider Unit | orchestrator unit_key + request hash | ALREADY COMPLETE |
| CF batch | `chapter_functions:v2:batch:{i}` | ALREADY COMPLETE |
| CF repair | `{unit_key}:repair` | ALREADY COMPLETE |
| Structure unit | `structure_stages:v2` | ALREADY COMPLETE |
| Asset materialize | asset_key + confirmed no-overwrite | ALREADY COMPLETE |
| Evidence | asset↔evidence links；source state valid/stale/missing | ALREADY COMPLETE |
| Confirm | WB-1.10 confirm protection | ALREADY COMPLETE |
| Confirm + Start | Journey/scene 路径有；Free whole-book 需对齐检查 | PARTIAL |
| Revision bind | estimate/consent/run snapshot | ALREADY COMPLETE |
| Conflict version | AnalysisConflict on confirmed overwrite attempt | ALREADY COMPLETE |

## Target freezes（Wave 1 tests must prove）

| Metric | Target |
|---|---|
| DUPLICATE RUNS | **0** |
| DUPLICATE PROVIDER CALLS | **0** |
| DUPLICATE PROVIDER UNITS | **0** |
| DUPLICATE ASSETS | **0** |
| DUPLICATE EVIDENCE | **0** |
| CONFIRMED OVERWRITE | **0** |

证明方式：唯一键断言 + 行为路径（重复 create / duplicate resume / re-pipeline），**不得只数行数**。

## Gaps
1. 四模块同 Run 路径上的统一幂等套件（现分散在 wb14/15/18/21/22）  
2. UI 双击 Confirm/Start 与 API 幂等联调  
3. Fixture pipeline 二次执行 `reused` 与 completed short-circuit 正式断言扩大到 CF batches  

## Wave 2 debt（not Wave 1）
Public 48 failed / Vitest 30 / check_project TIMEOUT — 除非证明直接破坏上述幂等主链。
