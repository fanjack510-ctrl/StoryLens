# Phase 2B Context Index

## WholeBookContextIndex

Process-local / computational index built from Context Units.

| Method | Behavior |
|--------|----------|
| `get_unit` | O(1) by unit_id |
| `list_units` | Deterministic order |
| `list_chapter_units` / `list_scene_units` | Filtered views |
| `resolve_text` | Delegates to bound `SnapshotTextResolver` |
| `locate_paragraph` | First structural unit covering paragraph id |
| `locate_evidence_window` | Match paragraph + offsets in metadata |
| `calculate_hash` | Recomputable from unit ids + hashes |
| `coverage` | Unit-type counts |

## Constraints

- `persistence = non-persistent`
- `is_fact_source = False`
- Rebuildable from Snapshot anytime
- Does not load all Evidence bodies up front
- Verified with 100 / 500 / 1000 chapter synthetic fixtures
- No search DB / semantic vectors; no cross-Book or cross-Snapshot mixing
