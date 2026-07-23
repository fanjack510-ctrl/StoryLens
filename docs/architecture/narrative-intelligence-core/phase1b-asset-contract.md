# Phase 1B-P — Narrative Asset Contract

**Change:** CHG-20260723-016  
**Status ceiling:** tested  
**Baseline:** VERSION `1.0.5` @ `fc25a984f243d641d91c11d887d07af8b3625fdd`

## Purpose

Freeze the shared Narrative Asset data model so Agents D / E / F can implement in parallel without rewriting `models.py`.

## Core principles

1. Narrative Asset base is a **public** capability — no Pro gating.
2. Model output becomes a **candidate version**, never auto user fact.
3. Stable identity ≠ analysis interpretation.
4. Assets and Relations are **versioned**.
5. Evidence binds a **COMPLETED Book Snapshot** + `paragraph_content_hash`.
6. User confirmed / corrected content is not overwritten by a new Run.
7. **Lock** is orthogonal to `review_status`.
8. Pattern Map is a derived visualization — **no** Pattern tables in this phase.
9. Old Reader Journey / Hook / Scene JSON stay unchanged; **no** dual-write or backfill.
10. No FTS5 / Neo4j / vector DB.

## Tables (skeleton)

| Table | Role | Owner |
|-------|------|-------|
| `narrative_assets` | Stable asset identity (`asset_key`) | Agent E |
| `narrative_asset_versions` | Interpretation + review + canonical flag | Agent E |
| `narrative_asset_evidence` | Version-bound Snapshot evidence | Agent E |

Related: Entity (Agent D), Relation / Conflict (Agent F) — see sibling contracts.

## `asset_key`

- Stable recognition of the same narrative asset across runs.
- Must **not** use DB autoincrement alone or Python `hash()`.
- Must **not** embed mutable model summaries.
- Helper: `app.narrative_core.asset_key.build_asset_key(...)` (SHA-256).
- Complex disambiguation deferred to Agent E.

## Canonical rules

1. `candidate` never auto-becomes canonical.
2. `confirmed` / `corrected` may become canonical.
3. `rejected` must not become canonical.
4. At most one `is_canonical=1` per `asset_id` (partial unique index).
5. Switch is transactional: clear old canonical, set new, same transaction.
6. Locked Asset: model may add candidates but must not switch canonical; conflicts → `analysis_conflicts`.
7. Old versions are retained forever (no overwrite).

## Protocol

`NarrativeAssetService` in `apps/api/app/narrative_core/contracts/asset.py`.

## Out of scope

Whole-book analysis, model calls, dual-write, history backfill, Pattern tables, Pro pages.
