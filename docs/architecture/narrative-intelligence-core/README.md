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
| Phase 1B Agent D | CHG-20260723-017 | verified | Entity / Alias |
| Phase 1B Agent E | CHG-20260723-018 | verified | Asset / Version / Evidence |
| Phase 1B Agent F | CHG-20260723-019 | verified | Relation / Evidence / Conflict |
| Phase 1B Integration | CHG-20260723-020 | verified | 006–010 联调 / Entity→Asset→Relation |
| Phase 1C-P | CHG-20260723-021 | verified | Engine / Capability / Quota Contract |
| Phase 1C Agent G | CHG-20260723-022 | verified | WholeBook Engine / Mock |
| Phase 1C Agent H | CHG-20260723-023 | verified | Backend Capability / License / Quota |
| Phase 1C Agent I | CHG-20260723-024 | verified | Frontend Capability Client |
| Phase 1C Integration | CHG-20260723-025 | verified | Engine + Capability e2e |
| Phase 1D-P | CHG-20260723-026 | verified | Product Contract freeze |
| Phase 1D Agent J | CHG-20260723-027 | verified | Preflight / Run UX |
| Phase 1D Agent K | CHG-20260723-028 | verified | Result DTO / Projection |
| Phase 1D Agent L | CHG-20260723-029 | verified | Evidence / Review / Map |
| Phase 1D Integration | CHG-20260723-030 | verified | Phase 1D Integration |
| Phase 2A-P | CHG-20260723-031 | tested | Mock Run Shell Contract freeze |
| Phase 2A Agent M | CHG-20260723-032 | registered | Backend Mock Run |
| Phase 2A Agent N | CHG-20260723-033 | registered | Frontend Mock Run Lab |
| Phase 2A Agent O | CHG-20260723-034 | registered | Recovery / Reliability |
| Phase 2A Integration | CHG-20260723-035 | registered | Phase 2A Integration |

\* 022–030 已为 `verified`（不得 ready/released）。031 上限 `tested`；032–035 保持 `registered`。硬边界见下。

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
- Phase 1C / 1D / 2A：`PRO_CAPABILITIES_SHIPPED=false`；`WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`；`PRODUCTION_DEFAULT_ENGINE_ID=None`
- Phase 1D：Preflight ≠ Run creation；Native/Enhanced 是模式不是产品；无 force-start；无 migrations / Pattern 表 / push / build / publish
- Phase 2A：`WHOLE_BOOK_MOCK_LAB_ENABLED` 默认 `false`；仅 Lab 路径；无真实 Engine/模型/Prompt；无 Celery/Redis/WebSocket；无新 Migration

## Phase 1C-P Contract

- [phase1c-engine-contract.md](./phase1c-engine-contract.md)
- [phase1c-stage-contract.md](./phase1c-stage-contract.md)
- [phase1c-capability-contract.md](./phase1c-capability-contract.md)
- [phase1c-quota-contract.md](./phase1c-quota-contract.md)
- [phase1c-engine-asset-boundary.md](./phase1c-engine-asset-boundary.md)
- [phase1c-frontend-capability-contract.md](./phase1c-frontend-capability-contract.md)
- [phase1c-api-contract.md](./phase1c-api-contract.md)
- [phase1c-migration-and-compatibility.md](./phase1c-migration-and-compatibility.md)
- [phase1c-parallel-file-ownership.md](./phase1c-parallel-file-ownership.md)
- [phase1c-parallel-file-ownership.json](./phase1c-parallel-file-ownership.json)
- [phase1c-contract-verification.md](./phase1c-contract-verification.md)

## Phase 1C Integration

- [phase1c-integration-report.md](./phase1c-integration-report.md)
- [phase1c-engine-capability-e2e.md](./phase1c-engine-capability-e2e.md)
- [phase1c-capability-api-verification.md](./phase1c-capability-api-verification.md)
- [phase1c-whole-book-preflight.md](./phase1c-whole-book-preflight.md)
- [phase1c-mock-production-isolation.md](./phase1c-mock-production-isolation.md)
- [phase1c-known-limitations.md](./phase1c-known-limitations.md)

## Phase 1D-P Product Contract

- [phase1d-product-flow.md](./phase1d-product-flow.md)
- [phase1d-preflight-page-contract.md](./phase1d-preflight-page-contract.md)
- [phase1d-run-progress-contract.md](./phase1d-run-progress-contract.md)
- [phase1d-result-information-architecture.md](./phase1d-result-information-architecture.md)
- [phase1d-result-envelope.md](./phase1d-result-envelope.md)
- [phase1d-module-result-contracts.md](./phase1d-module-result-contracts.md)
- [phase1d-evidence-review-contract.md](./phase1d-evidence-review-contract.md)
- [phase1d-conflict-center-contract.md](./phase1d-conflict-center-contract.md)
- [phase1d-structure-map-projection.md](./phase1d-structure-map-projection.md)
- [phase1d-api-contract.md](./phase1d-api-contract.md)
- [phase1d-release-scope.md](./phase1d-release-scope.md)
- [phase1d-parallel-file-ownership.md](./phase1d-parallel-file-ownership.md)
- [phase1d-parallel-file-ownership.json](./phase1d-parallel-file-ownership.json)
- [phase1d-contract-verification.md](./phase1d-contract-verification.md)

## Phase 1D Integration

- [phase1d-integration-report.md](./phase1d-integration-report.md)
- [phase1d-preflight-result-e2e.md](./phase1d-preflight-result-e2e.md)
- [phase1d-module-stage-dependency-boundary.md](./phase1d-module-stage-dependency-boundary.md)
- [phase1d-result-api-verification.md](./phase1d-result-api-verification.md)
- [phase1d-evidence-review-integration.md](./phase1d-evidence-review-integration.md)
- [phase1d-structure-map-integration.md](./phase1d-structure-map-integration.md)
- [phase1d-known-limitations.md](./phase1d-known-limitations.md)

## Agent J / K / L implementation notes

- Run UX: [phase1d-run-ux-implementation.md](./phase1d-run-ux-implementation.md)
- Result Projection: [phase1d-result-projection-implementation.md](./phase1d-result-projection-implementation.md)
- Review / Map: [phase1d-review-map-implementation.md](./phase1d-review-map-implementation.md)

## Phase 2A-P Mock Run Shell Contract

- [phase2a-run-shell-overview.md](./phase2a-run-shell-overview.md)
- [phase2a-mock-lab-security.md](./phase2a-mock-lab-security.md)
- [phase2a-run-creation-contract.md](./phase2a-run-creation-contract.md)
- [phase2a-run-state-machine.md](./phase2a-run-state-machine.md)
- [phase2a-stage-lifecycle.md](./phase2a-stage-lifecycle.md)
- [phase2a-mock-executor-contract.md](./phase2a-mock-executor-contract.md)
- [phase2a-task-registry-contract.md](./phase2a-task-registry-contract.md)
- [phase2a-mock-run-api.md](./phase2a-mock-run-api.md)
- [phase2a-frontend-lab-contract.md](./phase2a-frontend-lab-contract.md)
- [phase2a-polling-contract.md](./phase2a-polling-contract.md)
- [phase2a-partial-result-contract.md](./phase2a-partial-result-contract.md)
- [phase2a-run-actions-contract.md](./phase2a-run-actions-contract.md)
- [phase2a-idempotency-concurrency.md](./phase2a-idempotency-concurrency.md)
- [phase2a-recovery-contract.md](./phase2a-recovery-contract.md)
- [phase2a-mock-quota-budget.md](./phase2a-mock-quota-budget.md)
- [phase2a-error-contract.md](./phase2a-error-contract.md)
- [phase2a-audit-contract.md](./phase2a-audit-contract.md)
- [phase2a-parallel-file-ownership.md](./phase2a-parallel-file-ownership.md)
- [phase2a-parallel-file-ownership.json](./phase2a-parallel-file-ownership.json)
- [phase2a-contract-verification.md](./phase2a-contract-verification.md)
