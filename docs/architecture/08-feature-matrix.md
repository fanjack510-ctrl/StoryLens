# 08 — Feature Matrix

| 功能 | 状态 | 入口 | 备注 |
|------|------|------|------|
| 小说导入（TXT/DOCX/EPUB） | ✅ | `/library` | 支持 preview |
| 章节检测诊断 | ✅ | 书内 / reparse | diagnostics JSON |
| 章节重解析 / 换文件 | ✅ | ReparseDialog | 产生 revision book |
| 我的书库列表 / 搜索 | ✅ | `/library` | 类型筛选与排序 UI 未接线 ⚠️ |
| 正文阅读 | ✅ | `/books/:id?view=reading` | 字号/主题本地偏好 |
| 阅读进度书签 | ❌ | — | 无 last-chapter / scroll 持久化 |
| URL 章节与阅读器同步 | ⚠️ | BookRoutePage | 可能不同步 |
| Qwen 首次引导 | ✅ | 书库横幅 / Settings AI | BYOK |
| 云端同意与日预算 | ✅ | Settings + 启动分析 | 临时 run 额度 |
| 分析预检（preflight） | ✅ | StartAnalysisDialog | full-pipeline 建议 |
| 场景边界检测 | ✅ | 创建 AnalysisRun | 云端 v3.5 |
| 边界人工审阅 | ✅ | BoundaryReviewPanel | 普通云端路径 |
| 手动增删边界 | ✅ | BoundaryReviewPanel | |
| Scene Analysis | ✅ | confirm 后 / 自动路径 | 证据绑段落 ID |
| 场景分析结果展示 | ✅ | `view=result` | 结构 / evidence |
| 分析进度与失败提示 | ✅ | `view=progress` | |
| 统一恢复中心 | ✅ | UnifiedAnalysisRecoveryCard | |
| 预算暂停恢复 UX | ✅ | BudgetPauseRecovery | |
| Provider 恢复态 | ✅ | awaiting_provider_recovery | |
| Offline replay（场景） | ✅ | Tasks / API | 开发向 |
| Reader Journey 生成 | ✅ | result tab | scene v1.6 / chapter v1.2 |
| Journey 图表交互 v4.2 | ✅ | SyncWorkspace | MetricSelector |
| Journey Inspector / Evidence | ✅ | Journey UI | |
| Journey PNG 导出 | ✅ | 客户端 | |
| Journey JSON 导出 | ✅ | API | |
| Scene 结果 MD/JSON 导出 | ✅ | API | |
| 任务中心 | ⚠️ | `/tasks` | 仅开发者模式；`run_id` 深链未接 |
| 模型与 API 全面板 | ⚠️ | `/providers` | 开发者模式 |
| 本地 llama 启停 | ⚠️ | Providers | 非普通模式正式支持 |
| DeepSeek / GLM / Kimi | ❌ | Providers UI 灰置 | 规划中 |
| 案例库 | ❌ | `/cases` | Phase 占位 |
| 分析工作台（旧） | ⚠️ | `/workspace` | 开发入口 |
| 多章对比 | ❌ | — | V1 范围外 |
| 全书伏笔网络 / Neo4j | ❌ | — | V1 范围外 |
| 多模型投票 | ❌ | — | V1 范围外 |
| 商业计费 / 云账号 | ❌ | — | BYOK only |
| LICENSE 文件 | ❌ | 根目录 | 待操作者选定 |
| macOS / Linux 正式认证 | ❌ | — | 未封板 |
| Tauri 原生对话框 / 文件系统 API | ⚠️ | — | 依赖已装，业务未用 |

**图例：** ✅ 已完成 · ⚠️ 部分完成 · ❌ 未实现
