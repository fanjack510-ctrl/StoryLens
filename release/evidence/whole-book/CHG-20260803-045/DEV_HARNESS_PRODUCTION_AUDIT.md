# DEV_HARNESS_PRODUCTION_AUDIT — CHG-20260803-045

## Desktop routes

| Route / surface | Gate | Risk |
|---|---|---|
| `/dev/whole-book-diagnostics` | `import.meta.env.DEV` only（`router.tsx`） | OK if prod build strips |
| `/dev/whole-book-free-chapter-functions-harness` | DEV only | OK if prod build strips；Playwright 依赖 DEV |
| `/books/:bookId/whole-book` | production product | OK |
| WholeBook Mock Run Lab / runUx lab | feature folders；需确认未挂生产路由 | AUDIT → Wave 1 |
| Fixture Preview UI banner | product when flag on | **LABEL PRESENT**（`FIXTURE_PAGE_BANNER`） |

## Backend endpoints

| Surface | Gate | Risk |
|---|---|---|
| Free create-fixture routes | `fixture_preview_enabled` env | 正式构建若误开 env → 用户可跑 fixture；须默认 OFF + 标识 |
| `create_free` real | always raises disabled | OK for now |
| Mock lab router | `should_register_mock_lab_router` / env | 须确认生产 env 不注册 |
| Private engine lab | env | 同上 |
| Failure injection | test/scripts/seed | 不得挂公开 API |

## Frozen targets

| Target | Current audit |
|---|---|
| PRODUCTION DEV ROUTES | **ABSENT**（源码门禁）· **UNRESOLVED** without production build artifact test |
| PRODUCTION FAILURE INJECTION | **ABSENT**（未见生产挂载）· 需扫描确认 |
| PRODUCTION FAKE PROVIDER | **ABSENT** as default · fixture requires env flag |
| FIXTURE PREVIEW LABEL | **PRESENT** |

## Wave 1 must-fix / must-prove
1. Production build（`import.meta.env.PROD`）路由快照：**无** `/dev/*`  
2. 默认环境：fixture preview OFF；mock lab OFF  
3. 若 fixture ON：强制产品标识（已有 banner，补测试）  
4. 禁止 failure injection HTTP 进入正式 app.include_router  

发现泄漏 = Wave 1 **必修**。
