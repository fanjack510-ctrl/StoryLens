# Narrative Intelligence Core

StoryLens 叙事智能核心文档索引。当前基线：`VERSION=1.0.5`。

## 阶段状态

| Phase | Change | 状态 | 说明 |
|-------|--------|------|------|
| Phase 1P | CHG-20260723-011 | verified | 并行 Contract / ORM 骨架 / Migration ID |
| Phase 1A Agent A | CHG-20260723-012 | verified | Snapshot / Hash / Migration 001–003 |
| Phase 1A Agent B | CHG-20260723-013 | verified | Run Scope / Stage / Migration 004–005 |
| Phase 1A Agent C | CHG-20260723-014 | verified | Pattern Map 技术草案 / Mock / 隔离原型 |
| Phase 1A Integration | CHG-20260723-015 | verified | 合并修正与交叉验证 |
| Phase 1B-P | CHG-20260723-016 | tested* | Asset Contract / ORM 骨架 / Migration 006–010 |
| Phase 1B Agent D | CHG-20260723-017 | registered | Entity / Alias |
| Phase 1B Agent E | CHG-20260723-018 | registered | Asset / Version / Evidence |
| Phase 1B Agent F | CHG-20260723-019 | registered | Relation / Evidence / Conflict |
| Phase 1B Integration | CHG-20260723-020 | registered | 006–010 联调 |

\* Phase 1B-P 状态上限为 `tested`（本阶段完成后）。

## Phase 1P / 1A

- [phase1-parallel-contract.md](./phase1-parallel-contract.md)
- [phase1-migration-plan.md](./phase1-migration-plan.md)
- [phase1-parallel-file-ownership.md](./phase1-parallel-file-ownership.md)
- [phase1-contract-verification.md](./phase1-contract-verification.md)
- [phase1a-integration-report.md](./phase1a-integration-report.md)
- [phase1a-known-limitations.md](./phase1a-known-limitations.md)

## Phase 1B-P Contract

- [phase1b-asset-contract.md](./phase1b-asset-contract.md)
- [phase1b-entity-alias-contract.md](./phase1b-entity-alias-contract.md)
- [phase1b-relation-contract.md](./phase1b-relation-contract.md)
- [phase1b-evidence-contract.md](./phase1b-evidence-contract.md)
- [phase1b-review-lock-versioning.md](./phase1b-review-lock-versioning.md)
- [phase1b-pattern-map-data-boundary.md](./phase1b-pattern-map-data-boundary.md)
- [phase1b-migration-plan.md](./phase1b-migration-plan.md)
- [phase1b-parallel-file-ownership.md](./phase1b-parallel-file-ownership.md)
- [phase1b-parallel-file-ownership.json](./phase1b-parallel-file-ownership.json)
- [phase1b-contract-verification.md](./phase1b-contract-verification.md)

## Agent C（Pattern Readiness）

- [phase0b-pattern-map-readiness.md](./phase0b-pattern-map-readiness.md)
- [phase1d-pattern-map-contract-draft.md](./phase1d-pattern-map-contract-draft.md)

## 硬边界

- 不得实现真实整书分析 / 模型调用 / 双写 / 历史回填
- 不得建立 Narrative Pattern 数据表或接入正式路由
- 不得修改 `VERSION`、Tag `v1.0.5`、`release/1.0.5` baseline
- Agents D/E/F 不得修改 `models.py` 表结构；统一从 Phase 1B-P HEAD 派生分支
