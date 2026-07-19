# Phase 1C-C.2.2｜Synchronized Text–Journey Workspace

## 目标

在读者旅程可视化已就绪时，将分析结果页的「读者旅程」Tab 切换为**正文–旅程同步工作台**，实现 Scene / Phase / 证据段落在结构化正文与旅程曲线之间的双向定位。

## 布局

当 `tab=reader-journey` 且存在 `visualization` 时：

- 隐藏左侧永久 Scene 列表与中间单 Scene 正文列
- 主区域为 `ReaderJourneySyncWorkspace`
- 模式：`sync`（默认，58/42 分屏）| `journey`（全宽旅程）| `reading`（全宽正文）
- 可选「章节结构」抽屉替代 Scene 列表
- URL 同步：`tab`、`mode`、`scene`、`paragraph`、`metric`、`cluster`（不含正文）

断点：

- ≥1280px：水平分屏
- 900–1279px：垂直分屏
- <900px：正文/旅程 Tab 切换

## 关键文件

| 文件 | 职责 |
|------|------|
| `types/journeySelection.ts` | 选择状态类型 |
| `hooks/useJourneySelection.ts` | 状态 + URL 同步 |
| `StructuredChapterTextPane.tsx` | 结构化章正文 + 结构轨 |
| `ReaderJourneySyncWorkspace.tsx` | 编排分屏、加载章段落 |
| `ReaderJourneyWorkspace.tsx` | 受控选择（`activeSceneOrdinal` 等） |

## 数据

- 章段落：`GET /api/v1/chapters/{chapter_id}/paragraphs?limit=500`（分页至 `has_more=false`）
- Scene 14 真实范围：`B0001-C0002-P0064`–`P0068`

## 测试

- 单元：`StructuredChapterTextPane.test.tsx`、`ReaderJourneySyncWorkspace.test.tsx`
- E2E：`e2e/phase_1cc2_2_sync_workspace.spec.ts`

## 边界

- 仅前端 + 确定性映射；无模型调用、无 Profile DB 变更
- `visualization_version` 保持 1.1
- PNG 导出仍仅针对 `journey-export-root`（不含分屏 chrome）
