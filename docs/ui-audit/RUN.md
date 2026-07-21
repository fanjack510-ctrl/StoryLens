# StoryLens UI Audit 运行说明（0.1.0）

## 目标产物

`artifacts/StoryLens_UI_Audit_0.1.0.zip`

内含：截图、页面清单、截图清单、HTML 联系表、覆盖报告、界面清单副本、本说明。

## 一键运行

```powershell
cd D:\Dstorylens-wt-ui-audit
.\scripts\ui-audit\run-ui-audit.ps1
```

## 分步

```powershell
cd D:\Dstorylens-wt-ui-audit\apps\desktop
npm install
npx playwright install msedge
npx playwright test --config playwright.ui-audit.config.ts
cd ..\..
node scripts\ui-audit\pack-ui-audit.mjs
```

## 环境约定

| 项 | 值 |
|---|---|
| viewport | 1440 × 900 |
| deviceScaleFactor | 1 |
| locale | zh-CN |
| timezone | Asia/Shanghai |
| theme（主截图） | light |
| 数据 | 确定性 Mock，无真实用户数据 |

## 约束

- 不调用真实阿里云；API Key 仅出现在 password 遮罩输入中。
- 导入样本为 `e2e/ui-audit/fixtures/` 虚构文本。
- 产品未实现的界面记入覆盖报告 `not_implemented`，不伪造产品截图。
