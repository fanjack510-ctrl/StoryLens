# docs/44｜Phase 1C-C.2.6.1 Header and Insight Density

**性质：** 展示层密度与标题去重。不改 selection transaction / useJourneySelection / 数据与公式。

## 1. 双标题根因

普通 Books 旅程页同时可见：

1. `journey-analysis-title`（Workspace 分析头）
2. `journey-export-title`（export root 内常显，本应为 PNG 专用）

Sync sticky `journey-sync-title` 在 results shell 下通常已隐藏，但仍可能叠加。

## 2. 标题去重方案

- 页面唯一可见标题：`journey-analysis-title` + 章节副标题
- `journey-export-title` / `journey-export-chapter` 使用 `.journey-export-only-title`：默认 `display:none`，`.journey-exporting` 时显示
- Sync sticky 标题隐藏（`syncWorkspace.css`），避免与分析头重复
- 非 compact 的 workspace-head 去掉第二处「旅程分析」h2

## 3. 章节结论条

四项结论改为紧凑 insight strip（44–56px），网格：

`minmax(280px,2fr) minmax(110px,0.8fr) minmax(150px,1fr) minmax(280px,2fr)`

## 4. 可点击结论语义

| 项 | 条件 | 行为 |
|----|------|------|
| 核心牵引 | 存在 primary cluster_id | `question-cluster` intent → inspector=question；不改 Scene |
| 峰值 | 始终 | 复用 `handleSelectScene` → 峰值 Scene |
| 薄弱区间 | 始终 | 选择 `engagement_valley` Scene（非区间起点） |
| 章尾钩子 | 存在 strongest_hook | `hook` intent；paragraph 仅在有 evidence 时写入 |

## 5. 不可点击视觉

无稳定 id 时使用 `div.journey-insight-static`：`cursor:default`，无 hover 边框，非 button。

## 6. 曲线宽度

`ResizeObserver` 以容器宽度设置 `chartWidth`（下限仍为 `sceneCount*48` / 520），SVG `width:100%`，min-height **300px**。坐标公式未改。

## 7. PNG

导出根内仅在 exporting 时显示标题；结论条紧凑；不含 Inspector / 导航 / 分隔线。

## 8. v2-4-1 Thaw

`audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-4-1.json`

白名单（4）：Workspace、SyncWorkspace、readerJourney.css、syncWorkspace.css。

## 9–10. Freeze / E2E

门禁需识别 v2-4-1。E2E：`phase_1cc261_header_insight_density.spec.ts`。
