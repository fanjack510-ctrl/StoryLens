# Updater 通道（staging / stable）

StoryLens 桌面更新使用**两套独立 manifest**，共享同一 updater 公钥（不得重新生成）。

## 通道

| 通道 | 用途 | Manifest |
|------|------|----------|
| `stable` | 普通安装版默认 | `https://github.com/fanjack510-ctrl/StoryLens/releases/latest/download/latest.json` |
| `staging` | 仅内部测试 | `https://github.com/fanjack510-ctrl/StoryLens/releases/download/staging/latest.json` |

## 客户端策略

- `automatic_check = true`
- `automatic_download = false`
- `automatic_install = false`
- 普通用户只使用 `stable`，设置页不展示 staging
- 内部测试模式 / 开发者模式才可选择 staging
- 环境变量 `STORYLENS_UPDATE_CHANNEL=staging|stable` 可覆盖（优先于配置文件）

## 发布流程

1. 构建并签名同一套产物
2. **先**上传到 staging（`staging` release 资产 / `latest.json`）
3. 内部验证 opt-in 下载与安装
4. 验证通过后，将**同一套**签名产物提升到 stable（`latest.json`）
5. 禁止用开发环境直接改写正式 stable `latest.json`

## 模板

- 共用：`packaging/updater/latest.json.template`
- 通道差异仅在部署目标 URL，不更换公钥
