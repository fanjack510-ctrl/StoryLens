# docs/32｜Phase 1C-C.2.3A UI Shell Simplification

**阶段：** UI 壳层与信息架构精简  
**非目标：** 不执行 Single-Page Chapter Analysis Workspace；不改分析/任务跳转主流程。

## 1. 导航：修改前 → 修改后

**修改前主导航：** 首页 · 我的书库 · 分析工作台 · 任务中心 · 案例库 · 模型与API · 系统设置  

**修改后主导航：**

```
StoryLens
├─ 我的书库
├─ 设置
└─ 开发与诊断（默认折叠，localStorage: storylens.nav.devExpanded）
   ├─ 分析工作台
   ├─ 任务中心
   ├─ 案例库
   ├─ 模型与API
   └─ 系统状态（/settings）
```

- `/` → 重定向到 `/library`
- 旧路由全部保留，可从开发与诊断或直接 URL 访问

## 2. 书库页面

- 去掉装饰性 eyebrow / 冗长说明
- 搜索 · 文件类型 · 排序收成紧凑筛选栏
- 列表加宽；整行可点打开；Hash 降为悬停/次级
- 唯一 Primary：导入小说

## 3. 书籍章节页面

实现方式：`BookRoutePage` composition 包装未改哈希的 `BookWorkspacePage`。

- 顶部 CompactToolbar：开始分析（Primary）· 阅读设置 · 更多
- 分析前无 Artifact 时 CSS 隐藏空右栏，正文加宽
- 阅读设置弹层：字号 / 行距 / 正文宽度 / 段落 ID（`uiStore`）
- 更多：完整正文 · 场景边界审阅 · 重新识别章节 · 章节信息 · 技术信息
- 开始分析 / 边界审阅 / 重新识别复用原 `StartAnalysisDialog` / `BoundaryReviewPanel` / `ReparseDialog`
- 跳转任务中心行为不变

## 4. 分析结果页面

实现方式：`AnalysisResultsShellPage` composition 包装未改哈希的 `AnalysisResultsPage` / `ReaderJourneySyncWorkspace`。

顶部主操作（≤4）：

1. 返回章节  
2. 分析视图  
3. 读者旅程（有可视化时文案「查看读者旅程」）  
4. 更多  

内部仍切换现有 SyncWorkspace；模式文案经 CSS 映射为：正文与旅程 / 旅程总览 / 正文阅读（testid 不变）。

## 5. 按钮层级

| 层级 | 示例 |
|------|------|
| Primary | 导入小说、开始分析 |
| Secondary | 阅读设置、分析视图/读者旅程切换 |
| Tertiary | 更多内导出、技术信息、边界审阅 |

## 6. 更多菜单（结果页）

- 查看：章节结构 · 历史版本 · 技术信息  
- 导出：PNG / JSON / Markdown / 旅程 JSON（代理原有按钮）  
- 操作：返回任务记录 · 重新分析 · 高级边界审阅  

## 7. 技术信息

页脚不再常驻 FastAPI/SQLite/Provider。Run/Journey/Hash 等放入「更多 → 技术信息」。开发与诊断展开后可见后端连接摘要。

## 8. 路由兼容

保留：`/books/:bookId`、`/tasks`、`/analysis-runs/:runId/results` 及原业务行为。未做重定向重构，未建工作流表/聚合 API。

## 9. Freeze 验证

`scripts/check_core_freeze.py`：

- FROZEN_CORE modified=0  
- FROZEN_CONTRACT modified=0  
- REUSABLE_UI_LOGIC modified=0  

策略：壳层新组件 + CSS/composition；不修改 baseline manifest。

## 10. 后续单页面工作流边界

本阶段之后若做 1C-C.2.3 单页工作区：

- 仍须遵守 Core Freeze  
- 不得复制 SyncWorkspace / useJourneySelection  
- 不得自动串联 Reader Journey、不得新建 ChapterAnalysisWorkflow（除非单独立项）  
- 旧 results/tasks 路由先兼容后收敛  

## 用户启动与查看步骤（当前仍为多页）

1. 我的书库 → 导入/打开书  
2. 章节页 → 开始分析  
3. 任务中心（开发与诊断或 URL）  
4. 分析结果  
5. 读者旅程（结果壳层切换）  
