# Windows 更新签名密钥说明

- **公钥**：写入 `apps/desktop/src-tauri/tauri.conf.json` → `plugins.updater.pubkey`（可提交）。
- **私钥**：仅保存在本机 `.tauri/` 或 GitHub Secret `TAURI_SIGNING_PRIVATE_KEY`（**禁止提交**）。
- 构建时若无私钥，安装包仍可生成，但**不会**伪造 updater 签名产物。
- 本地/CI 启用签名需同时设置：`STORYLENS_SIGN_UPDATER=1` 与 `TAURI_SIGNING_PRIVATE_KEY`（或 `TAURI_SIGNING_PRIVATE_KEY_PATH`）。
- 可选 Secret：`TAURI_UPDATER_PUBKEY`、`TAURI_SIGNING_PRIVATE_KEY_PASSWORD`。
- 开发环境默认关闭更新检查（`debug_assertions` 或 `STORYLENS_DISABLE_UPDATER=1`）。
- **不要**在交互式 shell 中留下 `TAURI_SIGNING_PRIVATE_KEY` 后直接构建，否则可能卡在密码提示。
