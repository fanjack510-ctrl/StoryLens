# StoryLens Community V1.0 RC1

**Version:** `1.0.0-rc1`  
**Purpose:** Clean release-candidate workspace for Human UAT.

## Guarantees for this folder

| Item | Expected state |
|------|----------------|
| Database | **Empty** (no user books, no AnalysisRuns) |
| API Key | **None** configured |
| Developer Mode | **Off** by default |
| Qwen setup wizard | Shown on **first launch** when Key missing |
| Demo / sample book | **Not** auto-imported |
| Human UAT data | **Pending** — do not pre-seed |
| Real canary DB | **Not** included |
| Real model calls | **0** until the operator authorizes |

## How to use

1. Run repo bootstrap from the project root: `.\scripts\bootstrap.ps1`
2. Start: `.\scripts\start-dev.ps1`
3. Complete Qwen wizard with **your own** Aliyun Bailian API Key (BYOK).
4. Follow `audits/v1.0/v1.0-human-uat-checklist.md`.

## Do not

- Commit SQLite files from this folder to git
- Copy secrets into this README or any tracked file
- Publish to GitHub from automation
- Choose or invent a LICENSE here

## Related audits

- `audits/v1.0/v1.0-release-candidate-manifest.json`
- `audits/v1.0/certified-baseline/storylens-community-v1.0-certified-baseline.json`
