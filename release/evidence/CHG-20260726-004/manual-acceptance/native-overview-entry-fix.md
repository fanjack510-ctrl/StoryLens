# STEP 2.8-FIX-1 — Native Overview Book Entry Missing (P1)

```text
Problem：Windows RC 1.1.0-rc.1 书籍页只见「章节聚合洞察 Pro」，进入后为 Chapter Aggregation Insights（覆盖率 / MISSING_CHAPTER_ANALYSIS），而非「原生全书概览」。
RC1 Screenshot Observation：用户反馈可见入口仅为章节聚合洞察 Pro；未发现原生全书概览入口。
Acceptance Status (RC1)：BLOCKED
```

## Root Cause

```text
Situation B (primary)：PRO_NATIVE_OVERVIEW / VITE_PRO_NATIVE_OVERVIEW_ENABLED 在 RC1 GUI 构建与 Sidecar 启动中均为 false。
ProNativeOverviewEntry 在 flag off 时 return null，因此 Book Workspace 不渲染「原生全书概览」。
用户仅看到并列的 WholeBookInsightsEntry（章节聚合洞察 Pro），并误入该旧模块。

Contributing：
- G7 Smoke 验证了 Sidecar/API（含临时 env），未验证安装后 GUI 主页面入口在 flag 默认关闭时的可见性。
- Repository default false 正确；RC1 未提供可复现的 GUI 启用烘焙。
```

## Affected Files

```text
apps/desktop/src/components/proNativeOverview/ProNativeOverviewEntry.tsx (behavior unchanged; flag gate)
apps/desktop/src/services/proNativeOverviewFlag.ts
apps/desktop/vite.config.ts
apps/desktop/src/vite-env.d.ts
apps/desktop/src/pages/BookRoutePage.tsx (entry order: Native before Aggregation)
apps/desktop/src-tauri/src/backend.rs (RC version enables sidecar PRO_NATIVE_OVERVIEW_ENABLED)
scripts/build_windows_rc.ps1 (bake VITE flag; archive prior installers; default 1.1.0-rc.2)
apps/desktop/src/pages/proNativeOverview.test.tsx
apps/desktop/src/services/proNativeOverviewFlag.test.ts
```

## Fix

```text
1. RC build sets VITE_PRO_NATIVE_OVERVIEW_ENABLED=true for frontend bake (repo default remains false).
2. Vite define __STORYLENS_PRO_NATIVE_OVERVIEW_ENABLED__ from that env.
3. Tauri sidecar spawn sets PRO_NATIVE_OVERVIEW_ENABLED=true when app version contains "-rc".
4. Book toolbar order: 原生全书概览 (Free) then 章节聚合洞察 Pro.
5. Routes remain separate:
   Native → /books/:bookId/pro-native-overview
   Aggregation → /books/:bookId/whole-book-insights
6. Preserve RC1 installer under dist/release/archive/ (do not overwrite hash).
```

## Tests

```text
Frontend：
  proNativeOverview.test.tsx — dual entry, separate routes, Native before Aggregation, no Pro on Native
  proNativeOverviewApi.test.ts + proNativeOverviewFlag.test.ts
  typecheck OK

Backend：
  test_native_overview_free_entitlement.py — Free native + future Pro gate still licensed
  API / DB / Private Engine unchanged
```

## Routes

```text
NATIVE ROUTE：/books/:bookId/pro-native-overview
AGGREGATION ROUTE：/books/:bookId/whole-book-insights
```

## Feature Flag

```text
Repository Default：PRO_NATIVE_OVERVIEW_ENABLED=false (unchanged)
RC bake：VITE_PRO_NATIVE_OVERVIEW_ENABLED=true at RC build time
RC sidecar：auto-enable when package version contains -rc
User need not set system environment variables
```

## RC2 Build

```text
RC2 Version：1.1.0-rc.2
RC2 Installer：D:\Dstorylens-wt-narrative-phase2br1-integration\dist\release\StoryLens_1.1.0-rc.2_x64-setup.exe
RC2 SHA-256：F6156504CBCD24F417A629855E25699B897869F222CB9BE91C29F0F3241116D4
RC2 Size：42071169 bytes
Public HEAD at fix：9c1578014491699ec52f10ae4c274f74c3ca3c77
Build note：tauri/nsis OK; first collect hit file lock on storylens-api.exe; artifacts collected after process cleanup. Formal VERSION restored to 1.0.5.

RC1 Installer preserved：
  dist/release/archive/StoryLens_1.1.0-rc.1_x64-setup.exe
  (also retained under apps/desktop/src-tauri/target/release/bundle/nsis/)
  SHA-256：6873BC614558221CFD9E3D89B0DBCBB8028C5AA393C202F009D48945C0956013
  MATCH：YES
```

## Defects

```text
P0：none
P1：RC1 entry missing — FIXED in source; requires RC2 rebuild for acceptance
P2：none
```

## Governance

```text
DATABASE CHANGED：NO
API CHANGED：NO
PRIVATE ENGINE CHANGED：NO
Formal VERSION：1.0.5
CHG-003：tested
CHG-004：tested
verified：NO
Push / Tag / Release：NO
```
