# MANUAL_ACCEPTANCE_PLAN — CHG-20260803-048 / MG-V1.2.0-E2E-STABILIZATION

## Gate
MG-V1.2.0-E2E-STABILIZATION  
Integration evidence: CHG-20260803-048 · Planning: CHG-20260803-045

## Environment
See `MANUAL_UI_ENV.md` — isolated temp DB, ports 8007/1427, Fake/Fixture only, real provider **disabled**.

## Checklist

| # | Item | Automated evidence |
|---|---|---|
| 1 | 正式书籍入口进入 Free 全书页 | Playwright wb221 |
| 2 | 四模块同 Run 打开（overview → characters → structure → CF） | wb221 + Vitest |
| 3 | 浏览器刷新后模块/关键状态保持 | Vitest directed |
| 4 | 离开后重进：不新建 Run | Vitest directed |
| 5 | Evidence 深链使用真实 `chapter_id` | Vitest directed |
| 6 | CF：restore module / filters / cursor / detail | Vitest + Playwright |
| 7 | Pause / Resume / Cancel / restart recovery | wb221 backend |
| 8 | 冲突版本展示 | wb221 |
| 9 | 费用估算 + Consent 后行为 | wb221 |
| 10 | Provider disabled 时正式启动被阻止 | wb221 |
| 11 | 无购买 / License / 激活 UI | production build audit |
| 12 | 无 Dev Harness 正式入口（生产构建） | INDEX_NO_DEV / JS_NO_DEV |
| 13 | Fixture Preview 有明确标识 | Vitest directed |
| 14 | 终态 ProgressCard 消失（failed/canceled/completed） | Vitest directed |

## Deferred (non-gate)
- Reader offset highlight
- DEV diagnostics fuzzy

## Pass rule
Directed automated suites **PASS**. Manual gate pending owner walkthrough on `MANUAL_UI_ENV.md` environment.  
Full Journey suite **not required** for this wave (see `TEST_RESULTS.md`).

## Browser DOM (isolated env)
`DOM_VERIFY_RESULTS.json`: `page_ok_all=true`, purchase UI **ABSENT**, fixture banner present on fixture pages, layouts 1366/1920 OK.

## Status
Automated directed scope: **PASS**  
Browser DOM verify (smoke catalog sample): **YES**  
Manual MG walkthrough (owner): **pending** → NEXT: `MG-V1.2.0-E2E-STABILIZATION`
