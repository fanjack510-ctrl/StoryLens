# Phase 1D-P Run Progress Contract

`WholeBookRunViewState` + `WholeBookStageProgressDto` + control rules.  
Contract-only this phase; real Run create remains disabled.

## WholeBookRunViewState

| Field | Notes |
|-------|-------|
| `run_id` | |
| `book_id` | |
| `snapshot_id` | |
| `analysis_mode` | native / enhanced |
| `status` | see Run statuses |
| `current_stage` | current stage key or null |
| `stages` | list of `WholeBookStageProgressDto` |
| `completed_modules` | modules with usable results |
| `available_modules` | modules selectable / planned |
| `failed_modules` | modules failed (others remain) |
| `partial_results_available` | bool |
| `progress_percent` | honest estimate or null |
| `token_usage` | aggregate |
| `cost` | aggregate |
| `started_at` / `updated_at` | |
| `estimated_remaining` | optional |
| `blocking_issue` | optional blocker |
| `allowed_actions` | **backend-authored** |

## Run statuses

`pending` | `running` | `paused` | `interrupted` | `completed` | `failed` | `cancelled`

Stage statuses (Phase 1A):  
`pending` | `running` | `paused` | `interrupted` | `completed` | `failed` | `skipped` | `cancelled`

## WholeBookStageProgressDto

| Field | Notes |
|-------|-------|
| `stage_key` | Engine stage key |
| `display_name` | user-facing |
| `order` | plan order |
| `status` | stage status |
| `required` | bool |
| `resumable` / `retryable` | capability flags |
| `progress_percent` | honest; may be null |
| `started_at` / `completed_at` | |
| `attempt_count` | increments on retry |
| `checkpoint_available` | bool |
| `token_input` / `token_output` / `cost` | |
| `output_artifact_ids` | refs only |
| `produced_module_keys` | modules advanced by this stage |
| `warnings` | |
| `error_code` / `error_message` | no full body text |
| `allowed_actions` | backend-authored |

## Control rules

### pause

- Only when Run `running`
- Current Stage must be pausable
- Does **not** alter completed results

### resume

- From `paused` or `interrupted`
- Completed stages are **not** re-run
- Failed stages are **not** auto-recovered

### retry

- Only failed Stage
- Increments `attempt_count`
- Re-runs failed stage + affected downstream only

### cancel

- Allowed from `pending` / `running` / `paused` / `interrupted`
- Does **not** delete produced Asset Versions
- Candidate assets retained; mark Run incomplete

## `allowed_actions`

- Must be returned by backend on Run View / Stage Progress DTOs
- Frontend **must not** derive allowed actions locally from status alone
- Typical values (illustrative): `pause`, `resume`, `retry`, `cancel`, `view_partial_results`

## Progress honesty rules

1. 不展示内部 Prompt / 敏感系统配置 / License Key / Credential
2. 错误信息不得包含完整正文
3. 用户能看懂当前在做什么；禁止只显示「AI分析中」
4. 进度与真实 `RunStage` 对齐
5. **不伪造**精确百分比
6. 无法计算时使用阶段级状态，而不是假进度
7. 部分结果可用时 `partial_results_available=true`；单阶段失败不抹掉已完成模块
