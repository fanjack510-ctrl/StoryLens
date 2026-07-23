# Phase 1B Agent E — Asset Key Boundary

**Change:** CHG-20260723-018

## Frozen helper

Callers must use `app.narrative_core.asset_key.build_asset_key(...)` (SHA-256).  
`NarrativeAssetService.resolve_asset_key(...)` is a thin wrapper for Agent E call sites.

## Allowed inputs

| Input | Role |
|-------|------|
| `book_id` | Required isolation — different books never share a key |
| `asset_type` | Normalized type token |
| `identity_fingerprint` | Preferred stable business fingerprint from caller |
| `stable_label` | Fallback stable label (not mutable summary alone) |
| `disambiguator` | Optional stable suffix when collisions are known |

## Forbidden

- Python `hash()` (process-randomized)
- DB autoincrement alone as identity
- Embedding mutable model `title` / `summary` as the sole unique identity
- Novel-genre or character-specific merge heuristics
- Complex entity disambiguation / forced merge graphs

## Independent candidates

When no stable fingerprint can be determined, pass `independent=True` (or omit fingerprint/label).  
The service generates a unique unbound disambiguator (`independent:<token_hex>`) so a new Asset is created instead of forcing a merge.

## Stability guarantees

- Same `(book_id, asset_type, fingerprint[, disambiguator])` → same `asset_key`
- Same fingerprint across different `book_id` → different keys
- Key format: `na_` + first 32 hex chars of SHA-256 digest
