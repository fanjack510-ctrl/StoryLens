# AGENT_OWNERSHIP — WB-2.2.1

## PARALLEL AGENTS：**2**

真实缺口横跨 Backend 状态/幂等 与 Desktop 导航/生产隔离，拆两路合理。

---

### Agent 1 — Backend / State / Idempotency

**Scope**
- **P0：create-fixture consent validate 调用签名修复 + 测试**  
- Cost estimate ↔ provider unit planning（含 CF batch/repair 明示）  
- 四模块同 Run 编排断言与缺口修复（不重写模块契约）  
- Pause / Resume / Cancel / recoverable  
- Idempotency proofs  
- Restart recovery（隔离 DB；Fake）  
- Backend integration tests  

**File ownership（Public）**
- `apps/api/app/narrative_core/services/whole_book_cost_estimate_service.py`
- `apps/api/app/narrative_core/services/whole_book_free_product_v1_service.py`
- `apps/api/app/narrative_core/services/whole_book_fixture_pipeline_v1_service.py`
- `apps/api/app/narrative_core/services/whole_book_run_v1_service.py`
- `apps/api/app/narrative_core/services/whole_book_provider_orchestrator.py`（仅幂等/resume 必要）
- `apps/api/app/narrative_core/services/whole_book_minimal_*_v1_service.py`（最小必要；禁止无关重构）
- `apps/api/app/routers/whole_book_free_product_router.py`
- `apps/api/app/routers/whole_book_cost_consent_router.py`（若需）
- `apps/api/tests/test_whole_book_wb221_*`（新建）及相关 helpers  

**Private ownership（if required）**
- Private worktree：仅当 batch/cost 真值在 private adapters；路径在实施授权时冻结  
- 默认：**尽量 0 private 文件**

**Tests**
```text
pytest apps/api/tests/test_whole_book_wb221_*.py -q
pytest apps/api/tests/test_whole_book_wb18_pause_resume.py apps/api/tests/test_whole_book_wb21_structure_stages_a_o.py apps/api/tests/test_whole_book_wb22_chapter_functions_a_y.py apps/api/tests/test_whole_book_wb16_overview_pipeline.py -q
```

---

### Agent 2 — Desktop / Navigation / Production Isolation

**Scope**
- **P0：Evidence `chapter_id` 对齐 + 禁止 drawer fuzzy**  
- **P0：CF Evidence 正式回链保持 restore\***  
- Free 正式页四模块联调  
- refresh / reentry  
- Evidence return state（含 overview/chars returnModule）  
- ProgressPanel / header 态一致  
- Dev harness 生产隔离证明  
- Vitest / Playwright（正式页优先；harness 仅回归）  

**File ownership**
- `apps/desktop/src/pages/WholeBookFreeProductPage.tsx`
- `apps/desktop/src/pages/WholeBookFreeProductPage.module.css`
- `apps/desktop/src/components/wholeBookFree/**`
- `apps/desktop/src/services/wholeBookFree*.ts`
- `apps/desktop/src/services/wholeBookFreeEvidenceDeepLink.ts`
- `apps/desktop/src/app/router.tsx`（仅隔离相关）
- `apps/desktop/src/pages/wholeBookFree*.test.tsx`
- `apps/desktop/e2e/wb221_*.spec.ts`（新建）
- production route snapshot test（新建）

**Tests**
```text
cd apps/desktop && npx vitest run src/pages/wholeBookFreeProduct.test.tsx src/pages/wholeBookFreeStructure.test.tsx src/pages/wholeBookFreeChapterFunctions.test.tsx src/pages/wholeBookFreeProduct.layout.test.tsx
npx playwright test e2e/wb221_*.spec.ts
```

---

## Shared files（Integration-only merge / 禁并行双改）
- `apps/api/app/main.py`
- `apps/desktop/src/app/router.tsx`（若 Agent2 改完，Integration 复核）
- `apps/api/app/narrative_core/services/whole_book_product_capability_v1.py`
- `release/evidence/whole-book/WB-2.2.1-V120-E2E-STABILIZATION/**`
- `docs/whole-book/EXECUTION_REGISTRY.json`（Integration）

## Do not touch
- Pro insights / purchase / license UI  
- WB-2.3 storylines  
- Protected WIP worktrees  
- Wave 2 债务大修  

## Merge order
1. Agent 1（Backend）→ Public Integration  
2. Agent 2（Desktop）→ Public Integration  
3. Integration wiring + evidence + smoke  
4. Private merge **only if** Agent1 产生 private commits  

## Worktrees（建议，授权后创建）
- Public A1: `feature/wb-2.2.1-e2e-backend` from Integration HEAD  
- Public A2: `feature/wb-2.2.1-e2e-desktop` from Integration HEAD（或 A1 合并后）  
- Private：按需  
