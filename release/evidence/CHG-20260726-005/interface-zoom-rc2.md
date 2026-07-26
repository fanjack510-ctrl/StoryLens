# CHG-20260726-005 — Global interface zoom (STEP 2.8-FIX)

```text
Status：implemented (not verified)
Target：StoryLens 1.1.0-rc.2
Formal VERSION：1.0.5
```

## Implementation

```text
ZOOM IMPLEMENTATION：TAURI_WEBVIEW (primary) / CSS_ZOOM (fallback + early bootstrap)
SETTING KEY：storylens.appearance.interfaceZoom
ZOOM LEVELS：80 / 90 / 100 / 110 / 125 / 150
DEFAULT：100
SHORTCUTS：Ctrl+Plus / Ctrl+= / Ctrl+- / Ctrl+0
```

Primary apply path: `@tauri-apps/api` `getCurrentWebview().setZoom(factor)`.
Permission: `core:webview:allow-set-webview-zoom` in desktop capabilities.
Early CSS zoom in `apps/desktop/index.html` to reduce flash before React/Tauri apply.
Reading `正文字号` / line-height remain independent.

## Local verification

```text
vitest interfaceZoom.test.ts + SettingsAppearanceZoom.test.tsx：10 passed
desktop typecheck：pass
git diff --check：pass
Production / RC build：pass (1.1.0-rc.2)
DATABASE / MIGRATION / PRIVATE ENGINE / API：unchanged for this change
```

## RC2 candidate (includes zoom + native entry FIX-1)

```text
Installer：D:\Dstorylens-wt-narrative-phase2br1-integration\dist\release\StoryLens_1.1.0-rc.2_x64-setup.exe
SHA-256：467373BCDCB6B0E9E998DC6C32186883F43AA7B678C74DE5489F1FFA99DEC635
Size：42072681
Public HEAD：6bf5fbc12b06a80a42ea8381096b2aadc126b1eb
Private HEAD：48072775773a09f4dc849096ba314e4fa0487c58
Primary feature commit：a61974bd4b2fc71c2cdcc471dde56b92884a3699
```

Prior RC2 (entry-fix only) archived under `dist/release/archive/` before rebuild.

## Manual acceptance (user)

```text
Spot-check：80% / 100% / 125% / 150%
Ctrl + / Ctrl - / Ctrl 0
Restart restore
正文字号 still independent
Dialog / menu / charts / Reader Journey / Aggregation / Native Overview
```

```text
User Explicit Approval：NO
Allow verified：NO
```
