# 叙镜 StoryLens

**StoryLens（叙镜）** 是面向小说作者与写作学习者的本地优先 AI 拆书、结构化分析与读者旅程可视化工具。

## V1.0（Community RC）你需要知道的

| 项 | 说明 |
|----|------|
| 是什么 | 单章导入 → 场景边界审阅 → Scene Analysis → Reader Journey → 导出 |
| 正式范围 | 单章阅读与分析、边界审阅、旅程图表 / Inspector / Evidence、PNG·JSON·Markdown 导出、任务恢复、本地持久化、**自带 Qwen Key** |
| 数据位置 | 本机 `data/storylens.db`；运行时 `data/runtime/`（勿提交） |
| AI 服务 | **必须自备**阿里云百炼 Qwen API Key（BYOK） |
| 云端账号 | StoryLens **不提供**云端账号 |
| 费用 | 由你的 **阿里云账户** 承担 |
| 普通模式正式支持 | 仅 **阿里云百炼 · Qwen**（`aliyun_qwen_plus` / 默认 `qwen3.7-plus`；`auto_route=false`；Flash fallback 关闭） |
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

### 主要 API（摘要）

- `POST /api/v1/books/import`
- `GET /api/v1/books`、`/chapters`、`/paragraphs`
- `POST /api/v1/chapters/{chapter_id}/analysis-runs`
- `GET /api/v1/analysis-runs/{run_id}`
- `GET|POST /api/v1/analysis-runs/{run_id}/recovery-plan` / `recover`
- Reader Journey 与导出相关接口见桌面端与 `docs/05_api_contract.md`

### 历史阶段文档

更细的 Phase 文档仍保留在 `docs/00_*.md` … `docs/51_*.md`。V1.0 普通用户请优先阅读上方「用户文档入口」。
