# macOS 桌面安装包

StoryLens 1.3.4 增加 macOS 原生 DMG 构建。macOS 安装包必须在 macOS 上构建：
FastAPI/PyInstaller sidecar 和 Tauri 主程序都包含本机架构代码，不能从 Windows 交叉编译。

## 支持范围

| 安装包 | 处理器 | GitHub Actions runner |
|---|---|---|
| `StoryLens_1.3.4_arm64.dmg` | Apple Silicon（M1 及以后） | `macos-15` |
| `StoryLens_1.3.4_x64.dmg` | Intel Mac | `macos-15-intel` |

- 最低系统版本：macOS 12。
- 用户数据库：`~/Library/Application Support/StoryLens/`。
- 日志：Tauri 的 macOS 应用日志目录。
- API Key 仍由系统凭据库/本地环境读取，不进入安装包、构建日志或测试样本。
- PDF 导出使用本机已安装的 Chrome、Edge、Chromium 或 Brave；没有 Chromium 系浏览器时会给出明确提示。

## 构建与验证

GitHub Actions 手动运行 `.github/workflows/macos-release.yml`，输入仓库当前版本号。
工作流分别在 Apple Silicon 与 Intel runner 上执行：

1. Python 与 Rust 针对性平台测试；
2. PyInstaller 生成当前架构的 `storylens-api`；
3. Tauri 生成 DMG；
4. 启动 sidecar 并检查 `/health` 与受保护的关闭接口；
5. 挂载 DMG，确认 `StoryLens.app` 与 sidecar 都存在且可执行；
6. 输出 SHA-256 与构建摘要。

本地 Mac 也可以运行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,sidecar]"
STORYLENS_RC_CANDIDATE=1 ./scripts/build_macos_release.sh
./scripts/smoke_macos_release.sh
```

## 签名与公证状态

当前仓库没有 Apple Developer ID、证书或公证凭据，因此 GitHub Actions 只能生成测试用的未公证 DMG。
这不是可长期公开分发的最终状态：按照 Apple/Tauri 的正式分发要求，公开发布前应完成 Developer ID
签名和 Apple notarization。

未公证版本第一次启动时，macOS 可能阻止直接双击。测试者可以在 Finder 中右键应用选择“打开”，
或到“系统设置 → 隐私与安全性”确认允许。不要指导用户关闭 Gatekeeper，也不要移除系统安全属性。

正式签名需要在 GitHub Secrets 配置 Apple 证书、证书密码、Apple ID/App Store Connect 凭据，
且秘密值不得提交到仓库。配置完成后应将工作流改为“签名、公证成功才允许发布”。

## 1.3.4 追加平台资产

`v1.3.4` 已经发布并验证，tag 不得移动。macOS 平台适配作为同版本的追加构建提交存在；
若把 DMG 添加到现有 1.3.4 Release，发布说明必须记录 Mac 构建 commit 与“未公证测试版”状态，
保证资产来源可追溯。
