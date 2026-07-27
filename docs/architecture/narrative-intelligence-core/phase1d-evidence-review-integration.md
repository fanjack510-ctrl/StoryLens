# Phase 1D Evidence / Review Integration

## Evidence Read

- Service: `EvidenceReadService` (Agent L) over Phase 1B Snapshot Reader  
- Integrity: valid / stale / hash_mismatch / missing / inaccessible  
- Preview length capped; full body on demand; DTO does not long-term store full text  
- Mismatch blocks deep link navigation  
- Evidence Drawer is read-only (no DB writes)

## Review

- Adapter: `NarrativeReviewActionAdapter` (Phase 1B services underneath)  
- **Production write route not registered** (`POST /api/v1/narrative-review-actions`)  
- FE Review UI is prototype-only; must not call unregistered write endpoints  
- Frontend must not set `is_canonical` / `is_locked` directly

## Conflict Center

- Projector/service builds list items from Phase 1B conflicts  
- Blocking ≠ warning; blocking never auto-resolved  

Deferred to Phase 2E: formal review write HTTP + product page wiring.
