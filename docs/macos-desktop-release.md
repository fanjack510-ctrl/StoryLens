# macOS 桌面安装包

StoryLens 1.3.6 提供 macOS 原生 DMG 构建。macOS 安装包必须在 macOS 上构建：
FastAPI/PyInstaller sidecar 和 Tauri 主程序都包含本机架构代码，不能从 Windows 交叉编译。

## 支持范围

| 安装包 | 处理器 | GitHub Actions runner |
|---|---|---|
| `StoryLens_1.3.6_arm64-onedir-candidate.dmg` | Apple Silicon（M1 及以后） | `macos-15` |
| `StoryLens_1.3.6_x64-onedir-candidate.dmg` | Intel Mac | `macos-15-intel` |

- 最低系统版本：macOS 12。
- 用户数据库：`~/Library/Application Support/StoryLens/`。
- 日志：Tauri 的 macOS 应用日志目录。
- API Key 仍由系统凭据库/本地环境读取，不进入安装包、构建日志或测试样本。
- PDF 导出使用本机已安装的 Chrome、Edge、Chromium 或 Brave；没有 Chromium 系浏览器时会给出明确提示。

## 构建与验证

GitHub Actions 手动运行 `.github/workflows/macos-release.yml`，输入仓库当前版本号。
工作流分别在 Apple Silicon 与 Intel runner 上执行：

1. Python 与 Rust 针对性平台测试；
2. PyInstaller 以 `onedir` 生成当前架构的 `storylens-api` 运行目录；
3. Tauri 生成 DMG；
4. 对 Sidecar 主程序、Python Framework 和所有 Mach-O 文件逐项核对签名身份；
5. 启动 sidecar 并检查 `/health` 与受保护的关闭接口；
6. 挂载 DMG，确认 `StoryLens.app` 和完整 Sidecar 运行目录存在；
7. 从隔离状态启动桌面程序，验证复制后的 Sidecar `/health`；
8. 输出 SHA-256 与构建摘要。

macOS 不再使用 PyInstaller `onefile`。旧方案会在每次启动时把
`Python.framework` 解压到 `_MEI...` 临时目录；实际 Apple Silicon 用户机器已经证明，
该路径仍可能因外层 Sidecar 与运行时 Python 的 Team ID 不一致而被 Library
Validation 拒绝。`onedir` 让全部运行时文件在 DMG 构建和安装启动时都可见、可签名、
可逐项验证。桌面程序复制的是完整运行目录，不会覆盖或迁移用户数据库。

`StoryLens_1.3.6_arm64-signfix-candidate.dmg` 已在真实 Apple Silicon 机器上复现
`different Team IDs`，因此已失效，不得继续作为修复版分发。新候选必须带
`onedir-candidate` 后缀，并在真实问题机器通过后才能替换正式资产。

onedir 收集完成后，构建脚本会把其中每个 Mach-O 作为独立代码对象重新签名，
再执行严格校验。这一步同时清除 Python.org Framework 原始 bundle 签名对未随
PyInstaller 收集的资源文件的依赖，避免 `code has no resources` 的无效签名。
完整运行树位于 App 的 `Contents/Resources/storylens-api-runtime`，避免把 Python
包元数据误判为 `Contents/MacOS` 下的代码子组件；桌面进程不会直接从资源目录执行它。

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

## 1.3.6 候选资产边界

已有 tag 不得移动。修复候选先作为 GitHub Actions artifact 留存；真实 Apple Silicon
机器验证前不得覆盖同名正式 DMG。发布说明必须记录 Mac 构建 commit、SHA-256、架构、
签名模式、是否公证，以及真实机器验收状态，保证资产来源可追溯。
