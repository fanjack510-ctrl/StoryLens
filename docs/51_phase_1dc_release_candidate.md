# docs/51｜Phase 1D-C Certified Single-Chapter Release Candidate

**前置：** Phase 1D-B2 `REAL_CANARY_PASSED`（`phase-1db2-r13-20260719T022027Z`）  
**性质：** 认证封板 + 发布候选离线验证（默认零真实模型调用）

## 1D-B2 封板产物

- `audits/single-chapter-pipeline/phase-1db2-certification-manifest-v1.json`
- `audits/single-chapter-pipeline/phase-1db2-final-certification-report-v1.md`
- `audits/single-chapter-pipeline/phase-1db2-certified-file-hashes-v1.json`
- `audits/single-chapter-pipeline/phase-1db2-defect-closure-register-v1.json`
- `audits/single-chapter-pipeline/phase-1db2-to-1dc-handoff-v1.md`

## Certified Baseline v1.0

`audits/single-chapter-pipeline/certified-baseline-v1.0/`

分类：`FROZEN_CERTIFIED_*` / `CHANGEABLE_UI_SHELL` / `CHANGEABLE_CERTIFICATION_TOOLING`。  
门禁：`scripts/check_certified_baseline.py` → `CERTIFIED_BASELINE_PASS`。

## RC 隔离

- DB：`artifacts/release-candidate/storylens-rc-v1.sqlite3`
- Manifest：`audits/single-chapter-pipeline/release-candidate-v1-manifest.json`

禁止对 `data/storylens.db` 做破坏性测试。

## 范围

只做单章认证发布候选验证。不做多章比较、全书旅程、Pro/License/爱发电、自动路由。

## 运行

```powershell
.\.venv\Scripts\python.exe .\scripts\certification\seal_phase_1db2_and_prepare_1dc.py
.\.venv\Scripts\python.exe .\scripts\check_phase_1dc_release_candidate.py
```

## 结论枚举

- `PHASE_1D_C_RELEASE_CANDIDATE_READY`
- `PHASE_1D_C_NOT_READY`
