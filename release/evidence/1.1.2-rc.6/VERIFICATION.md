# VERIFICATION — StoryLens 1.1.2-rc.6 (CHG-20260731-024)

Status：**tested**（自动门禁通过；仍需用户手动安装态验收）

## Auto gates

| Gate | Result |
|------|--------|
| CWD GATE | 6/6 |
| SCENE WAIT GATE (CHG-015 pytest) | PASS |
| JOURNEY START COUNT (wait then start) | Scene incomplete → start blocked with WAITING_SCENE_ANALYSIS；complete path covered by CHG-015 |
| SUCCEEDED STALE RECOVERY | PASS (Playwright Case C + vitest) |
| RESUME SUCCESS AUTO RESULT | PASS (Playwright Case B / user A) |
| RESUME FAILURE PRESENTATION | PASS (Playwright Case A / user B) |
| RESUME REQUEST COUNT | 1 |
| ANALYSIS RECOVER REQUEST COUNT | 0 |
| DUPLICATE TASKS / STARTUP INTENTS | 0 |
| NEW ANALYSIS / JOURNEY RUNS on resume | 0 |
| PROGRESS CARD ON FAILED / SUCCEEDED | ABSENT |
| MAIN / RAIL CONSISTENCY | PASS |
| API RESTART | PASS (Case G) |
| PLAYWRIGHT A–G | PASS |
| INSTALLED AUTOMATIC ACCEPTANCE | PASS |
| PRODUCTION SCENARIO HOOK | ABSENT |
| REAL PROVIDER CALLS | 0 |
| FORMAL DATABASE WRITES | 0 |
| FORMAL INSTALL OVERWRITTEN | NO |

## Local evidence root

`D:\StoryLens-Local-Evidence\1.1.2-rc.6-20260731\`

- `CWD_INDEPENDENCE.json`
- `INSTALL_STATE_SUMMARY.json`
- `ISOLATED_INSTALLED_ACCEPTANCE.json`

## Isolated install

| Field | Value |
|-------|-------|
| Desktop Version | 1.1.2-rc.6 |
| Desktop Path | `%TEMP%\storylens-1.1.2-rc.6-installed-automatic\install\storylens-desktop.exe` |
| Sidecar Path | `%TEMP%\storylens-1.1.2-rc.6-installed-automatic\install\storylens-api.exe` |
| API Health | PASS |
| Listen | 127.0.0.1 |

## Next

STORYLENS 1.1.2-RC.6 MANUAL INSTALLED ACCEPTANCE
