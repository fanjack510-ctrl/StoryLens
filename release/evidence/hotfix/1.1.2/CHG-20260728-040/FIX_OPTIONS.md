# FIX_OPTIONS — CHG-20260728-040

## Comparison

| Option | Solves root? | Compatible 1.1.1? | DB migrate? | Cost ↑ | Double-charge risk | Changes algorithm results? | Fit for PATCH 1.1.2? | Defer to 1.2.0? |
|--------|--------------|-------------------|-------------|--------|--------------------|----------------------------|----------------------|-----------------|
| **A** Raise max output tokens only | Partially (A yes; H residual if still too low) | yes | no | yes per call | low if single attempt succeeds | no (same schema) | yes if modest + capped by user hard | no |
| **B** Compute output budget from input/schema/candidate count | Yes (A+C) | yes | no | controlled | low | no | **yes — preferred core** | no |
| **C** Shrink single structured payload | Yes (C) | yes | no | may ↓ | low | may change verbosity not verdicts if fields unchanged | yes if schema-compatible | maybe larger rewrite |
| **D** Split adjudication into output-bounded stages | Yes (C) | yes | no | may ↑ requests | medium if naive | should be equivalent if merge correct | yes if uses existing batch planner | no |
| **E** Controlled continuation on length | Partial | yes | no | yes | medium | risk of concat errors | risky for PATCH | prefer 1.2.0 |
| **F** Compact-prompt truncation retry | Weak alone | yes | no | yes | medium | no | only as adjunct | — |
| **G** Fix classification + usage UI only | No (symptoms) | yes | no | no | no | no | yes as adjunct | — |

## Recommendation (minimal PATCH)

**Primary: B + D (small) + H fix + G adjunct**

1. **Output-aware adjudication packing (D/B)**  
   Extend `plan_adjudication_batches` (or sibling) to also bound estimated **output** tokens (e.g. candidates × per-verdict estimate + envelope) so each request stays under configured limit with margin.

2. **Raise adjudication/boundary configured limit modestly within user hard cap (A/B)**  
   e.g. map `scene_boundary_adjudication` to a dedicated setting (not necessarily identical to detection), still ≤ `cloud_max_output_tokens_per_request` (4000). Do **not** blindly set to 8192.

3. **Make truncation_retry increase effective limit once (H)**  
   On `truncation_retry`, bump toward `min(configured_raised, user_hard_limit)` with a hard max attempts (already ≤3). Never infinite retry.

4. **Adjunct G**  
   Keep root `OUTPUT_TRUNCATED`; optionally surface clearer UI copy than only “结构校验失败”; expose invocation usage summary on failed task detail so “暂无用量明细” is not misleading.

### Explicit non-goals for 1.1.2
- No prompt rewrite of literary instructions
- No schema field removal that changes contracts
- No continuation-concat repair as primary (E)
- No whole-book / new providers
- Forward-port to `integration/whole-book-v120` after PATCH verify

### Database migration
**NO** for recommended path.

### Charge safety
- Prefer succeeding in 1 attempt after budget fix
- Truncation retries must not repeat identical doomed 768 forever
- Task-level retry should prefer resume/checkpoint where already implemented for detection; document if new run re-bills detection
