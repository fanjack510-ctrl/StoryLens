# 开发者环境

## 要求

- Windows 10/11（V1.0 正式支持）  
- Python 3.11 或 3.12（`<3.13`）  
- Node.js 20+  
- Rust stable（Tauri 桌面打包时）  

## 一键脚本

```powershell
.\scripts\bootstrap.ps1          # → bootstrap_windows.ps1
.\scripts\start-dev.ps1          # → start_storylens_dev.ps1
.\scripts\check-project.ps1      # venv: check_project.py + pytest
.\scripts\build-release.ps1      # → build_desktop.ps1（标注 1.0.0-rc1）
```

停止：`.\scripts\stop_storylens_dev.ps1`

## 配置

从 `.env.example` 复制为 `.env`。密钥只放本机环境或 OS keyring。

默认自动化测试使用 Fake Provider，**不会**调用真实 Qwen。真实调用必须显式授权。

更多架构细节见 [architecture.md](architecture.md) 与 `docs/01_architecture.md`。
