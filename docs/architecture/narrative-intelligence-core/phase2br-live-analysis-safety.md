# Phase 2B-R Live Analysis Safety (Private Engine Lab)

**Change:** CHG-20260723-041  
**Purpose:** Dev/test verification gate for real Provider + private Engine — **not** product release.

## Distinct from Mock Lab

| | Mock Lab (Phase 2A) | Private Engine Lab (2B-R) |
|--|---------------------|---------------------------|
| Env flag | `WHOLE_BOOK_MOCK_LAB_ENABLED` | `WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED` |
| Default | `false` | `false` |
| Header | `X-StoryLens-Mock-Lab: 1` | `X-StoryLens-Private-Engine-Lab: 1` |
| Engine | `mock_whole_book_v0` synthetic | Private Engine + real Provider (when enabled) |
| Meaning | Shell/orchestration dry-run | Real cost / real model risk |

Do not overload Mock Lab semantics for real analysis.

## Planned Lab surface

- Path prefix: `/api/v1/labs/private-whole-book-runs`
- Formal create `POST /api/v1/books/{book_id}/whole-book-runs` remains **disabled** (`WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=True` in `contracts/api_dto.py`)
- OpenAPI: Lab routes mounted only when env+environment allow (mirror Mock Lab pattern in `main.py` / `whole_book_mock_lab_runs.py`)

## Gate checklist (must all pass)

1. **Environment** — `development` or `test` only  
2. **Loopback** — reject non-loopback clients (same class of check as Mock Lab auth)  
3. **Header marker** — `X-StoryLens-Private-Engine-Lab: 1`  
4. **Capability** — fail-closed CapabilityService decision for whole-book feature keys  
5. **Credential** — keyring has usable `aliyun_qwen_plus` (or selected route); never log secret  
6. **Data transfer authorization** — user consent that cloud send is allowed  
7. **Fee estimate** — tokens + cost estimate shown before start  
8. **Single-run budget** — reservation / max for this run  
9. **Daily budget** — remaining requests/tokens/cost from `cloud_budget`  
10. **Explicit user confirm** — checkbox/action with Provider, location, whether raw text leaves device  
11. **Concurrency limit** — one active Private Lab run per book (or stricter)  
12. **Cancel** — cooperative cancel via token + Provider cancel  
13. **Interrupt recovery** — resume only if fingerprints match (engine/prompt/config/snapshot)  
14. **OpenAPI production isolation** — production builds do not expose Lab  
15. **Formal entry stays closed** — do not flip `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED` / `PRO_CAPABILITIES_SHIPPED` / `PRODUCTION_DEFAULT_ENGINE_ID`

## Consent payload (user-visible)

Must disclose before first Provider call:

- What content leaves device (catalog / chapter batches / Evidence windows — never silent full-book dump)  
- Provider key + model route  
- Execution location (local package vs future sidecar vs cloud)  
- Whether novel text is sent  
- Whether Provider payloads are retained (default: no raw body in StoryLens logs/artifacts)  
- Estimated tokens & cost  
- Single-run + daily remaining  
- Cancel availability  
- Local vs cloud differences  

Defaults: **do not upload** until confirm.

## Privacy / logging

| Store | Rule |
|-------|------|
| App logs | No novel body; no API key |
| Audit | No novel body; no credential |
| Stage Artifact | No full novel text |
| API responses | No raw Provider completion dump to frontend |
| Private Engine DTO | No credential fields |

## Failure / budget behavior

- Bounded retries only  
- Budget deny → stop; keep already-validated candidate writes  
- Validation failure → do not persist that batch  
- Partial module success allowed and projected as partial  

## Manual Live Smoke (post-Integration; not this phase)

See implementation plan §11. Status stays `tested` until user completes smoke → then `verified` only.

## Production gates (must remain)

| Constant | Required value | Location |
|----------|----------------|----------|
| `PRO_CAPABILITIES_SHIPPED` | `false` | `apps/desktop/src/services/productEdition.ts` |
| `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED` | `True` | `narrative_core/contracts/api_dto.py` |
| `PRODUCTION_DEFAULT_ENGINE_ID` | `None` | `whole_book_engine_registry.py` |
| `WHOLE_BOOK_MOCK_LAB_ENABLED` | `False` | `run_shell_contract/mock_lab.py` |
| `WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED` | planned default `False` | Agent S adds constant |
