# StoryLens 1.1.0 — Native Whole-Book Overview Contract

**Status:** Frozen (STEP 2.1)
**Contract version:** `1.0`
**Change:** CHG-20260725-003
**Step:** STEP-2.1

> 冻结 Public API、Public↔Private 交换 DTO、幂等规则与可量化验收条件。
> **不实现** Orchestrator / Provider / Materializer / UI / Prompt。
> 正式 `POST` 创建端点可保持 `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=True`；本文件只冻结契约形状。

## Related docs

- [Architecture](../architecture/storylens-whole-book-architecture.md)
- [Public/Private boundary](../architecture/storylens-public-private-boundary.md)
- [1.1.0 scope](../releases/storylens-1.1.0-scope.md)
- [ADR-001](../architecture/adr/ADR-001-single-business-database.md) · [ADR-002](../architecture/adr/ADR-002-whole-book-native-source-of-truth.md) · [ADR-003](../architecture/adr/ADR-003-unified-narrative-assets.md) · [ADR-004](../architecture/adr/ADR-004-whole-book-runtime-and-analysis-passes.md) · [ADR-005](../architecture/adr/ADR-005-long-text-index-strategy.md)
- Companion: [error codes](./storylens-1.1.0-native-overview-error-codes.md) · [state machine](./storylens-1.1.0-native-overview-state-machine.md) · [database](./storylens-1.1.0-native-overview-database.md)

## Code anchors

| Concern | Path |
|---------|------|
| Pydantic DTOs | `apps/api/app/narrative_core/contracts/whole_book_overview_v1.py` |
| Error codes | `apps/api/app/narrative_core/contracts/whole_book_overview_errors.py` |
| State machine | `apps/api/app/narrative_core/contracts/whole_book_overview_state_machine.py` |
| Fixtures | `packages/contracts/fixtures/whole_book_overview_v1/` |
| Fixture hash | `packages/contracts/fixtures/whole_book_overview_v1/fixture_hash.py` (+ Public mirror import) |

`CONTRACT_VERSION = "1.0"`.

---

## API (semantic freeze)

Paths may follow existing router prefixes; **semantics** below are frozen.

### Preflight

`POST /api/v1/books/{book_id}/whole-book-runs/preflight`

Prefer reusing existing whole-book preflight plumbing where possible. Response must include at least:

`book_id`, `chapter_count`, `paragraph_count`, `character_count`, `snapshot_required`, `provider_configured`, `license_allowed`, `mode`, `estimated_windows`, `estimated_tokens`, `estimated_cost`, `currency`, `warnings`, `blocking_errors`.

STEP 2.1 freezes the DTO only — full estimate algorithm is out of scope.

### Create Run

`POST /api/v1/books/{book_id}/whole-book-runs`

Request: `mode`, `module_key`, `provider_id`, `model_id`, `client_request_id`, `consent{estimated_tokens,estimated_cost,currency,confirmed}`.

Rules:

- 1.1.0 product entry defaults to `whole_book_native` (`book_overview`).
- Enhanced enum may remain in schema but is not the product default.
- Backend **must** enforce License / Capability gate (frontend hide ≠ authorization).
- Idempotency key: `book_id + client_request_id`.
- Active run conflict returns a frozen error (`RUN_ALREADY_ACTIVE` / `BOOK_HAS_ACTIVE_TASK`).

Response: `run_id`, `book_id`, `snapshot_id`, `mode`, `module_key`, `status`, `current_stage`, `progress`, `created_at`.

### Get Run

`GET /api/v1/whole-book-runs/{run_id}`

Includes progress, token/cost estimates vs actuals, provider/model, error + `retryable`, timestamps.

### Retry / Resume

`POST /api/v1/whole-book-runs/{run_id}/retry` · `POST /api/v1/whole-book-runs/{run_id}/resume`

Frozen DTOs:

- Request: `RetryRunRequest` / `ResumeRunRequest` — required `client_request_id` (idempotency key; may reuse create-run id); retry may include optional `reason`
- Response: `RetryResumeRunResponse` — `run_id`, `book_id`, `snapshot_id`, `status`, `progress`, `retryable`, `actions` (`RunActionsDTO`: `can_retry` / `can_resume`)

Rules:

- `failed` → retry; `paused` → resume.
- Completed is not retryable (`RUN_ALREADY_COMPLETED`).
- Retry must not re-call Provider for completed windows.
- Retry must not create a new Snapshot.
- Invalid Snapshot rejects resume (`SNAPSHOT_INVALID` / `SNAPSHOT_CONTENT_CHANGED`).
- Retry / resume requests are idempotent under the same `client_request_id`.

### Get Overview

`GET /api/v1/whole-book-runs/{run_id}/overview`

Only when `status=completed` (or an explicitly allowed partial-result policy later).
**Must not** reuse the chapter-aggregation insights API as native Overview.

---

## Public ↔ Private schemas

### Window input — `WholeBookOverviewWindowInputV1`

Contains run ref, window slice (paragraph texts from **bound Snapshot** only), prior minimal global state, constraints.
Must **not** pass DB sessions, Windows paths, API keys, license files, or ORM objects.

### Window result — `WholeBookOverviewWindowResultV1`

Candidate entities / assets / evidence, state_delta (1.1.0 min fields only), warnings, quality.

### Synthesis — `WholeBookOverviewSynthesisInputV1`

Materialized / validated assets + entities + evidence + final state + snapshot meta.
Must **not** dump all window fulltext unstructured.

### Projection — `WholeBookOverviewProjectionCandidateV1`

Structured Overview fields, each as `{value, confidence, evidence_refs, status}` with `OverviewFieldStatus`.

### Product Overview API — `OverviewApiResponse`

Separated from Private projection candidate. Includes:

- Typed `run` / `book` / `snapshot` summaries
- `coverage` with original paragraph coverage (Native completed ⇒ `original_coverage_percent = 100`)
- `evidence_index: EvidenceIndexEntry[]` with `evidence_role`, `confidence`, `snapshot_id`, `source_run_id`, and `deep_link` (`chapter_id`, `paragraph_id`, `paragraph_index`, optional `content_hash` / `integrity_status`) for UI jumps

Must **not** reuse the chapter-aggregation insights API (`/pro/whole-book-insights`).

---

## Unified error envelope

```json
{
  "error": {
    "code": "PRO_LICENSE_REQUIRED",
    "message": "...",
    "retryable": false,
    "details": {},
    "run_id": null,
    "stage_key": null,
    "window_index": null
  }
}
```

See [error-codes](./storylens-1.1.0-native-overview-error-codes.md).

---

## Idempotency (frozen)

| Domain | Key |
|--------|-----|
| Create Run | `book_id + client_request_id` |
| Active Run | one active Overview run per book+module+snapshot (default) |
| Window | `run_id + window_index` and `run_id + input_hash` |
| Asset | `source_run_id + asset_type + deduplication_key + snapshot_id` |
| Evidence | per asset version: `paragraph_id + evidence_role + normalized_quote` |

## Transaction boundary (window)

Prefer one transaction for: Entity/Alias merge + Asset/Version + Evidence + Usage/ProviderAttempt + Run State Version + Window Checkpoint.

If ProviderAttempt must persist before the call: record `started → succeeded/failed`; never mark window completed on provider failure; do not lose cost facts on rollback; do not double-bill without a ledger trail.

---

## Quantified acceptance

### Original coverage

```text
original_coverage_percent =
  covered_unique_paragraphs / valid_snapshot_paragraphs × 100
```

Native **completed** run must be **100%** (every valid snapshot paragraph appears in ≥1 window).

### Retry idempotency

After retry of the same failed run:

- completed windows: Provider call count does not increase
- completed windows: no duplicate assets / evidence
- incomplete windows: `attempt_count` may increase

### Evidence validity

- Paragraph belongs to bound Snapshot
- Chapter/paragraph relationship consistent
- Quote is normalized substring (or documented locator mode)
- Evidence points at existing candidate/asset
- Out-of-bound evidence never enters validated state

### Completed recoverability

After API session rebuild / app restart: run remains completed; Overview + evidence deep-links readable; no Private memory cache required.

### License

Free / invalid Pro create → HTTP **403** (`PRO_LICENSE_REQUIRED`). Backend gate required.

### DB upgrade

On 1.0.5-like schema upgrade: book/chapter/paragraph/run counts preserved; new tables usable; re-apply migration idempotent.

---

## Fixtures

Canonical: `packages/contracts/fixtures/whole_book_overview_v1/`
Manifest: `FIXTURE_MANIFEST.json` (`contract_version` + per-file sha256 + `combined_sha256`).
Private must mirror fixtures and verify the same hashes.
