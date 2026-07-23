# Phase 1D-P Evidence & Review Contract

Evidence refs + review actions. Builds on **Phase 1B** asset base.  
本阶段只定义 Contract / Adapter 边界；不实现正式编辑 UI。

## WholeBookEvidenceRefDto

| Field | Notes |
|-------|-------|
| `evidence_id` | |
| `evidence_type` | Asset Evidence / Relation Evidence |
| `book_snapshot_id` | |
| `snapshot_chapter_id` | |
| `snapshot_paragraph_id` | |
| `source_chapter_id` | |
| `source_scene_id` | optional |
| `stable_paragraph_id` | |
| `paragraph_content_hash` | jump integrity |
| `start_offset` / `end_offset` | |
| `evidence_role` | `support` / `contradict` / `context` |
| `evidence_label` | |
| `chapter_title` | |
| `paragraph_preview` | **short fragment only** |
| `deep_link` | chapter / scene / paragraph |
| `integrity_status` | see below |

### `integrity_status`

| Value | Meaning |
|-------|---------|
| `valid` | hash / availability ok |
| `stale` | Snapshot drift |
| `hash_mismatch` | paragraph content changed |
| `missing` | target gone |
| `inaccessible` | cannot read |

### Evidence rules

1. Preview = short fragment only; full body via Snapshot Reader on demand.
2. Click → deep-link to chapter / Scene / Paragraph.
3. Before jump: check paragraph hash; on mismatch **do not** silent-locate.
4. Old Snapshot Evidence remains viewable; never treat current body as old Evidence.
5. Support Asset Evidence and Relation Evidence.
6. Evidence Drawer does **not** write DB directly.

## NarrativeReviewActionRequest

| Field | Notes |
|-------|-------|
| `action` | see actions |
| `target_type` | asset / relation / conflict / … |
| `target_id` | |
| `expected_version` | concurrency guard |
| `actor` | |
| `correction_payload` | for `correct` |
| `evidence_changes` | |
| `resolution_payload` | for conflict resolve |
| `reason` | |
| `idempotency_key` | |

### Actions

`confirm` · `correct` · `reject` · `lock` · `unlock` · `mark_stale` · `resolve_conflict` · `dismiss_conflict`

### Action rules

| Action | Rule |
|--------|------|
| `correct` | Creates **new** Version; never overwrite original Version |
| `confirm` | Requires Evidence gate before confirm |
| `reject` | Soft reject — **no** physical delete |
| `lock` | Applies to stable Asset / Relation |
| `unlock` | Must be explicit |
| `expected_version` | Prevents concurrent overwrite |
| Conflict resolve | Must carry `schema` / `version` |
| Audit | Every user action produces audit record or minimal audit contract |

### Hard frontend limits

- Frontend **must not** directly edit `is_canonical`.
- Confirm / correct / lock go through Phase 1B asset services / review action API.
- Public asset view & manual maintenance remain **not** Pro-gated.

See Phase 1B: [phase1b-evidence-contract.md](./phase1b-evidence-contract.md), [phase1b-review-lock-versioning.md](./phase1b-review-lock-versioning.md).
