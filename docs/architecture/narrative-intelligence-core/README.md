# Narrative Intelligence Core

StoryLens 叙事智能核心文档索引。当前基线：`VERSION=1.0.5`。

## 阶段状态

| Phase | Change | 状态 | 说明 |
|-------|--------|------|------|
| Phase 1P | CHG-20260723-011 | tested | 并行 Contract / ORM 骨架 / Migration ID |
| Phase 1A Agent A | CHG-20260723-012 | tested | Snapshot / Hash / Migration 001–003 |
| Phase 1A Agent B | CHG-20260723-013 | tested | Run Scope / Stage / Migration 004–005 |
| Phase 1A Agent C | CHG-20260723-014 | tested | Pattern Map 技术草案 / Mock / 隔离原型 |
| Phase 1A Integration | CHG-20260723-015 | tested | 合并修正与交叉验证 |
| Phase 1B | — | 未开始 | 叙事资产底座；本阶段禁止启动 |

## Phase 1P Contract

- [phase1-parallel-contract.md](./phase1-parallel-contract.md)
- [phase1-migration-plan.md](./phase1-migration-plan.md)
- [phase1-parallel-file-ownership.md](./phase1-parallel-file-ownership.md)
- [phase1-contract-verification.md](./phase1-contract-verification.md)

## Agent A（Snapshot）

- [phase1a-migration-ledger-implementation.md](./phase1a-migration-ledger-implementation.md)
- [phase1a-snapshot-implementation.md](./phase1a-snapshot-implementation.md)
- [phase1a-snapshot-verification.md](./phase1a-snapshot-verification.md)

## Agent B（Run Stage）

- [phase1a-run-scope-implementation.md](./phase1a-run-scope-implementation.md)
- [phase1a-run-stage-implementation.md](./phase1a-run-stage-implementation.md)
- [phase1a-run-stage-verification.md](./phase1a-run-stage-verification.md)

## Agent C（Pattern Readiness）

- [phase0b-pattern-map-readiness.md](./phase0b-pattern-map-readiness.md)
- [phase1d-pattern-map-contract-draft.md](./phase1d-pattern-map-contract-draft.md)
- [phase1d-pattern-map-technology-options.md](./phase1d-pattern-map-technology-options.md)
- [phase1d-pattern-map-performance.md](./phase1d-pattern-map-performance.md)

## Integration（Phase 1A）

- [phase1a-integration-report.md](./phase1a-integration-report.md)
- [phase1a-integrated-migration-verification.md](./phase1a-integrated-migration-verification.md)
- [phase1a-snapshot-runstage-end-to-end.md](./phase1a-snapshot-runstage-end-to-end.md)
- [phase1a-known-limitations.md](./phase1a-known-limitations.md)

## 硬边界

- 不得开始 Phase 1B / 真实整书分析 / Neo4j / 向量库
- 不得修改 `VERSION`、Tag `v1.0.5`、`release/1.0.5` baseline
- Pattern Map DTO 仅为数据库设计输入，未映射 ORM，未接入正式路由
