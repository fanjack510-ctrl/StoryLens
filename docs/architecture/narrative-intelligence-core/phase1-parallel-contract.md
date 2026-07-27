# Phase 1 Parallel Contract (frozen)

**Change:** CHG-20260723-011 (Phase 1P)  
**Baseline:** StoryLens 1.0.5 / `v1.0.5` / `ddae7ee4910ab35a443e47fc1ffad4928e7a5543`  
**Branch:** `feature/narrative-phase1-contract`  
**Nature:** Shared ORM skeleton + enums + Protocols + migration IDs. No whole-book analysis, no model calls, no hash backfill business, no stage state-machine service.

---

## 1. Parallel architecture

```text
v1.0.5 (ddae7ee)
    └── feature/narrative-phase1-contract   ← Phase 1P (this Change)
            ├── feature/narrative-phase1a-snapshot      (Agent A)
            ├── feature/narrative-phase1a-runstage      (Agent B)
            ├── feature/narrative-pattern-readiness     (Agent C)
            └── integration/narrative-phase1a           (Integration)
```

All Agent branches **must** fork from the Phase 1P final commit, not from `v1.0.5` again.

---

## 2. Compatibility notes (important)

| Topic | Freeze |
|-------|--------|
| Legacy chapter binding | `analysis_runs.subject_type` / `subject_id` — **there is no `chapter_id` column** on `analysis_runs` in 1.0.5 |
| New scope fields | `scope_type`, `book_id`, `start_chapter_id`, `end_chapter_id`, `book_snapshot_id` (all nullable) |
| Legacy `analysis_type` | NULL allowed; treat NULL + `task_type=scene_pipeline` as chapter scene pipeline |
| Existing `AnalysisRun.content_hash` | Remains run input content hash — **not** the new chapter/paragraph `content_hash` columns |
| Chapter/Paragraph `content_hash` | New nullable columns; Agent A backfills |

---

## 3. Data objects

### schema_migrations
`migration_id` (PK), `checksum` (NOT NULL), `app_version`, `applied_at`  
Also records marker `baseline_1_0_5`.

### chapters / paragraphs
Added: `content_hash VARCHAR(64) NULL` + indexes.

### book_snapshots
`id`, `book_id` FK, `content_hash`, counts, `snapshot_status`, `source_fingerprint` (source fingerprint only), `error_code`, `error_message`, `created_at`
Unique `(book_id, content_hash)`.

### book_snapshot_chapters
Immutable chapter text in `content_text`. Unique `(snapshot_id, chapter_order)` and `(snapshot_id, source_chapter_id)`.

### book_snapshot_paragraphs
Offsets with CHECK `start_offset >= 0` and `end_offset >= start_offset`. Unique `(snapshot_chapter_id, paragraph_order)`.

### analysis_runs (additive)
`analysis_type`, `scope_type`, `book_id`, `start_chapter_id`, `end_chapter_id`, `book_snapshot_id`, `configuration_fingerprint`.

### analysis_run_stages
Per-run stage rows; unique `(run_id, stage_key)`; `cost` is `FLOAT` (aligned with `model_invocations.estimated_cost`).

---

## 4. Enums (module)

`apps/api/app/narrative_core/enums.py`

- `AnalysisScopeType`: chapter | chapter_range | book  
- `SnapshotStatus`: building | completed | failed | invalid  
- `StageStatus`: pending | running | paused | interrupted | completed | failed | skipped | cancelled  
- `RunStatus` (Phase 1A): pending | queued | running | paused | interrupted | completed | failed | cancelled
- `AnalysisType`: scene_pipeline | whole_book_native | whole_book_enhanced

`INVALID` snapshot: completed snapshot that failed integrity / book mismatch — not a building retry state.

---

## 5. Interfaces (Protocols)

Under `apps/api/app/narrative_core/contracts/`:

| Protocol | Owner |
|----------|-------|
| `MigrationLedger` | Agent A |
| `ContentHashService` | Agent A |
| `BookSnapshotRepository` / `BookSnapshotService` | Agent A |
| `SnapshotValidationGateway` | Agent A implements; **Agent B consumes only** |
| `AnalysisRunService` / `AnalysisRunStageRepository` | Agent B |

Pure hash helpers in `hash_canon.py` (Phase 1A unified book hash):

- `canonicalize_text`, `calculate_text_hash` (body canonicalization frozen)
- `BookHashChapterInput(chapter_order, title, content_hash)`
- `calculate_book_content_hash(chapters)` — **sole public book hash entry**

---

## 6. Stage state machine

Defined in `apps/api/app/narrative_core/stage_transitions.py`.

Rules (frozen):

- completed / skipped / cancelled are terminal  
- completed **cannot** return to running  
- retry = failed → running and **must** increment `attempt_count`  
- pause ≠ failed  
- interrupted = environment stop, not permanent analysis failure  

Agent B implements this matrix only; no unilateral extension.

---

## 7. Errors

`apps/api/app/narrative_core/errors.py` — `NarrativeCoreErrorCode` values including  
`MIGRATION_CHECKSUM_MISMATCH`, `SNAPSHOT_*`, `INVALID_RUN_SCOPE`, `BOOK_SCOPE_REQUIRES_SNAPSHOT`, `RANGE_SCOPE_*`, `DUPLICATE_STAGE_KEY`, `INVALID_STAGE_TRANSITION`, `COMPLETED_STAGE_CANNOT_RETRY`.

---

## 8. Hash canonicalization

1. CRLF / CR → LF  
2. No Unicode NFC/NFKC  
3. Do not strip meaningful whitespace  
4. SHA-256 hex of UTF-8 bytes  
5. Never use `hash()`  

---

## 9. Dependencies

- Agent B `validate_run_scope` / book scope **requires** Agent A `SnapshotValidationGateway`  
- Integration merges A then B then C, then runs cross-module tests  
- Agent C must **not** modify `models.py` or migrations  

---

## 10. Forbidden in Phase 1P / Agent scopes

- Whole-book model calls / prompts  
- Narrative assets / FTS5 / Neo4j  
- Changing Reader Journey / Scene / Hook algorithms  
- Shipping Pro (`PRO_CAPABILITIES_SHIPPED`)  
- VERSION bump / tag rewrite / push / installer  
- Full hash backfill of production data in 1P (Agent A may implement backfill service later on temp DBs)
