# MANUAL GATE PASS — MG-CHG-20260731-023-FINAL-STATE

MG-CHG-20260731-023 FINAL STATE ACCEPTANCE：**PASSED**

Gate：MG-CHG-20260731-023-FINAL-STATE  
Result：**PASSED**  
Change：CHG-20260731-023  
Target version：1.1.2  
Product fix head：`3fc04b61f10d2f9747c1869921a6089ee6f3f5db`  
LOADED FRONTEND COMMIT：`3fc04b61f10d2f9747c1869921a6089ee6f3f5db`  
Date：2026-07-31

## Frozen acceptance conclusions

| Item | Result |
|------|--------|
| 成功链路：interrupted → resume → succeeded → 自动显示结果 | PASS |
| 失败链路：interrupted → resume → failed → 显示生成失败 | PASS |
| 成功与失败顺序互换 | PASS |
| API 重启后仍通过 | PASS |
| 主页面与右侧栏一致 | PASS |
| terminal 后不残留「正在恢复」 | PASS |
| failed 不显示 ProgressCard | PASS |
| succeeded 不显示 ProgressCard | PASS |
| Resume Request = 1 | PASS |
| Analysis Recover Request = 0 | PASS |
| 新 Analysis Run = 0 | PASS |
| 新 Journey Run = 0 | PASS |
| Production Scenario Hook | ABSENT |
| Real Provider Calls | 0 |
| Formal Database Writes | 0 |

## URLs

SUCCESS URL：  
http://127.0.0.1:1467/books/1?chapter=1&analysisRun=1&journeyRun=1&view=progress&tab=reader-journey

FAILURE URL：  
http://127.0.0.1:1467/books/2?chapter=2&analysisRun=2&journeyRun=2&view=progress&tab=reader-journey

## Evidence

- `FINAL_STATE_FIX_REPORT.md`
- `acceptance/run_browser_e2e.ps1`（Playwright 三轮：fail→success / success→fail / API restart）
- `acceptance/MANUAL_FIXTURES.json`
- `acceptance/launch_api_accept.py`（TEMP-only；非产品 Worker）
- Vitest / API resume idempotency tests

## RC.5 incident (retained)

STORYLENS 1.1.2-RC.5 INSTALLED ACCEPTANCE：**FAILED**

Failure cause (unchanged)：

- succeeded Journey 被旧恢复状态覆盖；
- Resume 成功后页面未同步 terminal；
- 该缺陷已由 CHG-023 修复。

RC.5 安装包与归档继续保留，Hash 不得变化；本轮未重建 RC.5，未构建 RC.6。

## Constraints

- VERSION 仍为 1.1.2
- 未 Push / Tag / Release
- 未合并 `wip/chg023-abandoned-multi-state-fix`
