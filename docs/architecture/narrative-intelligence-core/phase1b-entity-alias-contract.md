# Phase 1B-P — Narrative Entity / Alias Contract

**Owner:** Agent D (CHG-20260723-017)  
**Migration:** `20260723_006_narrative_entities_aliases`

## Stable identity

`narrative_entities` stores identity only:

- `entity_type` (extensible string contract; minimum: character, location, organization, faction, object, concept, timeline_entity, unknown)
- `canonical_name` / `normalized_name`
- `lifecycle_status`: `active` | `superseded` | `archived`
- `is_locked` / `locked_at` (orthogonal to Alias review)

Do **not** put `candidate` / `confirmed` on Entity lifecycle.

## Alias

`narrative_entity_aliases`:

- Unique `(entity_id, normalized_alias)`
- Alias never overwrites `canonical_name`
- Model discoveries → Alias **candidates** via `add_alias_candidate`
- `review_status`: candidate | confirmed | rejected

## Protocol

`NarrativeEntityService` (`contracts/entity.py`):

- `create_entity`, `add_alias_candidate`, `confirm_alias`, `reject_alias`
- `lock_entity`, `unlock_entity`, `find_entity_by_alias`
- `merge_entities` — semantic frozen only; complex merge not implemented in Phase 1B-P

## Forbidden

Book-specific custom entity types; treating Alias as canonical rename without explicit user action.
