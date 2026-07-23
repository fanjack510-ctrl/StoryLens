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
| Phase 1B-P | CHG-20260723-016 | verified | Asset Contract / ORM 骨架 / Migration 006–010 |
| Phase 1B Agent D | CHG-20260723-017 | tested | Entity / Alias |
| Phase 1B Agent E | CHG-20260723-018 | tested | Asset / Version / Evidence |
| Phase 1B Agent F | CHG-20260723-019 | tested | Relation / Evidence / Conflict |
| Phase 1B Integration | CHG-20260723-020 | tested* | 006–010 联调 / Entity→Asset→Relation |

\* Phase 1B Integration 状态上限为 `tested`（不得 ready/released）。Phase 1B-P（016）已 `verified`。

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

## Phase 1B Integration

- [phase1b-integration-report.md](./phase1b-integration-report.md)
- [phase1b-integrated-migration-verification.md](./phase1b-integrated-migration-verification.md)
- [phase1b-entity-asset-relation-e2e.md](./phase1b-entity-asset-relation-e2e.md)
- [phase1b-canonical-lock-conflict.md](./phase1b-canonical-lock-conflict.md)
- [phase1b-known-limitations.md](./phase1b-known-limitations.md)

## Agent C（Pattern Readiness）

- [phase0b-pattern-map-readiness.md](./phase0b-pattern-map-readiness.md)
- [phase1d-pattern-map-contract-draft.md](./phase1d-pattern-map-contract-draft.md)

## 硬边界

- 不得实现真实整书分析 / 模型调用 / 双写 / 历史回填
- 不得建立 Narrative Pattern 数据表或接入正式路由
- 不得修改 `VERSION`、Tag `v1.0.5`、`release/1.0.5` baseline
- Integration **可**修订未发布的 migration 006（含 `superseded_by_entity_id`）及对应 ORM；Agents D/E/F 日常不得擅自改 `models.py` 表结构
