# CHG-20260731-023 Verification Notes

## Auto gate (pre-manual)

- Succeeded + stale interrupt fields → page view `completed`; recovery card / continue hidden (Vitest A/E).
- Continue → single `resumeReaderJourney`; zero `analysisRecoveryApi.recover` (Vitest B/F).
- Backend resume on running/succeeded → 202 idempotent, no new run/task (pytest G).
- Typecheck new errors: 0 (base 25 / final 25).
- HTTP E2E fixtures seeded on isolated DB; resume succeeded idempotent 202×2.

## Manual gate (pending)

MG-CHG-20260731-023 MANUAL UI ACCEPTANCE — Fixture A + Fixture B must both pass before RC.6 build.

Status: **tested** (not verified).
