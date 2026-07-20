# Windows 桌面发布计划（第一阶段）

状态：审查完成，进入实现
分支：`feature/windows-desktop-release`
日期：2026-07-20

## 1. 审查结论摘要

当前 StoryLens 是**开发者双进程形态**：PowerShell 分别拉起 FastAPI（uvicorn）与 Vite；Tauri 仅为可选壳层，**不管理后端**。普通用户无法“安装即用”。

| 项 | 现状 |
|----|------|
| 前端启动 | `apps/desktop` → `npm run dev`（Vite `:1420`）；可选 `npm run tauri dev` |
| FastAPI 启动 | `scripts/start_backend.ps1` → `.venv` + `uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| Tauri 管后端？ | **否**。`main.rs` 仅 `tauri::Builder::default().run(...)` |
| Sidecar 打包？ | **无**。无 PyInstaller / Nuitka / `externalBin` |
| 安装包缺什么 | 后端运行时、sidecar、进程生命周期、用户数据目录、updater、图标配置、`tauri build` 流水线 |
| 命令行窗口 | 开发脚本用 `-WindowStyle Hidden`；Tauri release 有 `windows_subsystem = "windows"`；交互 `run_api.ps1` 会露控制台 |
| 用户数据 / SQLite | 默认 `sqlite:///./data/storylens.db`（相对仓库 CWD），无 `%LOCALAPPDATA%` |

## 2. 原启动架构

```text
用户 PowerShell
  → bootstrap.ps1（创建 .venv、装依赖）
  → start-dev.ps1
       → start_backend.ps1（隐藏窗口 uvicorn :8000）
       → start_desktop_dev.ps1（隐藏窗口 Vite :1420，或 -Tauri）
  → 浏览器 / Tauri WebView → fetch http://127.0.0.1:8000
  → SQLite：./data/storylens.db
```

依赖：本机 Python、Node.js、手动脚本。`build-release.ps1` 仅产出 Vite `dist`，不产出安装程序。

## 3. 目标启动架构（本阶段）

```text
用户双击 StoryLens.exe（NSIS/MSI 安装后）
  → Tauri 主进程
       → 解析/分配本地端口（仅 127.0.0.1）
       → 启动 sidecar：storylens-api.exe（无控制台窗口）
       → 等待 /health
       → WebView 加载内嵌前端
       → 前端通过 invoke 取得 API_BASE 后再发业务请求
       → 退出时结束 sidecar
  → 用户数据：%LOCALAPPDATA%/StoryLens/
       database/  logs/  uploads/  exports/  config/
  → 启动后可选检查更新（失败不影响本地分析）
```

开发环境保持现有 `start-dev.ps1`；正式安装与开发使用不同数据目录。

## 4. 后端 sidecar 方案选型

| 方案 | 评估 |
|------|------|
| PyInstaller | 与当前 FastAPI/uvicorn/SQLAlchemy 栈匹配，社区成熟，选为**本阶段方案** |
| Nuitka | 编译更慢、环境更重，暂不采用 |
| 嵌入式 Python 目录 | 体积大、生命周期复杂，暂不采用 |

要点：

- 入口：`apps/api/sidecar_main.py`（设置环境变量后再加载 app）
- 资源：`packages/prompts`、`config/reader_journey_formulas.json` 等随包
- 监听：`127.0.0.1` only；端口由 Tauri 注入 `STORYLENS_APP_PORT`
- Windows：`CREATE_NO_WINDOW`，避免黑窗

## 5. 用户数据目录

| 环境 | 根目录 |
|------|--------|
| 正式安装（frozen / `STORYLENS_APP_ENV=production`） | `%LOCALAPPDATA%/StoryLens/` |
| 开发 | 仓库内 `./data/`（兼容现有行为）；可通过 `STORYLENS_DATA_DIR` 覆盖 |

子目录：`database/`、`logs/`、`uploads/`、`exports/`、`config/`。
升级不删数据；卸载默认不删书库；不把用户库打进安装包。数据库业务 schema 不变。

## 6. Tauri updater 基础

- 插件：Tauri 2 官方 `updater` + `process`（重启）
- Endpoint：`https://github.com/fanjack510-ctrl/StoryLens/releases/latest/download/latest.json`
- 公钥：构建变量 / 正式配置注入；私钥仅 GitHub Secrets
- 开发可关闭检查；失败不阻断本地分析；无强制更新

## 7. 版本与构建

- 单一脚本：`scripts/set_version.ps1 <version>`
- 统一：`pyproject.toml`、`apps/desktop/package.json`、`tauri.conf.json`、`Cargo.toml`、FastAPI `version`
- 一键构建：`scripts/build_windows_release.ps1` → `dist/release/`（gitignore）
- CI：Windows runner，手动 / tag 触发；有 Secret 才签名；不自动正式 Release（除非后续成熟）

## 8. 错误提示（中文面向用户）

覆盖：后端启动失败、端口占用、数据目录不可写、数据库打开失败、更新检查失败、缺少 sidecar、sidecar 意外退出。技术细节写日志。

## 9. 本阶段边界

不做：Prompt 开闭源调整、遥测、上传、登录计费、改分析/Reader Journey、提交与推送。

## 10. 实现清单（对照需求）

1. [x] 审查文档（本文）
2. [x] sidecar 构建与 Tauri `externalBin`（PyInstaller → `storylens-api.exe`）
3. [x] 用户数据目录与兼容路径（`%LOCALAPPDATA%/StoryLens/` + `STORYLENS_LEGACY_DATABASE_PATH`）
4. [x] 生命周期 / 健康检查 / 中文错误
5. [x] updater 客户端基础（启动检查 + 设置页按钮；开发关闭）
6. [x] `set_version.ps1` / `build_windows_release.ps1` / `build_sidecar.ps1`
7. [x] GitHub Actions 工作流（`.github/workflows/windows-release.yml`）
8. [x] 验证与未验证项记录（见 §11）

## 11. 验证记录（2026-07-20）

| 项 | 结果 |
|----|------|
| `git diff --check` | 通过 |
| `python scripts/check_project.py` | 通过 |
| `./scripts/build_windows_release.ps1` | 生成 NSIS：`dist/release/StoryLens_0.1.0_x64-setup.exe`；含 sidecar |
| 安装包含 sidecar | 通过（`externalBin` + release 目录旁路拷贝） |
| 未装 Python 理论可运行 | 通过（sidecar 为独立 exe，`runw` 无控制台） |
| sidecar `/health` | 通过（临时数据目录 smoke） |
| 应用启动自动起后端 | 未验证（未做完整安装后 GUI 手工验收） |
| 退出关闭后端 | 未验证（代码路径已实现 `CloseRequested` → kill） |
| 用户库在安装目录外 | 未验证（代码默认 `%LOCALAPPDATA%/StoryLens/`；需安装后确认） |
| updater 检查流程 | 未验证（无真实 Release / latest.json） |
| 更新检查失败不影响本地 | 代码层通过（`checkForAppUpdate` catch 软失败） |
| updater 签名产物 | 未验证（本地私钥会交互式要密码；需 CI Secret 非交互签名） |

## 12. 关键路径

- 计划 / 密钥说明：`docs/windows-desktop-release-plan.md`、`docs/windows-desktop-updater-keys.md`
- Sidecar：`apps/api/sidecar_main.py`、`apps/api/storylens-api.spec`、`apps/api/app/core/paths.py`
- Tauri：`apps/desktop/src-tauri/src/{main,backend,updater_support}.rs`
- 前端：`DesktopBootstrap`、`updaterService`、`SettingsGeneralTab` 检查更新
- 脚本：`scripts/{build_sidecar,build_windows_release,set_version}.ps1`
- CI：`.github/workflows/windows-release.yml`
