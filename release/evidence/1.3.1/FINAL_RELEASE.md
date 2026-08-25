# StoryLens 1.3.1 最终发布证据

- 发布日期：2026-08-25
- 安装包：`StoryLens_1.3.1_x64-setup.exe`
- 安装包大小：45,902,422 bytes
- SHA-256：`33279f33fd409e9972fe4ba1429fd5d0f5dae32bb19c0de110a7abc795a5682a`
- Windows 代码签名：未配置（`NotSigned`）
- Tauri updater 签名：未配置；未生成伪造签名或 `latest.json`

## 自动验证

- `scripts/build_windows_release.ps1`：通过
- `scripts/smoke_windows_release.ps1`：通过
- 发布烟雾测试：14 passed
- 打包 sidecar `/health`：HTTP 200
- sidecar 清理：无残留进程
- `npm audit --omit=dev`：0 vulnerabilities
- `npm run typecheck`：通过
- 路由与关键页面测试：29 passed
- `scripts/check_project.py`：通过（见 `RC1_VERIFICATION.md`）
- 版本门禁、变更台账门禁、产物门禁：通过

## 隐私与密钥

- `.env`、API Key、本地数据库、日志、授权私钥、生产授权码和本地参考语料均未纳入 Git 跟踪或发布产物。
- GitHub 仓库未配置 updater 私钥 Secret，因此本次只发布可校验哈希的 NSIS 安装包。

## 尚需人工验证

- 在一台干净 Windows 环境安装并确认 SmartScreen 提示后的启动流程。
- 待后续配置稳定的更新签名私钥后，再启用应用内自动更新通道。
