# INCIDENT_SNAPSHOT — INC-20260728-002

## Summary

Read-only freeze of the formal installed StoryLens 1.1.1 environment for Task #3 structured-output truncation.

## Paths

| Role | Path |
|------|------|
| Formal install | `C:\Users\msi\AppData\Local\StoryLens\` |
| Formal DB | `C:\Users\msi\AppData\Local\StoryLens\database\storylens.db` (+ wal/shm) |
| Formal logs | `C:\Users\msi\AppData\Local\StoryLens\logs\` |
| Incident copy (local only, not committed) | `D:\StoryLensIncident\INC-20260728-002-structured-output-truncation\` |

## Copy method

- Binaries: standard file copy
- DB/WAL/SHM/logs: `FileShare.ReadWrite` stream copy (process had locks)
- Config: formal `config\` directory empty/absent at snapshot time; no credential files copied into git evidence
- Formal AppData: **not written** by this step (copies are outbound only)

## Local copy inventory (hashes of copies)

| Relative path | Size | SHA256 |
|---------------|------|--------|
| binaries/storylens-api.exe | 39085482 | 81824128B119EB3A25392AD3D44714B0883CD111282B4A2FD7C0FA8EB91D48A7 |
| binaries/storylens-desktop.exe | 13086720 | 263BB44C92904574029A4AC1DDE23B2AE212B2D21835ADFE98AEE2D5ADAE3C0E |
| database/storylens.db | 39682048 | E5626A3DA7FEEC2323D61196B489E5E9322D660A91DC61ADF620C11D99B03460 |
| database/storylens.db-wal | 4466112 | 4FC2989BB55266EF530223FC126607C4D8D6D00BB2DC7B92C87294F3BBA3C97B |
| database/storylens.db-shm | 32768 | C927B9D88BD55FB2E52AE7B408CEF6B48FD86210159F9F0CE6CDD0C47C22849B |
| logs/sidecar.log | 13031955 | 63CAE188005A65360C271F3369CC256A725D67888FB60A1F741977E5296497B8 |
| logs/sidecar-stderr.log | 12956049 | 2A060393E72374E838BD850C9928E3C29BA3E31A1E424FF7C913F227344DE73B |

Copied at UTC: `2026-07-28T06:33:33Z`

## Formal AppData integrity

| Check | Result |
|-------|--------|
| Installed sidecar SHA matches 1.1.1 release evidence | YES |
| Installed GUI SHA matches 1.1.1 release evidence | YES |
| Formal DB last-write UTC (main file) | `2026-07-28T06:17:24.4734683Z` (pre-dates this investigation; later writes likely in WAL) |
| Formal AppData writes by this investigation | **0** |
| Secrets / full novel text / full provider responses committed | **NO** |

## Verdict

**INCIDENT SNAPSHOT: PASS**
