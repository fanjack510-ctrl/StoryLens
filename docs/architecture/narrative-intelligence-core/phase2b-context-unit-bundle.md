# Phase 2B Context Unit & Bundle

## WholeBookContextUnit fields

`unit_id`, `unit_type`, `book_snapshot_id`, `snapshot_chapter_id`, `snapshot_paragraph_ids`, `chapter_order`, `scene_id`, `stable_paragraph_ids`, `content_hash`, `text_ref`, `character_count`, `token_estimate`, `source_language`, `metadata`

## unit_type

`book` | `chapter` | `scene` | `paragraph_group` | `evidence_window` | `derived_summary`

## Context levels (Level 0–3)

| Level | Content |
|-------|---------|
| 0 | Full book metadata + chapter TOC |
| 1 | Chapter content refs + chapter summary refs |
| 2 | Scene / paragraph-group content refs |
| 3 | Evidence Window original-text refs |

Analysis may overview → chapter → evidence; final claims bind Level-3 original evidence.

## Binding / isolation rules

1. `text_ref` is on-demand — units do not default-carry full text
2. `derived_summary` must be marked derived
3. Derived summary cannot replace original evidence
4. Units cannot cross books
5. Units cannot mix snapshots
6. Context hash must be recomputable
7. Sort order deterministic
8. No book-specific split rules
9. Rules must apply across works
10. Long chapters use generic grouping (not single-book thresholds)

### Forbidden

Final evidence from chapter summaries alone; model summary as original text; unconditional full-body send to Provider; single-book threshold hardcodes; per-work special branches.
