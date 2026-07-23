# Phase 1B — Relation Evidence Implementation (Agent F)

**Change:** CHG-20260723-019  
**Owner:** Agent F  
**Table:** `narrative_relation_evidence`  
**Contract:** `phase1b-evidence-contract.md` (shared with Asset Evidence — no second contract)

## Binding

Evidence binds a **Relation Version** (`relation_version_id`), not only the stable Relation id.

## Validation (reuse Phase 1A Snapshot)

`NarrativeRelationServiceImpl.attach_relation_evidence` / `validate_relation_evidence`:

1. `book_snapshot_id` required → Snapshot must be `COMPLETED` and book must match Relation book (`SnapshotValidationGateway.validate_snapshot_for_book`).
2. `snapshot_paragraph_id` required (never null); chapter/paragraph must belong to the Snapshot.
3. `paragraph_content_hash` must equal Snapshot paragraph hash.
4. Offsets inside paragraph text recovered via `get_snapshot_paragraph_text` — **no second body reader**.
5. `source_scene_id` optional.
6. `evidence_role`: `support` | `contradict` | `context`.
7. No full user body stored on the Evidence row; labels truncated.

## Canonical gate

- Canonical Relation Version requires ≥1 `support` Evidence.
- `contradict` Evidence may coexist.
- `context` alone cannot make a Version canonical.
- Locked Relation Evidence is never silently deleted (no model delete API).

## APIs

- `attach_relation_evidence(...)`
- `validate_relation_evidence(evidence_id)`
- `list_relation_version_evidence(relation_version_id)`
