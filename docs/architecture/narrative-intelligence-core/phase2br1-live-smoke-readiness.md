# Phase 2B-R1 Live Smoke Readiness

## Harness

- `scripts/private_whole_book_live_smoke.py`
- `scripts/run_private_whole_book_live_smoke.ps1`

## Defaults

- Dry-run
- Module: `book_overview` only
- No permanent env mutation
- No auto-delete of Runs
- Never prints body / prompt / credential

## Real Live requirements (all)

1. `environment` in {development, test}
2. `WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED=true`
3. loopback
4. `X-StoryLens-Private-Engine-Lab: 1`
5. `WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE=true`
6. `allow_network=true`
7. `lab_dry_run=false`
8–12. Credential, Consent, Estimate, Budget, Provider health

## Integration policy

This Integration **must not** execute real Live. Automatic tests only cover dry mode.
