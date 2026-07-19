# V1.0 Baseline — Database Schema Snapshot

**Source of truth:** `apps/api/app/db/models.py`  
**Migrations:** idempotent ALTER helpers in `apps/api/app/db/session.py` (no Alembic revision tree in repo)  
**Default URL:** `sqlite:///./data/storylens.db` (`STORYLENS_DATABASE_URL`)

## Tables (22)

| Table | Purpose |
|-------|---------|
| `books` | Imported novel metadata + optional source bytes + diagnostics |
| `chapters` | Chapter index/title/word counts |
| `paragraphs` | Stable paragraph IDs + text spans |
| `reparse_audits` | Reparse history |
| `analysis_runs` | Pipeline run lifecycle, errors, progress |
| `scenes` | Scene ranges tied to run / boundary revision |
| `analysis_artifacts` | Validated JSON payloads (boundary, scene analysis, journey profiles) |
| `analysis_evidence` | Field → paragraph_id citations |
| `model_invocations` | Full model call audit log |
| `boundary_detection_batch_checkpoints` | Resumable boundary batches |
| `request_gate_decisions` | Budget gate audit |
| `cloud_budget_reservations` | Staged cloud budget ledger |
| `provider_configurations` | Per-provider runtime overlay |
| `application_settings` | Key-value JSON settings |
| `boundary_review_sessions` | Human boundary review sessions |
| `boundary_review_decisions` | Accept/reject/manual decisions |
| `boundary_revisions` | Immutable confirmed boundaries |
| `reader_journey_runs` | Journey run lifecycle |
| `scene_reader_journey_profiles` | Per-scene journey profiles |
| `reader_journey_phases` | Chapter phase segments |
| `chapter_reader_journey_summaries` | Chapter synthesis |
| `reader_journey_revisions` | Reserved for manual journey edits |

## Core relationships

```
Book 1──* Chapter 1──* Paragraph
Book 1──* Scene
AnalysisRun 1──* Scene / Artifact / ModelInvocation / Checkpoint
AnalysisRun 1──* BoundaryReviewSession 1──* Decision
BoundaryReviewSession 1──* BoundaryRevision 1──* Scene
AnalysisRun 1──* ReaderJourneyRun 1──* Profile / Phase
ReaderJourneyRun 0..1── ChapterReaderJourneySummary
```

See full field-level documentation: `docs/architecture/06-database-design.md`.
