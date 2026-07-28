# CODE_PATH — CHG-20260728-040

Read-only path for v1.1.1 sources on Public issue worktree  
`D:\Dstorylens-wt-hotfix-1.1.2-structured-output` @ `38c85ab4…`  
and Private @ `30d8dad8…` (adjudication path is Public API; Private engine not on this failure path).

## End-to-end call chain (incident)

```
UI create chapter analysis
→ apps/api analysis router (scene_pipeline)
→ apps/api/app/services/scene_pipeline.py
   → detection batches (scene_boundary / CompactTransition… v3.5)  [SUCCEEDED x14]
   → plan_adjudication_batches(...)   # packs by INPUT token budget only (max 12000)
   → generate_validated(..., task_type="scene_boundary_adjudication",
                          schema=BoundaryCandidateAdjudicationResult,
                          initial_invocation_kind="boundary_candidate_adjudication")
→ apps/api/app/services/structured_output.py::generate_validated
   → resolve_output_limit(task_type, invocation_kind)
   → ModelRequest with max_output_tokens = effective_limit
   → model_invocation_broker.invoke → Aliyun OpenAI-compatible adapter
   → response.finish_reason checked BEFORE JSON parse
   → OutputTruncatedError → next_kind=truncation_retry (same limit)
   → after max transport attempts → raise to pipeline
→ analysis_runs.status=failed_structural, failed_stage=structured_output
→ cloud_budget_reservations.status=released
→ TasksPage: 结构校验失败 / 场景进度 0/0 / 暂无用量明细
```

## Public files / symbols

| Layer | File | Symbol / notes |
|-------|------|----------------|
| Config defaults | `apps/api/app/core/config.py` | `cloud_output_scene_boundary: int = 768` |
| Output policy | `apps/api/app/services/cloud_output_policy.py` | `_configured_limit`, `resolve_output_limit`; maps `scene_boundary_adjudication` → `cloud_output_scene_boundary`; **`truncation_retry` does not raise limit** |
| Structured output | `apps/api/app/services/structured_output.py` | `OutputTruncatedError`, `generate_validated`; finish_reason ∈ `{length,max_tokens}` → truncate; truncation_retry prompt only |
| Pipeline | `apps/api/app/services/scene_pipeline.py` | adjudication loop ~L911–941 |
| Batch planner | `apps/api/app/services/scene_boundary_adjudicator.py` | `plan_adjudication_batches`, `MAX_ADJUDICATION_INPUT_TOKENS=12000` |
| Schema | `apps/api/app/schemas/scene.py` | `BoundaryCandidateAdjudicationResult` / `BoundaryCandidateVerdict` |
| Budget default | `apps/api/app/schemas/settings.py` | `cloud_max_output_tokens_per_request` default **4000** |
| Transport | `apps/api/app/model_gateway/providers/openai_compatible.py` | maps `max_output_tokens` → wire `max_tokens` |
| UI status | `apps/desktop/src/pages/TasksPage.tsx` | `failed_structural` → `结构校验失败`; scene progress from `completed_scene_count/total_scene_count`; usage section requires budget block fields else `暂无用量明细` |
| UI progress helper | `apps/desktop/src/services/runProgressDisplay.ts` | list progress formatting |

## Parameter sources (incident values)

| Parameter | Source | Value on failure |
|-----------|--------|------------------|
| configured_limit | Settings `cloud_output_scene_boundary` | **768** |
| user_hard_limit | `application_settings.cloud_budget_settings.cloud_max_output_tokens_per_request` | **4000** |
| effective_limit | `min`-style policy: uses configured when hard ≥ configured | **768** |
| Provider wire field | `provider_parameter_name` | `max_tokens` |
| Structured mode | request / provider | `json_object` |
| Thinking | disabled | `enable_thinking=false` |
| Transport max attempts | `aliyun_transport_max_attempts` / retries | 3 attempts observed |

## Defaults / ceilings

| Knob | Default (v1.1.1) |
|------|------------------|
| scene boundary / adjudication output | 768 |
| scene analysis output | 1600 |
| reader journey scene output | 3500 |
| user hard max output / request | 4000 (settings) |
| adjudication input packing | 12000 tokens |
| Native overview live default (separate path) | 8192 |

## Exception conversion points

1. Provider HTTP 200 + `finish_reason=length`  
2. `structured_output.generate_validated` → `OutputTruncatedError` (`OUTPUT_TRUNCATED`, category `structured_output`)  
3. After retries exhausted → pipeline marks run `failed_structural` / `SCENE_PIPELINE_FAILED` with root `OUTPUT_TRUNCATED`  
4. UI maps `failed_structural` → **结构校验失败** (even though root cause is truncation, not schema mismatch)

## Order of checks (important)

`finish_reason` / `_looks_truncated` is evaluated **before** `extract_json_object` / schema validate.  
Classification order is correct for length truncations; partial JSON was not persisted (`raw_logging_enabled=0`).

## Private engine

Private HEAD `30d8dad8…` contains native-overview parse/truncation helpers under  
`src/storylens_private_engine/...` — **not invoked** for this single-chapter assisted boundary adjudication failure. Public structured_output path is authoritative for INC-20260728-002.
