# 10 — Open Source Checklist

状态说明：✅ 已具备 · ⚠️ 部分 · ❌ 缺失 / 待操作者

| 项 | 状态 | 说明 |
|----|------|------|
| **LICENSE** | ❌ | 根目录无 `LICENSE`；见 `docs/license-selection-notes.md`。**Agent 不得擅自选定** |
| **README** | ✅ | 根 `README.md` 含 V1.0 RC 说明与快速开始 |
| **环境安装文档** | ✅ | `docs/getting-started.md`, `docs/developer-setup.md` |
| **引导脚本** | ✅ | `scripts/bootstrap.ps1`, `scripts/start-dev.ps1`, `scripts/check-project.ps1` |
| **API Key 配置** | ✅ | `docs/qwen-api-setup.md`；`.env.example` 占位；Keyring 存储 |
| **数据隐私说明** | ✅ | `docs/privacy.md`；本地 SQLite；不上传文本到 StoryLens 云（无云账号） |
| **本地运行** | ✅ | Windows PowerShell 路径文档化；API `:8000` + UI `:1420` |
| **Docker** | ❌ | V1.0 未提供正式 Docker 发行路径 |
| **贡献指南** | ⚠️ | 有大量 phase/audit 文档；缺独立 `CONTRIBUTING.md` |
| **行为准则 / Security policy** | ❌ | 无 `CODE_OF_CONDUCT.md` / `SECURITY.md`（建议开源前补） |
| **依赖许可证报告** | ✅ | `audits/v1.0/v1.0-dependency-license-report.json` |
| **SBOM** | ✅ | `audits/v1.0/v1.0-sbom.json` |
| **Secrets 扫描** | ✅ | `audits/v1.0/v1.0-secrets-scan.json`（PASS） |
| **测试与门禁脚本** | ✅ | pytest / vitest / `scripts/check_project.py` |
| **发布构建** | ⚠️ | `scripts/build-release.ps1` 等；完整 E2E/视觉回归未全部在 readiness 中封板 |
| **Human UAT** | ⚠️ | Checklist 已备：`audits/v1.0/v1.0-human-uat-checklist.md`；待操作者执行 |
| **Git 远程 / GitHub** | ⚠️ | 本基线前工作树曾无 `.git`；公开仓库尚未发布 |
| **架构基线文档** | ✅ | 本目录 `01`–`10` + `audits/v1.0-baseline/` |
| **回滚标签** | ✅ | `storylens-v1.0-baseline`（本基线建立） |

## 开源前建议顺序（仅方案，本 pass 不执行）

1. 操作者选定 LICENSE → 放置 `LICENSE` → 更新 README 徽章  
2. Clean Install Human UAT PASS  
3. 补 `CONTRIBUTING.md` + `SECURITY.md`（披露渠道）  
4. 确认 `.gitignore` 覆盖 db / runtime / key / UAT 产物  
5. 初始化远程、推送 tag `storylens-v1.0-baseline`  
6. 再考虑 Docker / 多平台认证（可列为 V1.1）
