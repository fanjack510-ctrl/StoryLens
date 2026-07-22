# 爱发电 StoryLens Pro 授权配置（V1 离线验签）

本文说明如何在爱发电售卖 **StoryLens Pro 1.x** 一次性虚拟商品，并用离线数字签名授权码完成交付。

## 边界（必须清楚）

1. 首版完全离线验签，不需要授权服务器。
2. 不收集用户邮箱。
3. 不限制设备数量。
4. 同一授权码被分享时，首版无法联网阻止。
5. 首版不能远程撤销退款订单。
6. 界面不得虚假显示「已绑定设备」或「已同步爱发电订单」。
7. 私钥只保存在发行方本机 `private_release/`，永不进入 Git / 安装包 / 前端。

## 1. 创建爱发电商品

建议名称：

`StoryLens Pro 1.x 专业版授权`

建议说明：

一次购买，永久使用 StoryLens 1.x 专业版功能。软件模型调用费用由用户自己的模型服务账户承担。

## 2. 生成密钥

```powershell
cd D:\Dstorylens-wt-ui-polish
python scripts/license/generate_keypair.py --env production --key-id prod-2026-01
```

- 私钥：`private_release/license_keys/<key_id>.ed25519.priv.b64`（备份到离线介质）
- 公钥：写入 `config/license_public_keys.json`

## 3. 批量生成授权码

```powershell
python scripts/license/generate_licenses.py `
  --product storylens_pro `
  --major-version 1 `
  --count 100 `
  --key-id prod-2026-01 `
  --private-key-file private_release/license_keys/prod-2026-01.ed25519.priv.b64 `
  --output private_release/afdian_storylens_pro_1x_codes.txt `
  --ledger private_release/afdian_storylens_pro_1x_ledger.csv
```

- 用户发放文件：一行一个授权码。
- 台账 CSV：仅发行方保存，不要上传到爱发电。

## 4. 导入爱发电自动发放

将 `afdian_storylens_pro_1x_codes.txt` 导入爱发电「自动发放 / 随机回复」区域。

不要把同一批码重复上传。记录已上传数量与剩余数量。

## 5. 配置购买链接

在 `config/license_public_keys.json` 的 `commerce.afdian_product_url` 填入爱发电商品 HTTPS 地址。

未配置时，设置页「购买专业版」会提示发行方完成配置，不展示空 URL。

## 6. 用户激活路径

设置 → 授权与专业版 → 输入授权码 → 激活专业版。

## 7. 人工联调清单

1. 生成测试密钥与 5 个测试码。
2. 在 StoryLens 激活第一个码，确认成功。
3. 刷新 / 重启网页版与桌面版，确认同一 `%LOCALAPPDATA%\StoryLens` 下 Pro 状态保持。
4. 篡改授权码一个字符 → 签名失败。
5. 错误 major_version → 版本不兼容。
6. 重复激活同一码 → 幂等。
7. 用户在爱发电创建测试商品并自行完成测试购买后，将发放码粘贴到 StoryLens，确认激活。

Cursor / 自动化不得登录爱发电账号或调用爱发电生产 API。
