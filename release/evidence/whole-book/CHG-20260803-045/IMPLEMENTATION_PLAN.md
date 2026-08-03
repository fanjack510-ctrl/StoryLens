# IMPLEMENTATION_PLAN — WB-2.2.1 / CHG-20260803-045

## Goal
稳定 Free 四模块**同一正式 Run**端到端行为（Fake/Fixture）；不新增分析模块；不开放真实 Provider（Wave 3）；不修 Wave 2 债务全集。

## In scope (must)

### Backend
1. **P0：修复 `create_fixture` → `validate_whole_book_consent` 调用签名**并补 create-fixture pytest  
2. Cost estimate 与 unit plan 对齐（CF batches；repair 策略明示）  
3. 跨四模块同 Run 集成测：stages、partial/fail 可读性、Resume 不重跑完成单元；审视 `project_result` 是否应 gate 四模块（最小必要）  
4. 幂等套件：duplicate run/unit/call/asset/evidence/confirmed overwrite = 0  
5. Pause/Resume/Cancel 跨阶段 + restart recovery（隔离 DB，不自动 Provider）  
6. Fixture vs formal 门禁回归（real create 仍禁用直至 Wave 3）

### Desktop
1. **P0：Evidence 深链改用 API `chapter_id`，禁止用 `chapter_index` 冒充 chapter id**  
2. **P0：消除 drawer fuzzy `indexOf`；CF Evidence 正式回链保持 restore\***  
3. 四模块正式页联调（非 harness）：切换 / 刷新 / 重进  
4. Evidence returnModule：overview + characters_events + structure + CF  
5. ProgressPanel 终态消失；header/模块态一致（对齐 v1.1.2）  
6. Production build：`/dev/*` ABSENT；fixture label PRESENT when enabled  

### Integration
合并后冒烟：四模块同 Run、Cost/Consent、任务控制、幂等、Evidence、刷新重进、生产路由隔离、定向回归、1366/1920。

## Out of scope
- WB-2.3 Storylines / WB-2.4 / Pro UI  
- Wave 2 全量失败修复  
- Wave 3 真实百炼  
- Installer / RC  

## Product code required
**YES**（Backend + Desktop）· Private：**YES** only if unit planning/cost helpers live in private adapters；prefer public-first；private only when engine batch estimate truth requires it.

## Implementation authorized
**NO** — waiting `AUTHORIZE WB-2.2.1 AGENT IMPLEMENTATION`

## Blockers before Agents
1. Owner accepts this plan  
2. MG-V1.2.0-SCOPE-RECONCILIATION already PASSED  
3. No Protected WIP edits  

## Success criteria (later MG-V1.2.0-E2E-STABILIZATION)
见 `MANUAL_ACCEPTANCE_PLAN.md`。
