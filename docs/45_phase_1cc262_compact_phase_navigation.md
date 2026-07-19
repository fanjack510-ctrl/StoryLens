# docs/45｜Phase 1C-C.2.6.2 Compact Phase Navigation Strip

**性质：** 旅程分析顶部 Phase 导航压缩与标题裁切修复。不改 selection transaction / useJourneySelection / Phase 数据与语义。

## 1. 文字遮挡根因

旧 Phase 卡为 **四行网格**（Phase 编号 / 两行 clamp 标题 / Scene 范围 /「平均牵引」+「· 当前」），并施加：

- `height` / `min-height` / `max-height: 72px`
- 标题 `-webkit-line-clamp: 2` + `overflow: hidden`

在固定 72px 壳内塞四行内容时，第二行标题被垂直裁切；选中态把「当前」拼进牵引行后更挤。

## 2. 为何桌面端不用下拉

Phase 1—4 承担全章横向比较与阶段定位。桌面端必须同时看见全部阶段；下拉只保留当前 Phase，会破坏结构概览。

## 3. 两行 Phase 结构

| 行 | 内容 |
|----|------|
| 1 | `Phase N · S起—止` …… 平均牵引数值（无「平均牵引」标签） |
| 2 | 阶段短标题（单行 ellipsis） |

导航条不再展示：核心问题、阶段回报、继续动力、节奏风险、当前 Scene、详细说明（仍在 Context Inspector）。

## 4. 当前 Phase 视觉

- 2px 主题色边框 + 浅背景
- 同行短标签「当前」（不拼在牵引数值后，不另起一行）

## 5. 中等宽度横向滚动

约 `701–1100px`：`grid-auto-flow: column` + `minmax(190px,1fr)` + 容器内 `overflow-x: auto`；禁止 2×2 增高；当前 Phase 仅通过 **strip.scrollTo** 滚入可见区（禁止 `scrollIntoView`，避免带动祖先滚动触发 Scroll Spy）；轻量滚动提示。

## 6. 小屏下拉

约 `≤700px`：显示「当前阶段」select；选项含编号、标题、Scene 范围、平均牵引；`onChange` 调用现有 `handleSelectPhase`（无第二套 activePhase）。

## 7. PNG

`.journey-exporting` 强制四列静态网格；隐藏 mobile select 与滚动提示；不出现横向滚动条。

## 8. v2-4-2 Thaw

`audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-4-2.json`

- purpose: `compact-phase-navigation-strip`
- 白名单：`ReaderJourneyWorkspace.tsx`、`readerJourney.css`（2 个生产文件）

## 9. Freeze

- FROZEN_CORE / FROZEN_CONTRACT 不变
- 仅 Thaw 白名单内 REUSABLE_UI_LOGIC 可改
- selection transaction / useJourneySelection 未改

## 10. E2E

`phase_1cc262_compact_phase_navigation.spec.ts`：1920 四列 / 1280 单行 / 窄屏下拉 / 长标题 ellipsis / PNG 四列。
