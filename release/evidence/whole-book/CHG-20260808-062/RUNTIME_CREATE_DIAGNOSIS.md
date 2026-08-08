# CHG-062 Runtime Create Diagnosis

## Captured against STALE API (127.0.0.1:56405)

REQUEST URL: POST /api/v1/books/1/whole-book/free/create
REQUEST JSON (consent_id omitted, limits present):

```json
{
  "estimate_id": 16,
  "client_request_id": "chg062-runtime-diag6",
  "max_provider_calls": 500,
  "max_input_tokens": 1858000,
  "max_output_tokens": 397000,
  "max_cost_budget_cny": "10",
  "auto_retry_enabled": false
}
```

HTTP STATUS: 422
ERROR CODE: REQUEST_VALIDATION_ERROR
DETAIL highlights:
- `consent_id`: Field required
- with null consent_id: Input should be a valid integer
- limits fields: Extra inputs are not permitted

OpenAPI (stale): `CreateFreeRunRequest.required = [estimate_id, consent_id, client_request_id]` — no limit fields.

## Source vs Running

SOURCE CreateFreeRunRequest: consent_id optional + limit fields (CHG-062) → NEW
RUNNING (before rebuild): consent_id required → OLD

ROOT CAUSE: **STALE SIDECAR**

## Sidecar rebuild

Command: `powershell -File scripts/build_sidecar.ps1`
OLD SHA256: `0C6513DEC5CBA15F71154E17CAB417C9CB9CFCD8C14B46B12ADC28533D4F3489`
NEW SHA256: `6E049C483744ECCD69AEFF19904BF92797123B1BF19A77FE6AC20AC3DFB7C197`
Path: `apps/desktop/src-tauri/binaries/storylens-api-x86_64-pc-windows-msvc.exe`

## After rebuild (127.0.0.1:57335)

OpenAPI: consent_id nullable/omitted; limit fields present; required=[estimate_id, client_request_id]
Create without consent_id: **not 422** (business path entered)
cloud_invocations / usage: **0** DeepSeek calls
Product code changed this round: **NO** (rebuild only)
