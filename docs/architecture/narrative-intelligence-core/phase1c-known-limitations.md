# Phase 1C Known Limitations

## Python / SSL

- Prefer `D:\Dstorylens\.venv\Scripts\python.exe` (3.12.10, OpenSSL 3.0.16).
- Agent H reported host Python 3.11 `_ssl` breakage; Integration does not change project code to paper over that.
- This environment: SSL import OK on project venv.
- HTTP TestClient suites may still be skipped on broken hosts; Integration verifies routes via import + OpenAPI schema registration (`test_17_openapi_routes_registered`).

## Quota persistence

- `InMemoryQuotaService` is explicitly `memory_non_production`.
- Process restart loses reservations/usage — do not treat as commercial quota.
- Formal release needs a durable Quota implementation (out of Phase 1C scope). No Quota DB tables in this phase.

## Real Engine

- No production WholeBook Engine registered.
- No real prompts / model calls / novel analysis.
- Mock path is test-only.

## Artifact evolution

- Stage results reuse `analysis_artifacts` with envelope JSON.
- Future typed columns / dedicated tables deferred (no schema change now).

## Frontend product surface

- Capability infrastructure + presentation components exist.
- No formal whole-book analysis page / Pro navigation in this phase.
- `PRO_CAPABILITIES_SHIPPED` remains false.

## Legacy `can_use_feature`

- Still routed through CapabilityService for compatibility.
- New whole-book code uses CapabilityService / Guard only.
- Large-scale legacy page migration deferred; audit remains in `phase1c-legacy-vip-audit.md`.
