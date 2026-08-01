# WB-2.1 SCOPE AND IMPLEMENTATION PLAN

CHANGE：CHG-20260801-032  
DATE：2026-08-01  
PRODUCT CODE MODIFIED：NO  
REAL PROVIDER CALLS：0  

## Baseline

| Item | Value |
|---|---|
| Public branch | `integration/1.2.0-after-1.1.2` |
| Public HEAD | `1ff1649043b98ee34738788bec81f18a80b5a1dc` |
| Private branch | `integration/1.2.0-private-after-1.1.2` |
| Private HEAD | `80b9ba75cd8041381dea8f2cd0ee95fc4695820c` |
| Public CLEAN | YES |
| Private CLEAN | YES |

## WB-2.1 SOURCE FILES（直接提及）

| Path | Lines / section |
|---|---|
| `docs/whole-book/EXECUTION_REGISTRY.json` | 429, 433–445, 457 — step definition |
| `docs/whole-book/PROTECTED_WORKTREES.md` | 4, 33, 37 — empty-policy WIP + selective port under WB-2.1 |
| `release/evidence/whole-book/WB-1.7/MANUAL_TEST.md` | 29 — do not start WB-2.1 |
| `release/evidence/whole-book/CHG-20260731-029/MANUAL_SMOKE_ENV.md` | 21 |
| `release/evidence/whole-book/CHG-20260731-029/TEST_RESULTS.md` | 49 |
| `release/evidence/whole-book/CHG-20260801-030/TEST_RESULTS.md` | 33 |
| `release/evidence/whole-book/CHG-20260801-031/MANUAL_GATE_RESULT.md` | 22 |
| `release/evidence/whole-book/CHG-20260801-031/TEST_RESULTS.md` | 36 |

Private worktree：无 `WB-2.1` 字面匹配。

## Supporting evidence（非字面 WB-2.1，但界定产品/技术范围）

| Path | Role |
|---|---|
| `release/evidence/whole-book/WB-1.6A/FINAL_REPORT.md` | Free 4 / Pro 8 capability contract |
| `apps/api/app/narrative_core/services/whole_book_product_capability_v1.py` | `whole_book.structure` = Free planned |
| `apps/desktop/src/services/wholeBookFreeProductApi.ts` | UI Free modules; structure planned |
| `release/changes/CHG-20260725-001.json` | Lab Structure Stages V2（tested，非 Free 产品化） |
| `apps/api/app/narrative_core/services/structure_stages_output_contract_v2.py` | StructureStagesResultV2 contract |
| Private `modules/structure_stages/` + citation policy | Lab/Private engine 已实现 |
| `docs/architecture/narrative-intelligence-core/phase2b-first-four-modules.md` | Engine first-four（含 storylines；与 Free 四模块不同） |

## Formal definition（最高优先级：EXECUTION_REGISTRY）

```json
{
  "step_id": "WB-2.1-STRUCTURE-STAGES",
  "change_id": "CHG-20260728-018",
  "manual_gate_id": "MG-WB-2.1",
  "phase": "WB-2",
  "title": "Structure stages (+ empty-policy rebase)",
  "acceptance_level": "L3",
  "depends_on": ["WB-1.10-CONFIRM-NO-OVERWRITE"],
  "next_step": "WB-2.2-CHAPTER-FUNCTIONS",
  "wb_status": "planned"
}
```

**MISSING：** `release/changes/CHG-20260728-018.json` 不存在（018–038 整段缺失）。因此详细验收条款、API 清单、Migration 决策不能从正式 Change Registry 读取。

## Answers to required questions

| # | Question | Answer | Evidence |
|---|---|---|---|
| 1 | Formal name | **WB-2.1-STRUCTURE-STAGES** / title「Structure stages (+ empty-policy rebase)」 | EXECUTION_REGISTRY |
| 2 | Module | Whole-book Free product module **故事结构**；engine key **`structure_stages`**；capability **`whole_book.structure`** | capability + Free UI + engine |
| 3 | User problem | 从完整原文识别可变结构阶段与转折点，并给出可深链 Evidence（非强制三幕式） | phase2b-first-four + V2 contract |
| 4 | Free / Pro | **Free**（planned → 本步产品化） | WB-1.6A |
| 5 | Free 4 modules? | **Yes** — Free 第 3 项（overview、characters_events 已 available） | WB-1.6A / capability registry |
| 6 | 故事结构? | **Yes** — UI label「故事结构」 | Free product page |
| 7 | 章节功能? | **No** — 属 **WB-2.2-CHAPTER-FUNCTIONS** | EXECUTION_REGISTRY next_step |
| 8 | Depends overview? | Pipeline 顺序上 overview 已在 WB-1.6；WB-2.1 registry 依赖是 **WB-1.10**，非“读取 overview 结果作为输入” | WB-1.9 native independence |
| 9 | Depends characters/events? | **不得依赖**为原生输入；可与同 Run 并存展示 | WB-1.9 / Wave D contract |
| 10 | Evidence deep link? | **Yes** — citations / evidence 精确定位；禁止模糊回退 | Assumption C + V2 citation rules |
| 11 | Real Provider? | Gate **L3**；本规划轮 **0**；实现轮默认 Fake/fixture，真实 Provider 需单独批准 | MANUAL_GATE_POLICY / EXECUTION_MASTER_PLAN |
| 12 | Private Engine? | **Yes** | CHG-20260725-001 + private runner |
| 13 | Data model? | Lab：`structure_stage` Narrative Asset；无独立 structure 表。Free 流水线 stage codes **尚未含 structure** | enums + WHOLE_BOOK_STAGE_CODES_V1 |
| 14 | API placeholder? | Lab：`/api/v1/whole-book-runs/{id}/results/structure_stages`；Free product **未暴露** structure 结果 | results router vs free product |
| 15 | UI placeholder? | **Yes** — `PlannedModulePanel`「故事结构 / 开发中」 | WholeBookFreeProductPage |
| 16 | Tests / fixtures? | Lab FakeHttp A–J + private schema tests；Free product structure：**无** | CHG-001 tests |
| 17 | Input source | **原始全书 Snapshot / Revision**（原生整书） | WB-1.9 verified |
| 18 | Allowed reads of chapter/journey/aggregate? | **Forbidden as native input** | WB-1.9 + inherited boundaries |
| 19 | Output fields | V2：`contract_version`, `coverage_scope`, `stages[]`, `turning_points[]`（+ confidence/limitations/context_capabilities）；stages 含边界与 cited summary；`stages=[]` **仅** `coverage_scope=insufficient` | structure_stages_output_contract_v2 |
| 20 | Missing/short/long/empty | **Empty-policy 细节在 Protected WIP，未进入本基线** → UNRESOLVED for product rules；Lab 已有 insufficient / local / overlap fail-closed 等 FakeHttp 场景 | PROTECTED_WORKTREES + A–J tests |

## SOURCE CONSISTENCY：INSUFFICIENT（含局部 CONFLICT）

### CONFLICTING / DRIFT DOCUMENTS

1. **缺失正式 Change `CHG-20260728-018`** — Registry 绑定存在，文件不存在。  
2. **EXECUTION_REGISTRY `wb_status` 仍为 planned**，而 Change Registry 中 WB-1.1/1.2/1.3/1.9/1.10 已 verified；WB-1.4–1.8 为 tested — registry 机器状态过期。  
3. **Protected WIP 迁移目标**写 `integration/whole-book-v120`，当前开发基线为 `integration/1.2.0-after-1.1.2`。  
4. **Phase2B “first four”**（overview / structure_stages / chapter_functions / **storylines**）与 **Free 四模块**（overview / characters_events / structure / chapter_functions）不同；storylines 为 Pro。不得混用。  
5. **Desktop Phase1D `StructureStagesResultDto`（V1）** 与 **Lab V2 cited-claim** 并存；Free 产品应采用哪套 UI 模型未在 CHG-018 冻结。  
6. **CHG-20260725-001**（Lab V2，tested）≠ Free Wave D 产品接线；不得把 Lab 完成等同于 WB-2.1 完成。

### Inherited boundaries（must keep）

- 原生全书文本输入；不依赖单章分析 / 阅读旅程 / Aggregate Insights  
- 已确认结果不静默覆盖；冲突新版本  
- Evidence 精确深链  
- Free 模块数 = 4；Pro = 8；无 Pro 购买界面  
- 本轮规划不调用真实 Provider；不为具体小说定制规则  

若 empty-policy WIP 审计后与上述冲突 → **阻塞**，不得自行调和。

---

## A. 用户可见功能（计划，待 CHG-018 补齐后实施）

| 项 | 计划内容 | 状态 |
|---|---|---|
| 入口 | 书籍页 → `/books/:bookId/whole-book`（现有 Free 入口） | 已有 |
| 显示 | 「故事结构」由 planned/开发中 → 可用结果（阶段列表、转折点、coverage、证据链） | 未实现 |
| 操作 | 仍走现有 prepare → 费用确认 → create/fixture → progress；structure 作为同 Run 模块结果读取 | Free pipeline 未含 structure stage |
| 失败/空/冲突 | insufficient 空阶段、失败 stage、冲突 revision — UI 需明确；细节受 empty-policy 约束 | UNRESOLVED |
| 与占位关系 | 替换 `PlannedModulePanel`「故事结构」；**不**实现「章节功能」（WB-2.2） | — |

## B. Public 工作（授权实施后）

| Area | Plan | Certainty |
|---|---|---|
| DB model | 优先复用 Narrative Asset `structure_stage` + Evidence；是否扩展 `WHOLE_BOOK_STAGE_CODES_V1` / provider units | **UNRESOLVED**（需 CHG-018 + WIP audit） |
| Migration | 仅当 stage/runtime 字段扩展时 REQUIRED | UNRESOLVED |
| Repository / Service | Free product service 接线 structure；capability `whole_book.structure` → available；复用/桥接 Lab mapper | REQUIRED |
| API | Free 结果读取路径；保持 prepare 双路径；不破坏 pause/resume/cancel | REQUIRED（具体 path 未冻结） |
| Types | TS 对齐 StructureStagesResultV2（或正式投影 DTO） | REQUIRED |
| Desktop | 结果面板、空/失败/冲突、Evidence deep link、1366/1920 | REQUIRED |
| Tests / Fixture | Free fixture 含 structure；回归 Lab A–J；capability count 不变（仍 4 Free） | REQUIRED |

## C. Private 工作

**PRIVATE IMPLEMENTATION：REQUIRED**（非 NOT REQUIRED）

依据：CHG-20260725-001；Public contract 委托 Private `validate_structure_stages_result_v2`；runner/prompt pack 已在 private HEAD；WB-2.1 标题要求 **empty-policy rebase**（Protected Private WIP `fix/phase2br1-structure-empty-policy` @ `5dabfd5…`，只读审计后 selective port）。

范围：empty-policy / citation empty-observation / coverage binding 的选择性迁入；输入输出 Contract 对齐 V2；错误码与确定性规则；Private 单测。禁止 raw copy dirty tree。

## D. 数据流（目标）

```
原始书籍
→ Immutable Snapshot / Revision（WB-1.2）
→ Cross-chapter windows（WB-1.3）
→（可选并行）entity/event + overview（已有 Free）
→ WB-2.1 输入：Snapshot + CitationCatalog / context capabilities（原生文本窗口，非章节分析结果）
→ Private structure_stages runner（Fake 或批准后的 Provider）
→ StructureStagesResultV2 中间/最终结果
→ Narrative Asset(structure_stage) + Evidence（精确深链）
→ Free UI「故事结构」展示
```

## E. 状态机（仅仓库实际使用）

**Run（canonical）：** `pending` · `running` · `paused` · `recoverable` · `failed` · `completed` · `cancelled`  

**不得硬加：** `not_started` · `preparing` · `queued` · `canceled`(美式拼写) · `conflict`（冲突用 revision/asset 模型，非 Run status）

**Stage：** `pending` · `running` · `paused` · `completed` · `failed` · `skipped` · `cancelled`  

**UI 展示映射：** `pending` / `current` / `done` / `failed` / `paused`（`wholeBookFreeProductStages.ts`）

## Database audit

| Question | Verdict | Evidence |
|---|---|---|
| 新表？ | **UNRESOLVED** for Free wiring；Lab path **NOT REQUIRED** 新表 | CHG-001 `database_changed=false`；Free stage codes 无 structure |
| 扩展现有 whole-book 表？ | **UNRESOLVED** | 可能扩展 stages/provider units |
| JSON payload 版本？ | **REQUIRED**（V2 `contract_version=2.0.0`） | output contract |
| 影响现有 Fixture？ | **REQUIRED**（Free fixture 需扩） | free product fixture pipeline |
| 影响 v1.1.2 单章？ | **NOT REQUIRED** if native isolation kept | WB-1.9 |
| 影响 WB-1.7–1.10？ | **可能回归** progress/capability/UI；须测 | Wave D |
| 旧库打开？ | **目标：允许**（additive） | 待 Migration 决策 |
| 回滚 | 关闭 capability 回 planned；不删用户 confirmed assets | WB-1.10 |

## API audit（计划级；路径未在 CHG-018 冻结）

| API | Plan | New / Reuse |
|---|---|---|
| `GET .../whole-book/prepare` + `/free/prepare` | 保持双别名 | Reuse |
| `POST .../free/create` · fixture · progress · pause/resume/cancel | 不破坏；progress 可出现 structure stage | Reuse + extend |
| `GET /api/v1/whole-book/product-capabilities` | structure：planned→available | Reuse |
| Lab `GET /api/v1/whole-book-runs/{id}/results/structure_stages` | 继续保留；评估是否增加 Free 产品别名 | Reuse / optional alias **UNRESOLVED** |
| Evidence source deep-link APIs | 复用 foundation | Reuse |

幂等：继续 `client_request_id`。权限：Free capability gate。真实 Provider 默认关闭。

## Risks → gates/tests

| Risk | Gate / Test |
|---|---|
| 全书过长 | window/partial_span/insufficient + FakeHttp；token/cost limits |
| Provider 截断 | repair max1 + fail-closed（Lab A–J） |
| 章节编号不连续 | window coverage / window binding tests |
| 空章/重复章 | empty-policy（WIP audit 后）+ fixture |
| Evidence 失效 | deeplink tests；stale citation scenarios |
| 旧 Revision 覆盖 | WB-1.10 conflict/version tests |
| 重复任务 | client_request_id idempotency |
| pause/resume 重复计费 | WB-1.8 + EXC task-control 边界 |
| Public/Private drift | contract schema tests both sides |
| v1.1.2 Journey 回归 | journey smoke / targeted suite |
| 1366/1920 布局 | CHG-031 layout tests + Playwright |
| Free/Pro 误露 | capability tests：Free=4，Pro=8，无购买 UI |

## Parallel agents

**PARALLEL AGENTS：2**（范围需 Backend+Private contract 与 Desktop 同时交付；文件所有权可分割。若授权前仅完成 CHG-018 补档与 WIP audit，则那一前置轮 **PARALLEL AGENTS：1**。）

### Agent 1 — Backend / Data / Contract / Private port

**Scope：** Migration（若需）、stage codes、Free service 接线、capability flip、Public↔Private contract、empty-policy selective port、Fake/fixture pipeline、backend tests。

**Ownership（预期）：**
- `apps/api/app/narrative_core/services/whole_book_free_product_v1_service.py`
- `apps/api/app/narrative_core/services/whole_book_product_capability_v1.py`
- `apps/api/app/routers/whole_book_free_product_router.py`（仅必要时）
- `apps/api/app/narrative_core/services/structure_stages_*`
- `apps/api/alembic/versions/*`（若新增）
- Private：`modules/structure_stages/**`, citation/empty-policy files（port 目标树，非 protected WIP）
- `apps/api/tests/test_whole_book_*structure*` / capability / free product API

**Tests：** capability；structure FakeHttp A–J 回归；free create/fixture+structure；pause/resume；native independence；no-overwrite。

### Agent 2 — Desktop / UI / Evidence

**Scope：** 故事结构结果页、类型、query、空/失败/冲突态、Evidence deep link、Vitest、Playwright 布局。

**Ownership（预期）：**
- `apps/desktop/src/pages/WholeBookFreeProductPage.tsx`（structure 面板区）
- `apps/desktop/src/pages/WholeBookFreeProductPage.module.css`（仅 structure 相关，避免与 Agent1 冲突）
- `apps/desktop/src/services/wholeBookFreeProductApi.ts` / stages helpers
- `apps/desktop/src/components/wholeBookFree/**`（structure 展示组件，新建优先）
- `apps/desktop/src/pages/wholeBookFreeProduct*.test.tsx`
- Playwright layout/evidence scripts under evidence dir

**Tests：** Vitest Free product；layout 1920/1366；deeplink；无 Pro 购买 UI。

### Shared / Integration-only

| Shared（禁止并行改） | Integration-only |
|---|---|
| `release/changes/*`, `release/unreleased.json` | 全量回归编排、capability↔UI 联调、Migration 与模型一致性 |
| `EXECUTION_REGISTRY.json` | Conflict/revision 行为验收 |
| `wholeBookFreeProductPage.tsx` 若必须双侧改 → Integration 合并 | prepare 双别名兼容证明 |
| Protected WIP paths | **永远禁止修改** |

**MERGE ORDER：** Agent1（contract+API+fixture）→ Agent2（UI 接真实类型）→ Integration → Manual Gate MG-WB-2.1 / 产品门禁。

## Integration plan

- Contract Public/Private 对齐（V2）  
- Migration/模型一致  
- API ↔ TS 类型一致  
- Conflict/Revision  
- Evidence 精确定位  
- Free=4 / Pro=8 / 无购买  
- v1.1.2 单章 + Journey 回归  
- Wave D Free prepare/progress/overview 回归  
- Typecheck + 相关全量测试  
- 隔离 UI 环境（非正式 AppData）  

两路实现 Agent **不得**各自宣称整体通过。

## Manual acceptance plan（此时不启动环境）

| Step | Manual / Auto |
|---|---|
| 正式书籍入口进入全书分析 | Manual |
| 未分析空状态 | Manual + Auto |
| 费用估算与确认 | Manual |
| 运行进度含结构阶段 | Manual + Auto |
| 暂停/恢复/取消（自动证据边界） | Auto primary；Manual spot |
| 故事结构结果完整性（阶段/转折/coverage） | Manual |
| Evidence 跳转原文 | Manual |
| 刷新与重新进入 | Manual |
| 冲突版本行为 | Manual + Auto |
| 无 Pro 购买界面 | Manual + Auto |
| 1366 / 1920 布局 | Manual + Auto（CHG-031） |
| 章节功能仍为开发中 | Manual |
| REAL PROVIDER = 0（除非批准 L3） | Auto + process |

## V1.1.2 regression

单章分析、Journey 状态机、既有桌面入口；不跑真实 Provider。

## Wave D regression

prepare 双路径、fixture 总览/人物事件、pause/resume/cancel、capability counts、布局 CHG-031。

## IMPLEMENTATION BLOCKERS

1. **`CHG-20260728-018` Change Registry 文件缺失** — 无正式实施 Change 正文。  
2. **empty-policy 仅在 Protected WIP** — 未做 read-only audit / selective port 计划细化；禁止猜测策略。  
3. **Free 产品数据流未定义到 stage-code 级** — DATABASE/API 多项 UNRESOLVED。  
4. **UI DTO 代际（V1 vs V2）未冻结**。  
5. **分支目标名漂移**（`whole-book-v120` vs 当前 `1.2.0-after-1.1.2`）需在实施 Change 中明示。  

**结论：** 本 CHG 完成范围抽取与压缩计划；**不得授权编码直至 blockers 至少关闭 #1，并完成 #2 的只读审计纪要。**

## CHG-032 status

`implemented`（规划/文档；无产品代码）  
不得标记 verified / ready / released。
