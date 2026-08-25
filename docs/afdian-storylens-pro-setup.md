# 爱发电 StoryLens Pro 授权配置（V1 离线验签）

本文说明如何在爱发电售卖 **StoryLens Pro 1.x** 一次性虚拟商品，并用离线数字签名授权码完成交付。

## 边界（必须清楚）

1. 首版完全离线验签，不需要授权服务器。
2. 不收集用户邮箱。
3. 不限制设备数量。
4. 同一授权码被分享时，首版无法联网阻止。
5. 首版不能远程撤销退款订单。
6. 界面不得虚假显示「已绑定设备」或「已同步爱发电订单」。
7. 生产私钥只保存在仓库外的发行方密钥目录，永不进入 Git / ZIP / 安装包 / 前端 / 日志。
8. 正式运行模式（`browser_local_production`、Tauri 桌面、Windows 安装包）只信任生产公钥；测试公钥仅用于开发与 pytest。

## 公钥隔离

| 运行模式 | 加载配置 | 可接受 key |
|---|---|---|
| `browser_local_dev` / pytest | `tests/fixtures/license_public_keys.test.json` | `test-dev-001` 等 test 环境 key |
| `browser_local_production` / Tauri / 安装包 | `config/license_public_keys.production.json` | 仅 `environment=production` |

正式模式收到测试授权码时返回 `LICENSE_KEY_NOT_ALLOWED_IN_RUNTIME`，用户文案为「此授权码不能用于当前版本。」，不展示内部 key 名称。缺少生产公钥时显示「专业版授权功能尚未配置。」，不得回退到测试公钥。

## 1. 创建爱发电商品

建议名称：

`StoryLens Pro 1.x 专业版授权`

建议说明：

一次购买，永久使用 StoryLens 1.x 专业版功能。软件模型调用费用由用户自己的模型服务账户承担。

当前正式权益口径：

| 免费版保留 | StoryLens Pro 额外解锁 |
|---|---|
| 导入、阅读、章节识别、作品画像 | 从已完成全文拆文的小说提取分类素材 |
| 单章场景识别、人工调边界与章节分析 | 从已完成全文拆文的小说生成作品 Skill |
| 全书评测、拆文、读懂 | 榜单共性归纳 |
| 浏览知识库、关键词检索、HTML 导出 | 按意思找参考、结构化 PDF 导出 |

不得把尚需私有引擎的章节聚合洞察写进爱发电商品权益。

## 2. 生成生产密钥（仓库外）

**不要由自动化在仓库内生成生产私钥。** 发行方本机执行：

```powershell
python scripts/license/generate_keypair.py `
  --env production `
  --key-id storylens-pro-1-prod-001 `
  --private-key-output D:\StoryLens-License-Secrets\production\storylens-pro-1-prod-001.ed25519.priv.b64 `
  --public-key-output D:\StoryLens-License-Secrets\production\storylens-pro-1-prod-001.ed25519.pub.b64
```

然后人工将公钥内容写入：

`config/license_public_keys.production.json`

要求：

1. 私钥保存在项目目录外；
2. 至少一份加密离线备份；
3. 不进入 Git / ZIP / Windows 安装包 / 日志；
4. 不复制到爱发电后台；
5. 爱发电只接收最终授权码。

`private_release/` 仅可用于临时生成的待上传授权码与发行台账（已 gitignore），**不得**作为生产私钥长期保存位置。

## 3. 批量生成授权码

```powershell
python scripts/license/generate_licenses.py `
  --product storylens_pro `
  --major-version 1 `
  --count 100 `
  --key-id storylens-pro-1-prod-001 `
  --private-key-file D:\StoryLens-License-Secrets\production\storylens-pro-1-prod-001.ed25519.priv.b64 `
  --output D:\StoryLens-License-Releases\afdian_storylens_pro_1x_codes.txt `
  --ledger-output D:\StoryLens-License-Releases\afdian_storylens_pro_1x_ledger.csv
```

- 用户发放文件：一行一个授权码。
- 台账 CSV：仅发行方保存，不要上传到爱发电，不要提交 Git。
- 终端只打印路径与数量，不打印全部授权码，不打印私钥。

## 4. 导入爱发电自动发放

将 codes 文本导入爱发电「自动发放 / 随机回复」区域。

不要把同一批码重复上传。记录已上传数量与剩余数量。

## 5. 配置购买链接

在 `config/license_public_keys.production.json` 的 `commerce.afdian_product_url` 填入爱发电商品 HTTPS 地址。

未配置时，设置页「前往爱发电购买」会提示发行方完成配置，不展示空 URL。

## 6. 发行前检查

```powershell
python scripts/license/check_license_release_config.py
```

当前生产公钥尚未填入、商品 URL 未配置时，可用（仅验证脚本能力，不代表可发布）：

```powershell
python scripts/license/check_license_release_config.py --allow-pending-keys --allow-missing-commerce
```

## 7. 用户激活路径

1. 设置 → 授权与专业版 → 前往爱发电购买；
2. 用户从爱发电订单的自动发货内容复制 `SLP1-` 开头的授权码；
3. 返回设置页 → 我已有授权码 → 粘贴并激活专业版。

激活后立即刷新全局 entitlement，无需重启、无需强制刷新，也无需保持联网。

## 8. 人工联调清单

1. 使用测试 fixture / `test-dev-001` 在 `browser_local_dev` 或 pytest 验证。
2. 确认 `browser_local_production` / Tauri 拒绝测试码。
3. 确认爱发电自动发货库存充足，且每行只包含一个完整授权码。
4. 发行方在爱发电创建测试商品并自行完成测试购买后，用订单实际收到的生产码在正式模式激活。
5. 激活后验证五项 Pro 能力均可用；退出并重启应用后授权仍有效。

Cursor / 自动化不得登录爱发电账号或调用爱发电生产 API，也不得在仓库内生成生产私钥。
