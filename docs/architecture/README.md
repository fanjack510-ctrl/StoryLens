# Architecture documentation index

V1.0 Baseline technical architecture set. **Subsequent optimizations must reference this baseline.**

| Doc | Title |
|-----|-------|
| [01-product-overview.md](./01-product-overview.md) | 产品定位与能力 |
| [02-system-architecture.md](./02-system-architecture.md) | 系统架构与数据流 |
| [03-frontend-architecture.md](./03-frontend-architecture.md) | 前端架构 |
| [04-backend-architecture.md](./04-backend-architecture.md) | 后端架构 |
| [05-ai-pipeline.md](./05-ai-pipeline.md) | AI 分析流水线 |
| [06-database-design.md](./06-database-design.md) | 数据库设计 |
| [07-api-reference.md](./07-api-reference.md) | API 清单 |
| [08-feature-matrix.md](./08-feature-matrix.md) | 功能矩阵 |
| [09-known-issues.md](./09-known-issues.md) | 已知问题 |
| [10-open-source-checklist.md](./10-open-source-checklist.md) | 开源检查清单 |

Related: [docs/audits](../audits/), [docs/release/v1.0-baseline-notes.md](../release/v1.0-baseline-notes.md), tag `storylens-v1.0-baseline`.

## Narrative Intelligence Core

| Doc | Title |
|-----|-------|
| [narrative-intelligence-core/phase1-parallel-contract.md](./narrative-intelligence-core/phase1-parallel-contract.md) | Phase 1P 并行 Contract 冻结 |
| [narrative-intelligence-core/phase1-migration-plan.md](./narrative-intelligence-core/phase1-migration-plan.md) | Migration 编号与顺序 |
| [narrative-intelligence-core/phase1-parallel-file-ownership.md](./narrative-intelligence-core/phase1-parallel-file-ownership.md) | 文件所有权 |
| [narrative-intelligence-core/phase1-parallel-file-ownership.json](./narrative-intelligence-core/phase1-parallel-file-ownership.json) | 文件所有权（机器可读） |
| [narrative-intelligence-core/phase1-contract-verification.md](./narrative-intelligence-core/phase1-contract-verification.md) | Phase 1P 验证记录 |
| [narrative-intelligence-core/phase2b-private-engine-boundary.md](./narrative-intelligence-core/phase2b-private-engine-boundary.md) | Phase 2B-P Public/Private/Provider 边界 |
| [narrative-intelligence-core/phase2b-engine-manifest-loader.md](./narrative-intelligence-core/phase2b-engine-manifest-loader.md) | Phase 2B-P Manifest / Loader |
| [narrative-intelligence-core/phase2b-provider-gateway.md](./narrative-intelligence-core/phase2b-provider-gateway.md) | Phase 2B-P Provider Gateway |
| [narrative-intelligence-core/phase2b-prompt-pack-contract.md](./narrative-intelligence-core/phase2b-prompt-pack-contract.md) | Phase 2B-P Prompt Pack Manifest |
| [narrative-intelligence-core/phase2b-context-pipeline.md](./narrative-intelligence-core/phase2b-context-pipeline.md) | Phase 2B-P Context Pipeline |
| [narrative-intelligence-core/phase2b-context-unit-bundle.md](./narrative-intelligence-core/phase2b-context-unit-bundle.md) | Phase 2B-P Context Unit / Levels |
| [narrative-intelligence-core/phase2b-evidence-pipeline.md](./narrative-intelligence-core/phase2b-evidence-pipeline.md) | Phase 2B-P Evidence Pipeline |
| [narrative-intelligence-core/phase2b-module-execution-spec.md](./narrative-intelligence-core/phase2b-module-execution-spec.md) | Phase 2B-P Module Execution Spec |
| [narrative-intelligence-core/phase2b-first-four-modules.md](./narrative-intelligence-core/phase2b-first-four-modules.md) | Phase 2B-P 首批四模块 |
| [narrative-intelligence-core/phase2b-output-validation.md](./narrative-intelligence-core/phase2b-output-validation.md) | Phase 2B-P Output Validation |
| [narrative-intelligence-core/phase2b-candidate-persistence.md](./narrative-intelligence-core/phase2b-candidate-persistence.md) | Phase 2B-P Candidate Persistence |
| [narrative-intelligence-core/phase2b-native-enhanced.md](./narrative-intelligence-core/phase2b-native-enhanced.md) | Phase 2B-P Native / Enhanced |
| [narrative-intelligence-core/phase2b-quality-model-routing.md](./narrative-intelligence-core/phase2b-quality-model-routing.md) | Phase 2B-P Quality / Model Route |
| [narrative-intelligence-core/phase2b-data-handling-privacy.md](./narrative-intelligence-core/phase2b-data-handling-privacy.md) | Phase 2B-P Data Handling / Consent |
| [narrative-intelligence-core/phase2b-checkpoint-recovery.md](./narrative-intelligence-core/phase2b-checkpoint-recovery.md) | Phase 2B-P Checkpoint / Recovery |
| [narrative-intelligence-core/phase2b-budget-usage.md](./narrative-intelligence-core/phase2b-budget-usage.md) | Phase 2B-P Budget / Usage |
| [narrative-intelligence-core/phase2b-error-contract.md](./narrative-intelligence-core/phase2b-error-contract.md) | Phase 2B-P Error Codes |
| [narrative-intelligence-core/phase2b-algorithm-generality.md](./narrative-intelligence-core/phase2b-algorithm-generality.md) | Phase 2B-P Algorithm Generality |
| [narrative-intelligence-core/phase2b-evaluation-contract.md](./narrative-intelligence-core/phase2b-evaluation-contract.md) | Phase 2B-P Evaluation Contract |
| [narrative-intelligence-core/phase2b-language-contract.md](./narrative-intelligence-core/phase2b-language-contract.md) | Phase 2B-P Language Contract |
| [narrative-intelligence-core/phase2b-parallel-file-ownership.md](./narrative-intelligence-core/phase2b-parallel-file-ownership.md) | Phase 2B-P 文件所有权 |
| [narrative-intelligence-core/phase2b-parallel-file-ownership.json](./narrative-intelligence-core/phase2b-parallel-file-ownership.json) | Phase 2B-P 文件所有权（机器可读） |
| [narrative-intelligence-core/phase2b-contract-verification.md](./narrative-intelligence-core/phase2b-contract-verification.md) | Phase 2B-P 61 项验证清单 |
| [narrative-intelligence-core/phase2br-implementation-plan.md](./narrative-intelligence-core/phase2br-implementation-plan.md) | Phase 2B-R 真实实现计划 |
| [narrative-intelligence-core/phase2br-private-repository-boundary.md](./narrative-intelligence-core/phase2br-private-repository-boundary.md) | Phase 2B-R 私有仓库边界 |
| [narrative-intelligence-core/phase2br-provider-and-budget-plan.md](./narrative-intelligence-core/phase2br-provider-and-budget-plan.md) | Phase 2B-R Provider / Budget |
| [narrative-intelligence-core/phase2br-live-analysis-safety.md](./narrative-intelligence-core/phase2br-live-analysis-safety.md) | Phase 2B-R Private Lab 安全门禁 |
| [narrative-intelligence-core/phase2br-parallel-file-ownership.md](./narrative-intelligence-core/phase2br-parallel-file-ownership.md) | Phase 2B-R 文件所有权 |
| [narrative-intelligence-core/phase2br-parallel-file-ownership.json](./narrative-intelligence-core/phase2br-parallel-file-ownership.json) | Phase 2B-R 文件所有权（机器可读） |
| [narrative-intelligence-core/phase2br-integration-report.md](./narrative-intelligence-core/phase2br-integration-report.md) | Phase 2B-R Integration 报告 |
| [narrative-intelligence-core/phase2br-known-limitations.md](./narrative-intelligence-core/phase2br-known-limitations.md) | Phase 2B-R 已知限制 |
| [narrative-intelligence-core/phase2br-production-isolation-verification.md](./narrative-intelligence-core/phase2br-production-isolation-verification.md) | Phase 2B-R 生产隔离验证 |
