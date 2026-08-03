# TASK_CONTROL_AUDIT — CHG-20260803-045

## Existing controls（single state machine）
`whole_book_run_v1_service`：pause / resume / cancel；status：pending/running/paused/recoverable/completed/failed/cancelled 等。  
**不得创建第二套任务状态机。**

## Matrix

| Behavior | Status | Evidence |
|---|---|---|
| Pause 不启新 Unit | PARTIAL | WB-1.8 / WB-2.1 / WB-2.2 service tests |
| In-flight call 合同处理 | PARTIAL | orchestrator cancellation_ref |
| Resume 从未完成 Unit | PARTIAL | unit checkpoint；缺跨模块 E2E |
| 已完成 overview 不重跑 | PARTIAL | pipeline completed short-circuit；缺 mid-run 证明 |
| 已完成 structure 不重跑 | PARTIAL | structure checkpoint reuse |
| CF 已完成 batch 不重跑 | PARTIAL | batch unit_key；需显式测 |
| Resume 不重复计费 | PARTIAL | duplicate resume tests（wb21/wb22） |
| Duplicate Resume | PARTIAL | `test_p_duplicate_resume_no_extra_provider_calls` |
| Cancel 后禁止继续 | ALREADY COMPLETE | cancel blocks resume tests |
| Cancel 后 Resume | ALREADY COMPLETE（禁止） | 现有冻结合同：cancel → resume raises |
| 重启不自动真实 Provider | ALREADY COMPLETE（默认） | Free create_real blocked；fixture flag |
| 手动 Resume 前安全 | PARTIAL | prepare recoverable_run；UI 控制缺口 |
| Terminal > stale interrupted | PARTIAL | Journey/CHG-029 强；whole-book Free 页弱 |
| ProgressCard 终态消失 | PARTIAL | Free page mode；需对齐 v1.1.2 Journey 语义 |
| Main / Rail 一致 | PARTIAL | Wave D / layout tests；需 E2E 回归清单 |

## Verdict
**PAUSE / RESUME / CANCEL：GAP**（服务层存在；四模块正式链路+UI 未闭环）

## Wave 1 must-fix / must-test
1. Free 页任务控件绑定同一 Run  
2. mid-pipeline pause/resume/cancel 跨 overview→CF  
3. ProgressCard 终态与 Main/Rail 一致性（复用 v1.1.2 规则，不新状态机）  
4. 应用重启后不自动启动 Provider Unit（隔离 DB）
