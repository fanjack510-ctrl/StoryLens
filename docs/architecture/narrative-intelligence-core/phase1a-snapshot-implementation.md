# Phase 1A Snapshot Implementation

**Change:** CHG-20260723-012  
**Owner:** Agent A  
**Branch:** `feature/narrative-phase1a-snapshot`

## Hash rules

Reuse Phase 1P `canonicalize_text` / `calculate_text_hash`:

- CRLF / CR → LF  
- No Unicode NFC  
- SHA-256 hex of UTF-8  
- Never `hash()`  

### Persistence

- Paragraph `content_hash` ← hash(`normalized_text`)
- Chapter `content_hash` ← hash(paragraphs joined by LF)
- Book aggregate hash ← length-prefixed records  
  `{order}:{title_len}:{title}:{chapter_content_hash}` joined by LF, then SHA-256  
  (avoids boundary ambiguity; includes order + title + chapter hash)

Protocol `calculate_book_content_hash(chapter_hashes)` remains implemented with length-prefixed hash lines for contract compliance. Snapshot `content_hash` uses the richer aggregate form.

Import/reparse hook: `ContentHashServiceImpl.refresh_hashes_after_import_or_reparse(book_id)`.

## Snapshot lifecycle

```text
create_or_reuse_snapshot(book_id)
  → backfill hashes + compute book aggregate hash
  → reuse COMPLETED (book_id, content_hash) if present
  → else BUILDING row (unique constraint)
  → copy immutable chapter content_text + paragraph offsets
  → integrity validate
  → COMPLETED  |  FAILED on error
```

### Concurrency

Unique `(book_id, content_hash)` + `IntegrityError` after savepoint → read winner; wait briefly if BUILDING; rebuild FAILED/stale in place. Not process-memory-lock only.

### Immutability

- Snapshot creation does not rewrite live Book/Chapter/Paragraph body text.
- Does not delete user source files.
- After COMPLETED, business layer must not mutate snapshot content; integrity failure may mark `INVALID`.

### Paragraph restore

`content_text[start_offset:end_offset]`; offsets must be in range; restored text hash must equal stored paragraph `content_hash`.

## Agent B surface (`SnapshotValidationGateway`)

| Method | Behavior |
|--------|----------|
| `get_completed_snapshot(snapshot_id)` | Only `COMPLETED` + integrity OK |
| `validate_snapshot_for_book(snapshot_id, book_id)` | Completed + `book_id` match |

BUILDING / FAILED raise `SNAPSHOT_NOT_COMPLETED`.

## Files

- `services/hash_backfill.py`
- `services/snapshot_repository.py`
- `services/snapshot_service.py`
- Tests: `test_narrative_hash_backfill.py`, `test_narrative_snapshot_service.py`
