# VERIFICATION — StoryLens 1.1.2-rc.7 (CHG-20260731-026)

Date：2026-07-31  
Status：**tested**（自动门禁通过；仍待人工真正安装态验收）  
不得标记：verified / ready / released

## Source

| Item | Value |
|------|--------|
| PUBLIC BUILD SOURCE HEAD | `5148fb7861bf21dcfb6d55de6419fe391a32561c` |
| PUBLIC FINAL HEAD | `5148fb7861bf21dcfb6d55de6419fe391a32561c`（证据提交前；提交后 tip 前进） |
| CHG-023 VERIFIED HEAD | `bfb9b9ad787b260a8b813f8b35a7612b075d0330` |
| CHG-025 VERIFIED HEAD | `ba9521f0069b6515551aaf005cc139a47355c926` |
| VERSION DURING BUILD | `1.1.2-rc.7` |
| VERSION AFTER BUILD | `1.1.2` |

## Installer

| Item | Value |
|------|--------|
| Path | `dist/release/StoryLens_1.1.2-rc.7_x64-setup.exe` |
| Size | 42776408 |
| SHA-256 | `9831A4821CADFF90665CCFDEB73A244A3C71595882F73C6EBAF9CADD37D50FB9` |
| Archive | `D:\StoryLens-Local-Evidence\installer-archive\StoryLens_1.1.2-rc.7_x64-setup.exe` |
| Archive hash match | YES |
| Sidecar SHA-256 | `5F196E6E077247CA471D77428398A054A82219709566487FE361E30859A2B023` |
| Desktop SHA-256 | `719E2471B84FAA44B48DB130F752A6748C1B90E525550A476AEBD8242FC25148` |
| RC.2–RC.6 preserved | YES |
| RC.6 hash match | YES |

## Automatic gates

| Gate | Result |
|------|--------|
| Prebuild | PASS |
| BUILD_EXIT | 0 |
| CWD | 6/6 |
| pytest regression | 45 passed |
| vitest (023/025/017) | 29 passed |
| Playwright CHG-023 A–D + restart | PASS（built frontend + MG launcher；非安装态） |
| Playwright CHG-025 E–G | PASS |
| Isolated installed acceptance | PASS |
| True packaged Sidecar resume A/B | PASS（`storylens-api.exe` + 外置 Mock `127.0.0.1:18170`） |
| SOURCE PYTHON API（true installed） | NO |
| Formal DB writes | 0 |
| Formal install overwrite | NO |
| Real / external provider | 0 |

## True packaged Sidecar notes

- API process path：`%TEMP%\storylens-1.1.2-rc.7-installed-automatic\install\storylens-api.exe`
- API SHA-256 与构建报告一致
- Resume success → `succeeded` + result；Resume failure → `failed` + no result
- 每场景 Resume Request=1；Analysis Recover=0
- Desktop UI 自动跳转结果 / 右侧 CTA 人工安装态验收仍待执行（自动门禁已覆盖 Playwright + Sidecar HTTP）

## Next

`STORYLENS 1.1.2-RC.7 MANUAL INSTALLED ACCEPTANCE`

No Push / Tag / Release / Stable 1.1.2.
