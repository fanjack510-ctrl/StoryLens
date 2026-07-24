# Phase 2B-R Known Limitations

**Change:** CHG-20260723-044 (post-integration)

1. **No Live Smoke** — status capped at `tested`; `verified` requires manual book run (estimate/consent/Evidence/cancel/budget).
2. **Private package optional on public CI** — four-module Lab path needs `storylens_private_engine` importable; Fake path remains default.
3. **Lab dry by default** — Bailian adapter `dry_run=True`; live HTTP only behind explicit Lab + live-probe env (not exercised here).
4. **Formal Run still disabled** — `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`; Private Lab ≠ product entry.
5. **Candidate-only persistence** — Phase1B sink never auto-confirm/lock/canonical overwrite; no new tables.
6. **First four modules only** — remaining whole-book modules not wired.
7. **Private Prompt bodies** stay in private repo; public Fake prompt pack remains for default tests.
8. **Gates frozen** — no Pro ship, no production default engine, Mock Lab & Private Lab default false.
