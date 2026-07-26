# FIX-3B — PROVIDER_OUTPUT_INVALID (Run #5 / #6)

## Readonly evidence (user DB unchanged)

Database: `C:\Users\msi\AppData\Local\StoryLens\database\storylens.db`

| Field | Run #5 | Run #6 |
|---|---|---|
| book_id | 1 | 5 |
| status | failed | failed |
| error_code | PROVIDER_OUTPUT_INVALID | PROVIDER_OUTPUT_INVALID |
| stored error_message | Window result is not a JSON object. | same |
| failed stage (stages table) | extract_overview_facts | extract_overview_facts |
| run.failed_stage | NULL (historical) | NULL |
| windows | 1 failed @ index 0; 2045 pending | 1 failed @ index 0; 6 pending |
| provider / model | aliyun_qwen_plus / qwen3.7-plus | same |
| invocations | #65 | #66 |
| input_tokens | 5191 | 4294 |
| output_tokens (stored) | 0 | 0 |
| estimated_cost (stored) | 0.0 | 0.0 |
| raw_response_text length | 35 (= overwritten with error message) | 35 |
| finish_reason | NULL | NULL |
| Repair attempted | NO | NO |
| Relationship | Independent runs (not retry_of) | |

Active Run: 0

## Cost reconciliation

```text
ACTUAL_COST_RECONCILIATION_REQUIRED
```

Stored actual cost is ¥0.00 because failure accounting overwrote Provider text and zeroed output tokens/cost.
Input-only lower bound (qwen3.7-plus official list, output=0):

- Run #5 ≈ ¥0.010382
- Run #6 ≈ ¥0.008588
- Total lower bound ≈ ¥0.01897
- Output cost: UNKNOWN (raw output destroyed)

Do not treat stored ¥0 as true settlement. Do not overwrite STEP 2.G5 ledger rows.

## Root cause

1. Window 0 Provider reply failed `parse_window_result_text` — `extract_json_object` did not yield a dict → wire `PROVIDER_OUTPUT_INVALID` / message `Window result is not a JSON object.`
2. Failure class for the **stored symptom**: **C** (JSON not an object / unparseable). Historical raw body was destroyed, so B / I / J cannot be proven for #5/#6.
3. **Accounting defect**: on failure, attempt text was replaced with the error message and output_tokens/cost forced to 0 — destroys diagnostics and under-reports cost.
4. No Provider Repair existed on this path; citation repair never ran because parse failed first.

## Fixes (generic)

- Stronger JSON extract (fence / prose / balanced object)
- Truncation classification → internal `PROVIDER_OUTPUT_TRUNCATED` (wire still PROVIDER_OUTPUT_INVALID)
- One controlled Provider Repair for recoverable format failures (not empty / truncated / filtered)
- Preserve Provider text/tokens/cost on failed attempts; harvest repair call_log pair
- Chinese Task Center copy; failed window / provider / model / repair in serialize_run + TasksPage
- Live max_output_tokens 2048 → 4096 (bounded)

## Offline gates

- Private parse matrix + engine: PASS
- Public native overview directed (step23/24/runtime/walking/http/ai_binding): 53 passed
- Desktop `tsc --noEmit`: PASS
- Live Provider: NOT called in FIX-3B
- Database / migration / contract: unchanged
- VERSION: 1.0.5

## RC3 acceptance

Remains BLOCKED until RC4 with FIX-3B is installed and short live smoke (optional) passes. Not verified.
