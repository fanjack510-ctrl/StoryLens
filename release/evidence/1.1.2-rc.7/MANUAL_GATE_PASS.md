# MANUAL GATE PASS — MG-STORYLENS-1.1.2-RC.7-INSTALLED

Date：2026-07-31  
Gate：`MG-STORYLENS-1.1.2-RC.7-INSTALLED`  
Result：**PASSED**  
Change：CHG-20260731-026  
RC：1.1.2-rc.7

## Installer

| Item | Value |
|------|--------|
| Path | `dist/release/StoryLens_1.1.2-rc.7_x64-setup.exe` |
| SHA-256 | `9831A4821CADFF90665CCFDEB73A244A3C71595882F73C6EBAF9CADD37D50FB9` |
| Build source HEAD | `5148fb7861bf21dcfb6d55de6419fe391a32561c` |

## Runtime surface

- Packaged Desktop：`storylens-desktop.exe`（SHA `719E2471…`）
- Packaged Sidecar：`storylens-api.exe`（SHA `5F196E6E…`）
- Isolated DATA_DIR：`%TEMP%\storylens-1.1.2-rc.7-installed-automatic\AppData\StoryLens-true-exec`
- External Mock：`127.0.0.1` only
- SOURCE PYTHON API：NO
- Vite / 源码 API：未用于最终验收

## Passed checks

| Check | Result |
|-------|--------|
| Resume Success | PASS |
| Resume Failure | PASS |
| succeeded 覆盖旧 recovery | PASS |
| Normal Flow | PASS |
| 右侧「查看阅读旅程」 | PASS |
| 顶部「阅读旅程」 | PASS |
| 两个入口结果一致 | PASS |
| Desktop / Sidecar 真安装态 | PASS |
| Real Provider Calls | 0 |
| Formal Database Writes | 0 |
| Formal Install Overwritten | NO |

## Outcome

RC.7 最终安装态人工验收通过。CHG-20260731-026 可标记 **verified**。  
允许进入 StoryLens **1.1.2** 正式稳定版安装包构建（CHG-20260731-027）。
