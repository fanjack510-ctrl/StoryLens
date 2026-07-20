# StoryLens VIP 授权方案（客户端基础阶段）

状态：客户端基础已落地，真实收款 / 远程验签未接通
分支意图：`feature/vip-license-foundation`
日期：2026-07-20

## 1. 商业流程（目标形态）

```text
GitHub 下载 StoryLens
  → 爱发电购买 VIP
  → 爱发电自动发送激活码
  → 用户在 StoryLens 输入激活码
  → 授权服务验证
  → 本地保存签名授权
```

本阶段**不**接真实爱发电、**不**接支付、**不**开发真实授权服务器、**不**限制当前已有功能。

## 2. 职责边界

| 角色 | 职责 | 不做 |
|------|------|------|
| 爱发电 | 收款；第一阶段用预生成激活码；自动随机回复发码 | 不托管小说正文；不做 StoryLens 商城站 |
| StoryLens 客户端 | 输入激活码、调用最小授权 API、本地保存签名授权、功能门禁 | 不存签名私钥；不存 API Key；不存小说正文 |
| 授权服务（未来独立部署） | `activate` / `refresh` / `deactivate` / `status`；验签与设备绑定 | 不接收小说正文；不进开源仓私钥与激活码库 |

原则：

- **不建设独立商城网站**；购买入口走爱发电。
- 后续可接爱发电 API / Webhook，把「发码」从随机回复升级为订单联动。
- **激活码数据库与签名私钥不进开源仓**。
- **永久授权不默认承诺未来云端算力**（算力仍由用户自备 Key / 自有配额承担）。

## 3. 客户端状态模型

| 状态 | 含义 |
|------|------|
| `FREE` | 默认免费版 |
| `VIP_ACTIVE` | VIP 有效 |
| `VIP_EXPIRED` | 已过期 |
| `VIP_OFFLINE_GRACE` | 离线宽限（曾验证成功，暂无法刷新） |
| `VIP_INVALID` | 签名或载荷无效 |

授权信息字段：`license_id`、`plan`、`issued_at`、`expires_at`、`device_limit`、`features`、`last_verified_at`、`signature`。

## 4. 统一客户端接口

```ts
activateLicense(code)
refreshLicense()
deactivateLicense()
getLicenseStatus()
hasFeature(featureKey)
```

本阶段实现为 **DEV Mock**（源码中明确标记 `DEV_MOCK_LICENSE_SERVICE`），不得伪装成真实付费授权。Mock 激活仅在开发模式可用；正式包展示「即将开放」。

## 5. 本地授权文件

预留路径（Windows）：

```text
%LOCALAPPDATA%/StoryLens/license/storylens.license
```

要求：

- 不放安装目录；软件升级时保留；不进入 Git
- 不保存 API Key；不保存小说内容
- 客户端不保存签名私钥；未来只保存验证公钥
- 当前前端无法直接安全写入该目录时，使用存储抽象 + Mock（`localStorage` / memory），**不得绕过 Tauri 安全边界**

## 6. 功能门禁

统一通过 `hasFeature(featureKey)`，禁止页面散落 `if (isVip)`。

已登记功能键（本阶段均为未启用或免费策略，**不锁定**现有 Community 功能）：

- `batch_analysis`
- `novel_rhythm_map`
- `character_arc`
- `foreshadow_tracking`
- `novel_comparison`
- `advanced_report`
- `inspiration_center`

## 7. 未来授权服务契约（预留，未实现网络）

| 方法 | 路径 | 请求要点 | 响应要点 |
|------|------|----------|----------|
| POST | `/license/activate` | `code`, `device_id`, `app_version?` | `status`, `license` |
| POST | `/license/refresh` | `license_id`, `device_id`, `signature` | `status`, `license` |
| POST | `/license/deactivate` | `license_id`, `device_id`, `signature` | `{ status: "FREE", ok: true }` |
| GET | `/license/status` | `license_id`, `device_id` | `status`, `license \| null` |

类型定义见 `apps/desktop/src/services/license/types.ts`。

## 8. 爱发电第一阶段操作建议

1. 在爱发电创建 VIP 方案（月 / 年等），文案写清「激活码发货、本机授权、不承诺云端算力」。
2. 预生成一批激活码，存于**私有**发码库（不进 Git）。
3. 爱发电「自动回复」配置为随机/顺序发送未使用激活码。
4. 用户在 StoryLens 设置中的授权卡片输入激活码（卡片组件：`LicenseSettingsCard`；本阶段未挂到 `SettingsPage`）。
5. 后续若爱发电开放订单 Webhook，再把「随机回码」升级为「订单号 ↔ 激活码」绑定。

## 9. 安全与隐私

- 授权服务与客户端日志不得记录小说正文。
- API Key 仍只走现有凭据通道，与 license 文件隔离。
- 开源仓可含验证公钥与客户端验签逻辑；私钥与激活码库存私有运维侧。

## 10. 代码位置

- `apps/desktop/src/services/license/`
- `apps/desktop/src/stores/license/`
- `apps/desktop/src/components/settings/LicenseSettingsCard.tsx`
