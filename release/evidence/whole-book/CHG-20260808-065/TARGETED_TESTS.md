# CHG-20260808-065 Unified Provider Routing

PUBLIC BASE: 673d95ea7fbad13c0430e7f8a8221d299e60cf01
BRANCH: feature/v120-provider-routing
WORKTREE: D:\Dstorylens-wt-v120-provider-routing

## Targeted pytest
`pytest apps/api/tests/test_cloud_provider_routing_chg065.py`
Result: 13 passed

## Typecheck
`npm run typecheck` (apps/desktop)
Result: PASS

## Targeted frontend
`vitest run src/components/providers/providerDisplayLabels.test.ts`
Result: PASS (enabled ≠ active / connection failure keeps 已启用)

## Policy
- scene_boundary / scene_structure / whole_book: FOLLOW_DEFAULT
- json_schema_repair / retry / resume / whole_book_repair: INHERIT_RUN
- high_difficulty_review: FIXED aliyun_qwen_max
- local tasks: LOCAL_ONLY

## Key modules
- apps/api/app/services/task_routing_policy_v1.py
- apps/api/app/services/cloud_provider_resolver_v1.py
- analysis_execution_plan follows active_cloud_provider
- routing_preview uses resolver
- ProvidersPage: 正在编辑 + 当前默认; Settings: 当前默认 AI 服务商
- Saving Provider config no longer auto-switches active_cloud_provider

REAL PROVIDER CALLS: 0
PROTECTED WIP MODIFIED: NO
