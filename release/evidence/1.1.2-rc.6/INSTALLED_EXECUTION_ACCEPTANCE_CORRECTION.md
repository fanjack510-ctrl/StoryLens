# INSTALLED EXECUTION ACCEPTANCE CORRECTION — CHG-20260731-024 / 1.1.2-rc.6

Date: 2026-07-31  
Related audit: `D:\StoryLens-Local-Evidence\1.1.2-rc.6-manual-installed-mg\resume-success-failure-audit\`

## Purpose

纠正 CHG-024 / RC.6 构建与自动门禁报告中，对「安装态 Journey 执行」的过宽表述。  
**不修改**原始 `VERIFICATION.md` / `TEST_RESULTS.json` 正文；以本文件为追加更正。

## Corrections

### 1. Automatic Resume Success / Failure

下列自动结果实际执行面为：

- TEMP `launch_api_accept.py`
- 源码树 Python / uvicorn API（integration worktree）
- `STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE=1` + Journey Fake Mode
- CHG-023 风格 Seed（段落 ID 形如 `B0231-C0001-P####`，可被 Fake 正则解析）

**不是** RC.6 打包 Sidecar（`storylens-api.exe`）上的 Journey Worker 完整执行。

### 2. Packaged Sidecar — what WAS verified

安装态打包 Sidecar 在 RC.6 自动门禁中仅证明：

- 进程启动
- `/health`
- CWD 独立性（6/6）
- 打包资源配置加载
- 基础连接 / 隔离库写入门禁（Formal DB writes = 0）

### 3. Must NOT remain labeled as installed-execution verified

以下条目**不得**再被引用为「安装态已验证」：

| Item | Prior claim | Corrected status |
|------|-------------|------------------|
| Resume Success Auto Result | PASS (installed) | PASS only on TEMP/source API + Fake；**未**在打包 Sidecar 验证 |
| Resume Failure Presentation | PASS (installed) | UI/终端展示可在 TEMP API 复现；**未**在打包 Sidecar Worker 验证 |
| Journey Worker 完整执行 | implied | **未验证**（打包 Sidecar） |

### 4. Fixture A manual failure (retained)

人工 MG 首次 Resume Success 失败根因已审计为：

`INVALID_SUCCESS_FIXTURE`（Seed `B0RC6A-…` 与 Fake 正则不兼容）  
产品缺陷：NO；CHG-023 终态展示：PASS  

证据保留于 `resume-success-failure-audit\`。

### 5. Release train

RC.6 INSTALLED ACCEPTANCE：`BLOCKED / NOT COMPLETED` until true packaged-Sidecar execution gate passes.
