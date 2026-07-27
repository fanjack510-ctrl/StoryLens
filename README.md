# 叙镜 StoryLens

**StoryLens（叙镜）** 是面向小说创作者的本地优先 AI 拆书与结构化分析工具。

## StoryLens 1.1.0 你需要知道的

StoryLens 1.1.0 是面向小说创作者的**单章小说拆解与分析**版本。

| 项 | 说明 |
|----|------|
| 是什么 | 小说导入 → 章节阅读 → 场景边界审阅 → 单章结构化分析 → 任务进度 / 结果查看 |
| 正式范围 | **SINGLE CHAPTER ONLY**：书库与导入、章节阅读、场景边界识别与人工确认、单章分析、任务中心、失败/取消/恢复/重试、本地与云端模型配置、预算与费用控制 |
| 暂未开放 | 原生全书概览、章节聚合洞察、独立读者旅程分析入口（直接访问全书路由显示「该功能正在完善中」） |
| 数据位置 | 本机用户数据目录；运行时数据勿提交到 Git |
| AI 服务 | **必须自行填写**模型服务 API Key；软件**不内置**开发者个人 API Key |
| 原始文件 | 用户原始 TXT / DOCX / EPUB **不会被软件删除** |
| 云端账号 | StoryLens **不提供**云端账号 |
| 费用 | 由你的模型服务账户承担 |
| 平台 | Windows 10/11（PowerShell 脚本）；桌面栈 React + Vite + Tauri |

开源许可证尚未选定，见 [`docs/license-selection-notes.md`](docs/license-selection-notes.md)。**请勿**期望仓库中已有 `LICENSE` 文件。

## 快速开始

```powershell
cd D:\Dstorylens
.\scripts\bootstrap.ps1
.\scripts\start-dev.ps1
```

- 桌面开发界面：`http://127.0.0.1:1420`
- API 健康检查：`http://127.0.0.1:8000/health`

验收：

```powershell
.\scripts\check-project.ps1
```

用户文档入口：

- [入门](docs/getting-started.md)
- [Qwen 配置](docs/qwen-api-setup.md)
- [导入第一本书](docs/import-first-book.md)
- [第一次分析](docs/run-first-analysis.md)
- [边界审阅](docs/boundary-review.md)
- [读者旅程](docs/reader-journey.md)
- [预算与费用](docs/budget-and-cost.md)
- [恢复](docs/recovery.md)
- [隐私](docs/privacy.md)
- [故障排查](docs/troubleshooting.md)
- [开发者环境](docs/developer-setup.md)
- [架构](docs/architecture.md)

V1.0 发布就绪审计：`audits/v1.0/`。

---

## 工程说明（开发者）

推荐环境：Windows 11、Python 3.11/3.12、Node.js 20+、Rust stable（Tauri）、SQLite。

配置从根目录 `.env` 读取；不存在时可由引导从 `.env.example` 创建。API Key 也可经桌面向导写入操作系统凭据库，**不要**把真实 Key 提交到 Git。

默认自动化测试使用 Fake Provider，不连接真实模型。真实 Qwen 调用必须由操作者明确授权。

构建前端：`.\scripts\build-release.ps1`（调用 `build_desktop.ps1`；正式版本以 `tauri.conf.json` / `set_version.ps1` 为准）。
构建 Windows 安装包：`.\scripts\build_windows_release.ps1`。

### Narrative Intelligence Core（Phase 1C）

阶段状态与 Contract 文档见 [`docs/architecture/narrative-intelligence-core/README.md`](docs/architecture/narrative-intelligence-core/README.md)。Phase 1C-P（CHG-021）已冻结 Engine / Capability / Quota 契约；`PRO_CAPABILITIES_SHIPPED=false`；无真实整书引擎。

### 主要 API（摘要）

- `POST /api/v1/books/import`
- `GET /api/v1/books`、`/chapters`、`/paragraphs`
- `POST /api/v1/chapters/{chapter_id}/analysis-runs`
- `GET /api/v1/analysis-runs/{run_id}`
- `GET|POST /api/v1/analysis-runs/{run_id}/recovery-plan` / `recover`
- Reader Journey 与导出相关接口见桌面端与 `docs/05_api_contract.md`

### 历史阶段文档

更细的 Phase 文档仍保留在 `docs/00_*.md` … `docs/51_*.md`。V1.0 普通用户请优先阅读上方「用户文档入口」。
