# Phase 1A Migration Ledger Implementation

**Change:** CHG-20260723-012  
**Owner:** Agent A  
**Branch:** `feature/narrative-phase1a-snapshot`

## Scope

Implements `MigrationLedger` against Phase 1P frozen migration IDs:

| migration_id | Role |
|--------------|------|
| `baseline_1_0_5` | Baseline marker (legal registration / checksum reject) |
| `20260723_001_schema_migrations` | Create ledger table |
| `20260723_002_content_hashes` | Chapter/Paragraph `content_hash` |
| `20260723_003_book_snapshots` | Snapshot tables |

Agent A does **not** modify `20260723_004` / `20260723_005`.

## Components

- `apps/api/app/narrative_core/services/migration_ledger.py` — `MigrationLedgerService`
- `apps/api/app/narrative_core/migrations/runner.py` — checksum conflict / baseline invalid raise `NarrativeCoreError` (same codes; no ID/SQL renumber)

## Behavior

1. Ledger table ensured before read/write.
2. Checksum = SHA-256 of frozen SQL body (CRLF→LF), via `migration_checksum`.
3. Re-apply is idempotent when checksum matches.
4. Checksum mismatch → `MIGRATION_CHECKSUM_MISMATCH` (no overwrite).
5. Illegal baseline checksum → `MIGRATION_BASELINE_INVALID`.
6. Registration happens only after successful DDL path in runner; failed apply does not rewrite a conflicting row.

## Entry

`create_db()` still calls `apply_narrative_phase1p_migrations(engine)` (Phase 1P hook unchanged). Agent A services wrap/verify the same ledger.
