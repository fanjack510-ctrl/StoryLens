# Phase 1C Contract Verification

Phase 1C-P verification checklist (CHG-021).

## Automated

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest apps/api/tests/test_narrative_phase1cp_contract.py -q --noconftest
python scripts/version_manager.py check
python scripts/change_registry.py check
git diff --check
```

## Test coverage (16 cases)

1. Protocol imports (`CapabilityService`, `WholeBookAnalysisEngine`, registry)
2. Request DTO — snapshot required, capability denied
3. Native / enhanced modes in mock engine plan
4. Stage catalog — unique keys, dependency DAG
5. `WholeBookStageResult` shape
6. Registry register mock + `health_check`
7. Capability keys unique; match `keys.ts`
8. `shipped=false` → `CAPABILITY_NOT_SHIPPED`
9. `CapabilityDecision` / `QuotaDecision` fields
10. Legacy mapper conflict-free
11. WholeBook error codes in `NarrativeCoreErrorCode`
12. Foundation capability not Pro-gated
13. `PRO_CAPABILITIES_SHIPPED=false` in `productEdition.ts`
14. Mock `execute_stage` — no model
15. All registry keys present

## Manual

- [ ] Ownership JSON paths exist on disk
- [ ] No live whole-book run router registered
- [ ] CHG-022–025 `parallel_plan` populated

Status target after tests pass: CHG-021 → `tested`.
