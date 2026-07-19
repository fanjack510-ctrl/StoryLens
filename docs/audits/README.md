# Audits index

StoryLens 审计产物分布在仓库根目录 `audits/` 与本目录索引中。

## V1.0 Baseline（开源前技术基线）

| 项 | 路径 |
|----|------|
| Manifest | [`audits/v1.0-baseline/baseline-manifest.json`](../../audits/v1.0-baseline/baseline-manifest.json) |
| File tree | [`audits/v1.0-baseline/current-file-tree.txt`](../../audits/v1.0-baseline/current-file-tree.txt) |
| Dependencies | [`audits/v1.0-baseline/dependency-lock.txt`](../../audits/v1.0-baseline/dependency-lock.txt) |
| DB schema | [`audits/v1.0-baseline/database-schema.md`](../../audits/v1.0-baseline/database-schema.md) |
| API registry | [`audits/v1.0-baseline/api-registry.md`](../../audits/v1.0-baseline/api-registry.md) |
| Architecture docs | [`docs/architecture/`](../architecture/) |
| Release notes | [`docs/release/v1.0-baseline-notes.md`](../release/v1.0-baseline-notes.md) |
| Git tag | `storylens-v1.0-baseline` |

**规则：** 后续所有优化必须以该 Baseline 为对照；变更需说明相对 Baseline 的动机与回滚方式。

## 既有 V1.0 RC 审计

见 [`audits/v1.0/`](../../audits/v1.0/)（feature scope、defect register、certified hashes、SBOM、readiness report 等）。
