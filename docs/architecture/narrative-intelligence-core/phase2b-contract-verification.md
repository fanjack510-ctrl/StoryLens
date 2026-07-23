# Phase 2B Contract Verification

Phase 2B-P verification checklist (CHG-036). Directed tests only. Matches brief §33 (61 items).

## Automated

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest apps/api/tests/test_narrative_phase2bp_contract.py -q --noconftest
python scripts/version_manager.py check
python scripts/change_registry.py check
git diff --check
```

## 61 verification items

1. Private Manifest
2. Manifest schema/version
3. Engine signature invalid
4. Engine protocol incompatible
5. App version incompatible
6. Production does not degrade to Mock
7. Loader Fake
8. Provider Gateway
9. Credential never enters DTO
10. Prompt Pack Manifest
11. Prompt hash
12. Prompt body never enters Artifact
13. Source data / instruction isolation
14. Context Bundle
15. Snapshot hash
16. Chapter hash
17. Context Unit ordering
18. No cross-Snapshot mix
19. Evidence Candidate
20. Evidence hash
21. Evidence offset
22. Derived summary not final Evidence
23. Module Registry
24. Stage Registry
25. Execution Spec
26. Planning / Producer / Result Dependency consistency
27. Four Module Specs
28. Structure not forced three-act
29. Overview not forced single protagonist
30. Chapter Function multi-label
31. Storyline multi-membership
32. Module Runner Protocol
33. Fake Runner
34. Output Validator
35. Invalid schema
36. Invalid reference
37. Evidence insufficient
38. Candidate only
39. No canonical write
40. Native mode
41. Enhanced degrade
42. Quality Profile
43. Analysis Mode vs Quality Profile separation
44. Data Handling Consent
45. Checkpoint compatibility
46. Budget / Usage
47. Error Code uniqueness
48. zh/en Language Contract
49. Evaluation Case
50. Metamorphic Case
51. No formal Prompt
52. No model calls
53. Formal Run still disabled
54. `PRO_CAPABILITIES_SHIPPED=false`
55. `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
56. `PRODUCTION_DEFAULT_ENGINE_ID=None`
57. Mock Lab default `false`
58. No new Migration
59. `version_manager` check
60. `change_registry` check
61. `git diff --check`

## Forbidden during verification

- Full Pytest / Vitest
- Production / Windows build
- publish / push

## Status target

- CHG-031 → `verified` (unchanged)
- CHG-032–035 → remain `tested` (do not mark verified without manual Mock Lab acceptance)
- CHG-036 → `tested` max (not ready/released)
- CHG-037–040 → `registered`
