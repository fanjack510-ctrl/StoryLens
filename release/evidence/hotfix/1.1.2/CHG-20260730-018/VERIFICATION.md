# CHG-20260730-018 Verification

## Fix
- Backend: active journey ⇒ recovery `user_status=running`; prefer active journey row over old recoverable interrupted; recover() no-ops when journey already active.
- Frontend: suppress UnifiedAnalysisRecoveryCard / progress-panel recovery while journey is active; invalidate recovery-plan query on active transition.

## Tests
- Vitest: PASS
- Pytest: PASS (3)
- Real provider: 0
- Formal DB writes: 0

## Status
`tested` — not verified; no Build / Push / Tag / Release / VERSION change.
