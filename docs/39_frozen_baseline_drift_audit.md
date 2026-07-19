# docs/39｜Frozen Baseline Drift Audit（Phase 1C-C.2.5.2-Audit）

**性质：** 只读审计。不修改生产代码、测试、Prompt、Schema、API、历史 Manifest / thaw、数据库。  
**产物：** `audits/mvp-functional-baseline-v1/frozen-drift-audit-2.5.2.json`

## 1. 结论摘要

| 项 | 数量 / 结果 |
|----|-------------|
| 漂移文件总数（相对 core-freeze raw SHA） | **18** |
| EXPECTED_PRESENTATION_DRIFT | **6** |
| UNEXPLAINED_REUSABLE_LOGIC_DRIFT（分类桶） | **4**（其中 **内容漂移 0**，均为 CRLF） |
| FROZEN_CONTRACT_DRIFT（分类桶） | **3**（其中 **内容漂移 0**，均为 CRLF） |
| FROZEN_CORE_DRIFT（分类桶） | **5**（其中 **内容漂移 0**，均为 CRLF） |
| missing | **0** |
| 仅换行符漂移（LF 归一后 == baseline） | **12** |
| `can_continue_ui_work` | **true**（语义内容完整；raw 哈希门禁仍 FAIL） |

**关键事实：** 全部 5 个 CORE + 3 个 CONTRACT + 4 个非白名单 REUSABLE 的 raw 哈希差异，在将 `\r\n` 归一为 `\n` 后 **SHA-256 与 baseline 完全一致**。即：**无公式/契约/选择内核内容改写**，仅为 Windows CRLF 换行导致的字节差。

## 2. 有效冻结视图（只读）

```
effective baseline =
  core-freeze-manifest.json
  + ui-presentation-thaw-v1.json
  + ui-presentation-thaw-v2.json
```

规则验证：

1. UI thaw **不能**覆盖 FROZEN_CORE / FROZEN_CONTRACT（`check_core_freeze.py` 行为正确）。
2. REUSABLE_UI_LOGIC 仅精确路径列入 thaw 才允许变化。
3. 当前仅存在 v1、v2；无其它 thaw 文件。
4. 非因「只加载一个 thaw」误报：两脚本默认均叠加 v1+v2（union=15）。

## 3. 漂移分类明细

### A. EXPECTED_PRESENTATION_DRIFT（6）

均在 v1/v2 白名单，且相对 baseline / thaw `before_sha256` 存在**真实内容**变化（展示链 2.4→2.5→2.5.1→2.5.2）：

- `ReaderJourneyWorkspace.tsx`
- `ReaderJourneySyncWorkspace.tsx`（见 §5 needs_review）
- `StructuredChapterTextPane.tsx`
- `sceneDetailFields.tsx`
- `exportJourneyPng.ts`
- `SplitPane.tsx`

另有 thaw 内 CSS / 新展示文件（不在 90 个 frozen 哈希项内，或按 thaw status 记为 allowed_modified / new_present）：`readerJourney.css`、`syncWorkspace.css`、`journeyUiLabels.ts`、`JourneySceneDetailPanel.tsx`、`overviewMode.ts`、`JourneyOverviewModes.tsx`、`JourneyResizableSplit.tsx` 等。

### B. UNEXPLAINED_REUSABLE_LOGIC_DRIFT（4，内容=0）

- `useJourneySelection.ts`
- `safeRender.ts`
- `JourneyDetailErrorBoundary.tsx`
- `exportSceneCard.ts`

全部 `line_ending_only=true`。**无 API / Selection / Scroll Spy / Evidence 内容级改写证据。**

### C. FROZEN_CONTRACT_DRIFT（3，内容=0）

- `readerJourneyVisualization.ts`
- `journeySelection.ts`
- `readerJourneyProfileItems.ts`

全部 CRLF-only。

### D. FROZEN_CORE_DRIFT（5，内容=0）

- `reader_journey_semantic_calibrate.py`
- `reader_journey_visual_calibration.py`
- `reader_journey_offline_replay.py`
- `reader_journey_question_lifecycle.py`
- `reader_journey_contract_migrate.py`

全部 CRLF-only。

### E. MISSING_OR_RENAMED

0。

## 4. 时间线推断（无 Git）

- `docs/37`（2.5.1）记录当时 `check_core_freeze` / thaw **PASS** 且 FROZEN_* modified=0。
- 因此 12 个 CRLF raw 漂移应出现在 **2.5.1 报告之后**（环境/编辑器/工具写回 CRLF），**不是** 2.5.2 故意改内核。
- 无历史字节快照可对比「谁写入 CRLF」；证据强度来自 **LF 归一哈希 == baseline**。

## 5. Phase 1C-C.2.5.2 边界核验

| 检查项 | 结果 |
|--------|------|
| Context Inspector 是否纯展示状态 | 是（`inspector=` URL，类似 `overview=`） |
| 第二套 activeScene / activePhase | 否 |
| 是否改 `useJourneySelection` 内容 | 否（仅 CRLF raw 漂移） |
| Scene 点击语义 | 仍更新 activeScene；Inspector 切 scene |
| Phase 点击语义 | Workspace **不再**随 Phase 写入 `activeSceneOrdinal`；SyncWorkspace `selectPhase` **不带** firstScene — **选择相邻 UX**，落在已 thaw 的 SyncWorkspace，但超出 thaw 文案 “no selection semantics” → **needs_review** |
| URL scene/metric | 未改语义；新增 `inspector` |
| Scroll Spy / Evidence / PNG 数据 / Profile / Visualization / 后端 | 未发现 2.5.2 改动 |

**2.5.2 自身引起：** 白名单展示文件内容演进（Workspace / SyncWorkspace / CSS / Phase 详情面板 / labels / overviewMode / ResizableSplit 等）。  
**2.5.2 之前已存在 / 环境造成：** 12 个 CRLF-only frozen 漂移。  
**无法确定作者工具：** CRLF 写入具体进程（无 Git）。

## 6. 脚本门禁与缺口

| 脚本 | 结果 | 说明 |
|------|------|------|
| `check_core_freeze.py` | **FAIL** | modified=12（5 CORE+3 CONTRACT+4 非白名单 REUSABLE）；thawed=6 |
| `check_ui_presentation_thaw.py` | **FAIL** | 正确叠加 v1+v2；仍因 FROZEN_* / 非白名单 raw 差失败 |
| `check_project.py` | PASS | |
| pytest | 271 passed | |
| ruff / tsc / eslint(RJ) | PASS | |
| vitest readerJourney | 76 passed | |
| build / e2e | 本轮未跑 | |

**缺口建议（只建议，不实现）：**

1. effective freeze checker：区分 `eol_only` vs `content`。
2. 可选 ops：将 12 个文件恢复为 LF，使 raw 门禁再 PASS（不得在本审计阶段执行）。
3. **禁止**自动接受新哈希进 baseline。

## 7. 数据库（只读）

来源：运行既有 `_readonly_audit.py`（该脚本会**重写** `database-baseline.json` 元数据；**未写 SQLite**）。本审计因此对既有 JSON 有一次旁路刷新，记入 JSON `database_state.audit_side_effect`。

| 项 | 值 |
|----|-----|
| integrity_check | ok |
| foreign_key_check | [] |
| AnalysisRun 总数 | 55 |
| ReaderJourneyRun 总数 | 2 |
| Run #55 | succeeded |
| JourneyRun #2 | succeeded |
| Profile（journey2） | 14 |
| Scene 6–19 | 14 |
| 活动 Reservation | 0 |
| AnalysisRun 新增 | 0 |
| ReaderJourneyRun 新增 | 0 |

## 8. 是否允许继续 UI 开发

**允许（`can_continue_ui_work=true`）**，依据：

- FROZEN_CORE **无法解释的内容漂移 = 0**
- FROZEN_CONTRACT **内容漂移 = 0**
- 非白名单 REUSABLE **内容漂移 = 0**
- 2.5.2 修改落在展示白名单（SyncWorkspace Phase 点击需人工复核）
- Run #55 / JourneyRun #2 succeeded；库完整；测试通过

**同时：** raw `check_core_freeze` / thaw 仍 FAIL，**不得**用「测试通过」宣称哈希门禁已绿。继续 UI 前应在独立 ops 中处理 EOL，或接受「语义绿 / raw 红」状态。

## 9. 费用与模型

真实模型请求=0；Token=0；费用=0；AnalysisRun 新增=0；ReaderJourneyRun 新增=0。
