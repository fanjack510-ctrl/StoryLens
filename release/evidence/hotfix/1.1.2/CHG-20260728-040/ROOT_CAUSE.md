# ROOT_CAUSE — CHG-20260728-040 / INC-20260728-002

## Primary categories (selected)

| Code | Category | Selected | Confidence |
|------|----------|----------|------------|
| **A** | 请求输出上限配置过低 | **YES** | **CONFIRMED** |
| **H** | Retry 策略无效 | **YES** | **CONFIRMED** |
| C | 单次 structured output Schema/批次体积过大 | YES (contributing) | HIGH |
| D | Prompt 要求内容过多 | secondary | MEDIUM |
| I | 用量结算或 Reservation 状态错误 | partial UI symptom only | HIGH that reservation release is correct; usage ledger exists |
| J | 场景进度统计错误 | UI mapping symptom | CONFIRMED as display of pre-scene failure |
| B | 模型/Provider 硬输出上限 | NO (user hard 4000; provider accepted 768 and stopped at length) | — |
| E | 模型异常冗长 | possible but not required | LOW |
| F | finish_reason 检查顺序错误 | NO (checked before parse) | CONFIRMED not F |
| G | 截断响应错误分类错误 | partial: root code correct, UI status label “结构校验失败” is coarse | MEDIUM |
| K | 其他 | — | — |

## A — Request output limit too low (CONFIRMED)

### Code evidence
- `apps/api/app/core/config.py`: `cloud_output_scene_boundary = 768`
- `apps/api/app/services/cloud_output_policy.py`: `scene_boundary_adjudication` → same 768; `resolve_output_limit` sets `effective_limit = configured` when user hard ≥ configured

### DB evidence
- Invocations 80/81/82: `requested_output_tokens=768`, `actual_output_tokens=768`, `finish_reason=length`
- `request_parameters`: `configured_limit=768`, `user_hard_limit=4000`, `effective_limit=768`
- Prior successful adjudications on same install used 440–505 output tokens under the same 768 ceiling with ~half the input size

### Log evidence
- Sidecar application logs do not mirror invocation finish_reason strings; DB `model_invocations` is the system of record

### Certainty / scope
- **Determined: YES** for this failure mode
- Affects all providers using `cloud_output_scene_boundary` for detection/adjudication
- Affects scene_pipeline boundary adjudication (and detection when output near 768); not native-overview 8192 path
- Present in v1.1.1 (and earlier phase-2b2 tests assert 768)

## H — Retry strategy ineffective (CONFIRMED)

### Code evidence
- `structured_output.py` truncation_retry only appends “请从头重新生成完整JSON…”; `resolve_output_limit(..., invocation_kind="truncation_retry")` still resolves to 768 for adjudication
- Transport allows up to 3 attempts → three paid truncated calls

### DB evidence
- Attempts 1–3 all `effective_limit=768`, all `finish_reason=length`

### Certainty
- Retry cannot succeed if required output > 768 regardless of prompt wording

## C — Single adjudication batch too large vs output budget (HIGH)

### Code evidence
- `plan_adjudication_batches` packs by **input** tokens (`MAX_ADJUDICATION_INPUT_TOKENS=12000`) only; no output-budget packing

### DB evidence
- One adjudication call: 20 candidates, ~72 paragraph ids, snapshot `character_count=12029`, `input_tokens≈6215`
- Output exhausted exactly at 768

### Impact
- Larger chapters / denser candidates more likely to fail; smaller chapters succeed under same 768

## I / J — Usage UI & scene progress (symptoms, not truncation root)

### I
- Reservation `#6` correctly `released` after failure; consumed tokens/cost recorded
- `model_invocations` holds full usage; TasksPage shows “暂无用量明细” when budget block fields absent → **display gap**, not lost accounting

### J
- Scenes never created (`scenes` count for chapter=0) → detail “场景进度：0 / 0”
- DB `progress_current/total` is `0/1` (pipeline stage progress); UI detail prefers scene counters

## F / G notes

- Finish reason checked before JSON parse → not F
- Root error `OUTPUT_TRUNCATED` is correct; status `failed_structural` / UI “结构校验失败” is a coarse product mapping (G partial)

## Earliest introduction

- Output ceiling 768 for boundary tasks is intentional Phase 2B-2 policy (tests in `test_phase_2b2.py`); shipped through v1.1.1
- Failure surfaces when adjudication batch output needs >768 (observed when input ≈6k tokens / 20 candidates)

## Other models / analysis types

| Path | Same 768? | Risk |
|------|-----------|------|
| scene_boundary detection | yes | medium (often finishes &lt;768) |
| scene_boundary_adjudication | yes | **high for large batches** |
| scene_analysis | 1600 | different |
| reader_journey_* | 3000–3500 | different |
| native overview live | 8192 | different module |
