# VERIFICATION — StoryLens 1.1.2 stable (CHG-20260731-027)

Date：2026-07-31  
Status：**tested**（自动门禁通过；本轮不 Push / Tag / GitHub Release）

## Preconditions

| Item | Result |
|------|--------|
| RC.7 Manual Gate | PASSED（MG-STORYLENS-1.1.2-RC.7-INSTALLED） |
| CHG-026 | verified |
| CHG-023 / CHG-025 | verified |
| VERSION | 1.1.2（无 rc/beta/preview） |
| RC.2–RC.7 archives | PRESERVED |
| RC.7 hash match | YES |

## Build

| Item | Value |
|------|--------|
| BUILD_EXIT | 0 |
| Installer | `dist/release/StoryLens_1.1.2_x64-setup.exe` |
| Size | 42773631 |
| SHA-256 | `F3DAF5AB0F8E6DFFCE89DAA055CD860D67206EF2A877C602D86987217A9E69AB` |
| Archive | `D:\StoryLens-Local-Evidence\installer-archive\StoryLens_1.1.2_x64-setup.exe` |
| Sidecar SHA-256 | `E847FAEAE6971542BB2894F745D62FD72D24C3C2E0FED661D28B427ED22C6D07` |
| Desktop SHA-256 | `DDA8CE50150D7DD4B461A585F11AAE864BACA464227418458319B9BC9E2F5EF7` |
| Desktop ProductVersion | 1.1.2 |
| Note | `STORYLENS_RC_CANDIDATE=1` 仅跳过未冻结 registry（同 V1.1.0 stable 模式）；产品版本仍为 1.1.2 |

## Automatic gates

| Gate | Result |
|------|--------|
| CWD | 6/6 |
| True packaged Sidecar Resume Success | PASS |
| True packaged Sidecar Resume Failure | PASS |
| Succeeded stale recovery（vitest CHG-023） | PASS |
| Right rail / Top CTA / destination match（Playwright CHG-025） | PASS |
| Main/Rail + ProgressCard absent（vitest） | PASS |
| Real / external provider | 0 |
| Formal DB writes | 0 |
| Formal install overwrite | NO |

## Next

`STORYLENS 1.1.2 STABLE INSTALLER DELIVERY`（人工交付；本轮不发布到 GitHub）
