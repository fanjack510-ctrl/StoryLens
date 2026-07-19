# Phase 1C-C.2｜Reader Journey Visual Workspace

## 目标

将 Reader Journey 结构化结果渲染为「预测读者阅读旅程」可视化工作台。全部坐标、排序、归并与节点等级由确定性程序计算；不调用模型。

## 页面结构

1. 章节诊断摘要（可展开完整诊断）
2. 阅读阶段横向旅程（3—6 Phase）
3. 阅读牵引曲线（SVG，单指标切换）
4. 核心问题链（primary + ≤4 phase；secondary 折叠）
5. Scene 节奏带（core / secondary / beat）
6. 详情抽屉（点击 Scene）

标题：**预测读者阅读旅程**  
说明：基于文本结构与模型语义分析生成，不代表真实读者行为数据。

## visualization schema

`GET /api/v1/analysis-runs/{run_id}/reader-journey` 在 `status=succeeded` 时返回：

```json
{
  "visualization": {
    "visualization_version": "1.1",
    "chapter_summary": {},
    "phases": [],
    "curve_series": {},
    "scene_nodes": [],
    "primary_question_chain": {},
    "phase_question_chains": [],
    "secondary_question_chains": [],
    "payoff_markers": [],
    "hook_markers": [],
    "risk_intervals": [],
    "formula_versions": {},
    "calibration_status": {}
  }
}
```

实现：`apps/api/app/services/reader_journey_visualization.py`

## 公式版本

| 公式 | version |
|------|---------|
| engagement | `config/reader_journey_formulas.json` |
| chain rank | 1.0 |
| scene importance | 1.1 |
| chain merge | 1.0 |
| hook select | 1.1 |
| payoff derive | 1.1 |
| question cluster | 1.1 |
| visualization | 1.1 |

## Phase 1C-C.2.1 视觉校准（v1.1）

实现：`apps/api/app/services/reader_journey_visual_calibration.py`

- Scene 等级：`classify_scene_levels`（绝对阈值 + 强制地板 + 稀缺 demote）
- 主图 Hook：`select_visible_hooks`（每 Scene 最多 1 个可见 marker；全部 hooks 仍保留在 `scene_nodes[].hooks`）
- Payoff：`derive_and_select_payoffs`（从 `reader_question_answered` / `information_changes` 推导 micro payoff 并与 semantic payoff 去重）
- 问题簇：`build_question_clusters`（alias / escalation；可见簇 ≤5）
- 密度告警：`build_density_warnings`（Core / Hook 分布异常）

主图默认精简视图；前端可切换「完整标记」。诊断摘要增加 `primary_cluster_title`、`core_scene_count`、`strong_hook_count`、`stage_payoff_count` 及最长风险区间。

## 问题链

- 规则归并（弱词剥离、问题类型、实体冲突保护、n-gram）
- Ranking → 1 primary + ≤4 phase + secondary
- lifecycle：created / carried / transformed / answered / dropped / open

## Scene 节点

importance 公式 + 地板规则：章尾≥core，Phase 转折≥secondary，强钩子/强回报≥core。

## PNG 导出

前端 SVG→Canvas 2×，文件名 `StoryLens_{chapter}_ReaderJourney_v1.0.png`。

## 边界

- 真实模型请求 = 0
- 不修改 Scene 边界 / Profile / 不新建 JourneyRun
- 确定性数据与模型语义数据在 UI 中分开展示

## 测试

- `apps/api/tests/test_phase_1c_c2.py`
- `apps/api/tests/test_phase_1c_c2_1.py`
- `apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.test.tsx`
- `apps/desktop/e2e/phase_1cc2_reader_journey_visual.spec.ts`

## 后续

人工修订 journey revision UI；更细粒度同义归并词典。

## Phase 1C-C.2.2 同步工作台

正文–旅程分屏同步见 `docs/30_phase_1cc2_2_sync_workspace.md`。
