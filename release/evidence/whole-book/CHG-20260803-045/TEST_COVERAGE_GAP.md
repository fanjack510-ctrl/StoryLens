# TEST_COVERAGE_GAP — CHG-20260803-045

## Existing (keep; do not rewrite modules)

| Area | Tests | Kind |
|---|---|---|
| Capability Free 4 | `test_whole_book_wb16a_product_capability.py` | unit/api |
| Overview pipeline | `test_whole_book_wb16_overview_pipeline.py` | integration (fixture) |
| Structure A–O | `test_whole_book_wb21_structure_stages_a_o.py` | integration |
| Chapter functions A–Y | `test_whole_book_wb22_chapter_functions_a_y.py` | integration |
| Pause/resume | `test_whole_book_wb18_pause_resume.py` + wb21/22 subsets | integration |
| Prepare alias | `test_whole_book_prepare_route_alias_chg030.py` | api |
| Free product UI | `wholeBookFreeProduct.test.tsx` | Vitest |
| Structure UI | `wholeBookFreeStructure.test.tsx` | Vitest |
| CF UI | `wholeBookFreeChapterFunctions.test.tsx` | Vitest |
| Layout 1366/1920 | `wholeBookFreeProduct.layout.test.tsx` | Vitest |
| CF Playwright | `e2e/wb22_chapter_functions.spec.ts` | **Harness DEV** |
| Structure Playwright | `e2e/wb21_structure_stages.spec.ts` | mostly product/mocks |

## Gaps (Wave 1 only)

| Gap | Priority |
|---|---|
| create-fixture consent validate 签名 + 产品入口测 | P0 |
| Evidence chapter_id（非 chapter_index）深链测 | P0 |
| Drawer 无 fuzzy fallback 测 | P0 |
| 跨四模块同一 Run 正式 API+UI 套件 | P0 |
| Cost estimate ↔ CF batch/repair 对齐测 | P0 |
| Free 页 Pause/Resume/Cancel + ProgressPanel/header | P0 |
| Duplicate create/resume/asset 统一套件 | P0 |
| Evidence returnModule overview/chars + CF restore round-trip | P0 |
| Refresh / reentry 不 create | P0 |
| 隔离 DB 进程重启矩阵 | P0 |
| Production build 无 `/dev/*` | P0 |
| 正式页 Playwright（非 harness）四模块切换 | P1 |
| Confirm+Start Free 对齐 | P1 |

## Explicitly NOT Wave 1
- Public 48 failed / 6 errors 全量修复  
- Vitest 30 readerJourney 全量修复  
- check_project TIMEOUT  
- 除非有证据证明某失败直接打断 Free 主链（见 IMPLEMENTATION_PLAN blockers）

## Regression coverage verdicts
- V1.1.2 Journey/scene：**PARTIAL**（已有 CHG-029 证据；Wave 1 需列定向回归命令）  
- Wave D：**PARTIAL**  
- WB-2.1：**PARTIAL→强**（已有 A–O + UI）  
- WB-2.2：**PARTIAL→强**（已有 A–Y + UI；缺正式页非 harness E2E）  
