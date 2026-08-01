# DATA_MODEL_AUDIT 鈥?CHG-20260728-041

**Audited tree:** Public `fix/1.1.2-structured-output-truncation` / models shared with v1.1.1 lineage  
**Date:** 2026-07-28  
**Implementation status:** BLOCKED (CHG-040 not integrated)

## 1. BoundaryRevision 鈥?exists?

**Yes.** `BoundaryRevision` 鈫?`boundary_revisions`

Key columns today: `id`, `review_session_id`, `chapter_id`, `analysis_run_id`, `revision_number`, `final_boundaries_json`, `confirmed_by`, `confirmed_at`, `coverage_rate`.

**Gap:** no `status` (draft/confirmed/superseded/stale), no `source`, no `based_on_revision_id`, no `chapter_text_hash`, no `boundary_hash`, no draft rows. Revisions are **confirmed-only**.

## 2. UI 鈥滆竟鐣屼慨璁?#N鈥?
Tasks detail uses `boundary_revision_id` (table **PK**).  
Some APIs also expose `revision_number` (per-session sequence).  
These are **not the same integer**; product copy must be clarified in implementation.

## 3. Scene 鈫?revision

`scenes.boundary_revision_id` nullable FK.  
Assisted confirm path sets it; automatic scene pipeline may leave NULL.  
Scenes are effectively append-on-confirm (new rows), not in-place boundary edits.

## 4. Scene ID reuse across revisions

**Not reused.** New confirm 鈫?new `Scene.id` rows; `scene_key` embeds revision PK.  
CHG-041 must treat identity as **(revision_id, scene_id)** and reuse journey results by **input hash**, not bare scene_id.

## 5. Journey Task binding

`ReaderJourneyRun` has **no** `boundary_revision_id`, no `boundary_hash`, no frozen included-scene snapshot hashes.  
Enqueue uses live `load_revision_scenes(analysis_run_id)`.

**HIGH incompatibility** with required immutable journey binding.

## 6. Journey Result binding

`SceneReaderJourneyProfile` binds `scene_id` only. No revision/hash. No superseded journey status for chapter journey runs.

## 7. Auto-start Journey

After scenes complete: `chapter_analysis_completion.continue_chapter_after_scenes` 鈫?`ensure_auto_reader_journey_row` 鈫?`execute_reader_journey`.  
Also after boundary review confirm.  
CHG-041 must **interrupt** auto-skip of confirmation UI.

## 8. Scene analysis reuse key (today)

Artifacts keyed by `run_id` + `subject_id=str(scene.id)` + valid status 鈥?**not** content/boundary hash.  
Journey reuse for CHG-041 needs new `scene_journey_input_hash_v1`.

## 9. Paragraphs

`paragraphs.id` stable string PK; `paragraph_index` order; `content_hash` nullable. Suitable for paragraph-gap boundaries.

## 10. included_in_journey

**Absent.** All revision scenes enter journey today.

## 11. Draft

`BoundaryReviewSession` has pending/in_review/confirmed/鈥? 
**No** draft BoundaryRevision. UI 鈥滀繚瀛樿崏绋库€?is not a revision draft lifecycle.

## 12. Optimistic lock

**None** (no etag / If-Match on boundary APIs).

## 13. Journey stale/superseded

**Not** on `ReaderJourneyRun`. Required for CHG-041 result invalidation.

## 14. Migration pattern

Public uses named `migrate_phase_*` in `apps/api/app/db/session.py` (idempotent ALTER).  
Narrative ledger uses dated IDs (`20260725_011_鈥); next would be a new dated id if that lane is used.  
CHG-041 should prefer extending Public `migrate_phase_*` / ORM columns for chapter pipeline tables unless audit forces narrative migration.

## 15. Existing assisted boundary review

Full transition-decision review already exists (`boundary_reviews` API + `BoundaryReviewPanel`).  
CHG-041 product is a **post-scene partition editor** (move/add/delete split lines, exclude from journey), not a replacement for transition adjudication 鈥?must coexist without overwriting AI revision rows.

---

## Compatibility matrix vs product freeze

| Target | Current | Action |
|--------|---------|--------|
| draft/confirmed/superseded revision | confirmed-only | **EXTEND** schema + lifecycle |
| AI revision immutable | soft | **ENFORCE** write guards |
| Journey binds revision+hash | live load | **EXTEND** ReaderJourneyRun + gate |
| included_in_journey | missing | **ADD** field on revision scenes |
| boundary_hash | missing | **ADD** compute + store |
| Optimistic lock | missing | **ADD** etag |
| Auto journey start | yes | **CHANGE** to confirm gate |
| CHG-042 Task #4 | separate | **DO NOT TOUCH** |

## Migration necessity

**Likely YES** (minimal) for: revision status/source/hashes, included_in_journey, journey revision binding, journey superseded flag, draft etag.  
Exact migration ID deferred until implementation on integrated hotfix tip.

## Stop condition

No silent refactor performed. Implementation blocked until CHG-040 merge into `hotfix/1.1.2` completes.
