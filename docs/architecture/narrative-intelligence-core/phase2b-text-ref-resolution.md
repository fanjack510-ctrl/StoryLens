# Phase 2B TextRef Resolution

## Types

- `SnapshotTextRef` — chapter / paragraph_group / evidence_window locator
- `SnapshotTextResolver` — explicit resolve only; hash + book + snapshot checks

## URI form

`snapshot://{kind}/book/{book_id}/snapshot/{snapshot_id}/chapter/{chapter_id}/paragraphs/{ids}/hash/{hash}[/off/{start}-{end}]`

## Rules

1. Context DTOs default to URI refs — no full body.
2. Resolve requires completed Snapshot belonging to Book.
3. Hash mismatch raises typed error.
4. Offsets validated for evidence windows.
5. Paragraphs cannot cross chapter or Snapshot.
6. Logs record kind/ids/char counts only — never full text.
7. Resolved text is never written into Artifacts by this layer.
8. `clear_cache()` after tests / process teardown; cache size limited.
