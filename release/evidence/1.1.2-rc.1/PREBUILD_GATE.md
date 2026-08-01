# PREBUILD GATE — StoryLens 1.1.2-rc.1

- STATUS: PASSED (with noted typecheck pre-existing)
- RELEASE CHANGE: CHG-20260729-008
- INCLUDED: CHG-20260728-040, CHG-20260728-041, CHG-20260729-001..006, CHG-20260729-007
- RC1 BUILD SOURCE HEAD: 9eee79dcad676973fe1f44c5f45b97b39ba55b86 (+ gate hygiene pending commit)
- PRIVATE HEAD: 23a0b025db51acaa8e62f4e81bc7628f19a8e2a6
- VERSION (formal before RC override): 1.1.2
- RC VERSION: 1.1.2-rc.1
- RELEASE SCOPE: SINGLE CHAPTER ONLY
- TARGETED PYTEST HOTFIX: see gate-pytest-hotfix.txt
- TARGETED VITEST: 3 files / 13 passed
- TYPESCRIPT TYPECHECK: FAIL (pre-existing test fixture + BookRoutePage comparisons; Vite build does not require tsc -b)
- VERSION CHECK: PASS
- REAL PROVIDER CALLS: 0
- FORMAL DATABASE WRITES: 0
- GATE HYGIENE: status_version server_default=0 for create_all / migration test compatibility
