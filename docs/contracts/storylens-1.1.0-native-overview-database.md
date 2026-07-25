# StoryLens 1.1.0 — Native Overview Database

**Status:** Frozen (STEP 2.1)  
**Change:** CHG-20260725-003  
**Migration:** `20260725_011_whole_book_overview_runtime`  
**ORM:** `WholeBookRunWindow`, `WholeBookRunStateVersion` in `apps/api/app/db/models.py`

## Related docs

- [Contract](./storylens-1.1.0-native-overview-contract.md)
- [Error codes](./storylens-1.1.0-native-overview-error-codes.md)
- [State machine](./storylens-1.1.0-native-overview-state-machine.md)
- [Architecture](../architecture/storylens-whole-book-architecture.md)
- [Public/Private boundary](../architecture/storylens-public-private-boundary.md)
- [1.1.0 scope](../releases/storylens-1.1.0-scope.md)
- [ADR-001](../architecture/adr/ADR-001-single-business-database.md) · [ADR-002](../architecture/adr/ADR-002-whole-book-native-source-of-truth.md) · [ADR-003](../architecture/adr/ADR-003-unified-narrative-assets.md) · [ADR-004](../architecture/adr/ADR-004-whole-book-runtime-and-analysis-passes.md) · [ADR-005](../architecture/adr/ADR-005-long-text-index-strategy.md)

---

## Inventory decision (confirmed)

### REUSE

| Capability | Existing structure |
|------------|--------------------|
| Snapshot | `book_snapshots` (+ chapters/paragraphs) |
| Run | `analysis_runs` |
| Stages / checkpoint | `analysis_run_stages.checkpoint_json` |
| Narrative facts | `narrative_entities` / aliases / assets / versions / evidence |
| Overview projection storage | `analysis_artifacts` + product DTOs (**not** a dedicated overview fact table as SoT) |
| Provider attempts / usage | `model_invocations` (+ existing budget structures) |
| Lab 10-stage keys | `WholeBookStageKey` — keep |
| Free run statuses | `queued` / `running` / `interrupted` — keep |

### ADD (minimal)

1. **`whole_book_run_windows`** — window execution, input hash, attempt, tokens/cost, checkpoint, provider attempt link  
2. **`whole_book_run_state_versions`** — recoverable minimal global state after windows  

### NOT added

- Second business DB / `pro.db`
- Neo4j / vector DB / FTS5
- Dedicated Overview JSON-as-sole-truth table
- Full novel body duplication into window rows
- Private-side migrations

---

## New tables

### `whole_book_run_windows`

Unique: `(run_id, window_index)`, `(run_id, input_hash)`.

Fields include paragraph/chapter bounds, `input_hash`, `status`, `attempt_count`, state version before/after, `provider_attempt_id`, token/cost, errors, `checkpoint_json`, timestamps.

Does **not** permanently store full window body text.

### `whole_book_run_state_versions`

Unique: `(run_id, version_number)`.

`state_json` is recoverable runtime state — **not** the sole narrative fact source. Formal facts remain Entity/Asset/Evidence.

---

## Migration rules

1. Additive only; compatible with 1.0.5 DBs.
2. Safe defaults / nullable where needed; no Free column deletes/renames.
3. Idempotent re-apply (ledger + `IF NOT EXISTS`).
4. ORM and migration DDL stay aligned.
5. Order: `create_all()` (or upgrade path) then `apply_narrative_migrations()` which includes 001–010 then **011**.
6. Entry points: `apply_narrative_overview_migrations` / `apply_narrative_migrations`; `create_db()` calls `apply_narrative_migrations`.
7. No Private-repo migrations.

Checksum source: `SQL_011` in `apps/api/app/narrative_core/migrations/runner.py`.

---

## Free compatibility

- 1.0.5 Book / Chapter / Paragraph / chapter AnalysisRun / Reader Journey remain readable.
- Free APIs gain no mandatory new request fields.
- Free data does not require Pro status backfill.
- Free users without Pro must not create Whole-Book Overview runs.
- Active Whole-Book runs count as active tasks (block delete) — product rule; enforcement in later steps.
- Original TXT/DOCX/EPUB never deleted by Overview runtime.
