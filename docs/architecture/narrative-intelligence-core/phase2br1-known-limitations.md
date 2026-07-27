# Phase 2B-R1 Known Limitations

- Automatic tests use Fake/Capturing Transport — not real model quality
- Formal Prompt quality not validated against production novels
- Real cloud cost not verified end-to-end
- Very long books / rate limits not load-tested
- Evidence rows have no independent `run_id` column (Version → run association)
- Private Sidecar packaging / installers not part of this Integration
- Live Smoke harness stops before HTTP create unless wired with a DB session
- `fallback_to_fake` remains available on Lab analysis runtime for module fixture paths;
  Live Provider path must not silently treat Fake success as live success
