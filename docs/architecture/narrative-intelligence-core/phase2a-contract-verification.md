# Phase 2A Contract Verification

Phase 2A-P verification checklist (CHG-031). Directed tests only.

## Automated

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest apps/api/tests/test_narrative_phase2ap_contract.py -q --noconftest
python scripts/version_manager.py check
python scripts/change_registry.py check
git diff --check
```

## 37 verification items

1. Mock Lab default disabled
2. production environment rejected
3. non-loopback rejected
4. missing marker rejected
5. non-Mock Engine rejected
6. Create Request DTO
7. idempotency shape
8. Snapshot completed precheck
9. Run metadata schema
10. Run state transitions
11. illegal transitions rejected
12. expected_state required
13. Stage lifecycle catalog
14. completed stages do not rerun (rule)
15. retry attempt impact
16. cancel rules
17. Executor Protocol methods
18. Task Registry Protocol
19. one run → one task (fixture)
20. Polling Policy floor
21. Partial Results gate
22. Recovery plan explicit-resume
23. checkpoint schema/version
24. Engine version mismatch decision
25. Quota vs Cloud Budget separation
26. Error codes unique
27. Audit event shape
28. FE/BE run status parity
29. FE/BE error code parity
30. Formal run create still disabled
31. `PRO_CAPABILITIES_SHIPPED=false`
32. `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
33. `PRODUCTION_DEFAULT_ENGINE_ID=None`
34. No new Migration
35. `version_manager` check
36. `change_registry` check
37. `git diff --check`

## Forbidden during verification

- Full Pytest / Vitest
- Production / Windows build
- publish / push

## Status target

- CHG-031 → `tested` (not ready/released)
- CHG-032–035 remain `registered`
- CHG-027–030 → `verified`
