# Phase 2A Idempotency & Concurrency

1. Create uses idempotency_key
2. Same key → same Run
3. History runs allowed for same Book/Snapshot/Config
4. Default ≤1 active Mock Run per Book
5. One Executor per Run
6. Actions use operation idempotency_key
7. State updates use expected_state/version
8. Replay must not duplicate Asset Version
9. Replay must not duplicate Artifact
10. Recovery must not re-init completed stages

Active = pending|running|paused|interrupted. failed does not occupy slot by default.
