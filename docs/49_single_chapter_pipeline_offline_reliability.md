# docs/49｜Single-Chapter Journey Pipeline Offline Reliability（Phase 1D-B1）

**性质：** 认证（非功能开发）  
**模型请求：** 必须为 0  
**前置：** Reader Journey UI Final Freeze v2.7 + Single-Chapter Template Governance v2.7

## 1. 目标

离线证明单章节从导入到 Template v2.7 渲染的工程链路可靠：完整性、原子性、幂等性、故障可见性、模板渲染与 E2E 稳定性。

本阶段**不**调用真实模型，**不**修改冻结生产文件，**不**在认证中直接修复核心缺陷（仅 Defect Report）。

## 2. 独立认证环境

| 项 | 路径 |
|----|------|
| 认证目录 | `artifacts/single-chapter-pipeline-certification/` |
| 认证 SQLite | `.../certification.sqlite3` |
| 主库快照 | `main_db_before.json` / `main_db_after.json` |
| 审计报告 | `audits/single-chapter-pipeline/` |

主库 `data/storylens.db` 只读比对 SHA/mtime/Run 计数；认证写入不得进入主库。

## 3. 流水线地图

见 `audits/single-chapter-pipeline/pipeline-map-v1.json`。

要点：Reader Journey **不会**在 AnalysisRun.succeeded 后自动启动；必须由用户触发 `POST .../reader-journey`。

## 4. 离线回放入口

```powershell
.\.venv\Scripts\python.exe .\scripts\run_single_chapter_pipeline_certification.py
```

使用 `FakeProvider` 走生产解析/校验/持久化路径（零 HTTP）。

## 5. 门禁

```powershell
.\.venv\Scripts\python.exe .\scripts\check_single_chapter_pipeline_reliability.py
.\.venv\Scripts\python.exe .\scripts\run_e2e_stability_triple.py
```

E2E 必须连续 3 次完整 `npm run test:e2e` 全部通过。

认证脚本 `scripts/run_e2e_stability_triple.py` 在每次运行前清理本仓库占用的 `:1421`，并以 `--workers=1` 执行完整套件（不挑用例重跑），用于隔离默认并行下的 Run #55 争用抖动。

## 6. Phase 1D-B2 Canary

计划见 `audits/single-chapter-pipeline/real-canary-preflight-v1.json`。

- 6 章 + 2 次重复分析 = **8 次完整流水线**
- `max_cost` **未配置时拒绝启动**
- **无操作者明确批准不得开始真实调用**

## 7. 结论枚举

只允许：

- `ENGINEERING_READY_FOR_REAL_CANARY`
- `ENGINEERING_BLOCKED`

不得输出 `PRODUCTION_CERTIFIED`。

## 8. Phase 1D-B1 最终结论（本轮）

**ENGINEERING_VERDICT:** `ENGINEERING_READY_FOR_REAL_CANARY`  
**CANARY_START_ALLOWED:** `false`（`max_cost` 未配置；无操作者批准）

详见 `audits/single-chapter-pipeline/phase-1db1-final-verdict-v1.json`。
