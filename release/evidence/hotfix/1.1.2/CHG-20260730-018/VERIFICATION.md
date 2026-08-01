# CHG-20260730-018 Verification

## Fix
- Backend: prefer Active Journey over stale recoverable; `user_status=running` while starting/running/resuming; recover returns `already_running` / `already_resuming` with zero new runs; plan details include cache key `{analysis_run_id, journey_run_id, confirmed_revision_id, status_version}`.
- Frontend Workflow Presentation: `is_journey_active` / `show_recovery_card` / `show_resume_action` / `show_stop_action`; Recovery Card §五 gates; cache key never `chapter_id` alone; Active copy §十.

## Tests
- Vitest: PASS (36)
- Pytest: PASS (6)
- HTTP E2E A/B/C: PASS
- Real provider: 0
- Formal DB writes: 0

## Status
`tested` — not verified; no Build / Push / Tag / Release / VERSION change.
