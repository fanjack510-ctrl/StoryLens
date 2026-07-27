# Phase 1D Contract Verification

Phase 1D-P verification checklist (CHG-026). Section 二十二 — 30 items.

## Automated

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest tests/test_narrative_phase1dp_contract.py -q --noconftest
python scripts/version_manager.py check
python scripts/change_registry.py check
git diff --check
```

## 30 verification items

1. Preflight DTO (`WholeBookPreflightPageModel` / backend preflight fields)
2. Native / Enhanced mode (`whole_book_native` / `whole_book_enhanced`)
3. Module Key uniqueness (11 keys)
4. Module dependency table / auto-fill rules
5. Stage dependency (module ≠ hard 1:1 stage bind)
6. Run status enum (`pending`/`running`/`paused`/`interrupted`/`completed`/`failed`/`cancelled`)
7. `allowed_actions` Contract (backend-authored)
8. Stage progress DTO (`WholeBookStageProgressDto`)
9. Result Envelope (`WholeBookResultEnvelope`)
10. Module status enum semantics
11. 11 Module Result DTO imports
12. Evidence DTO (`WholeBookEvidenceRefDto`)
13. Evidence `integrity_status` values
14. Review Action (`NarrativeReviewActionRequest`)
15. `expected_version` concurrency field
16. Conflict Center (`ConflictCenterItemDto`)
17. Structure Map Projection DTO
18. Pattern DTO does **not** map directly to ORM / no Pattern tables
19. Frontend ↔ backend Capability Key consistency
20. Frontend ↔ backend Module Key consistency
21. Frontend ↔ backend status enum consistency
22. Fixture Guard
23. Run creation still disabled (`WHOLE_BOOK_RUNS_ENDPOINT_DISABLED` semantics)
24. `PRO_CAPABILITIES_SHIPPED=false`
25. `WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true`
26. Legacy Phase 1C API modules still import
27. Legacy asset services not Pro-gated
28. `version_manager` check
29. `change_registry` check
30. `git diff --check`

## Forbidden during verification

- Full Pytest / Vitest suite
- Production / Windows build / Smoke
- publish / push

If TypeScript typecheck mutates:

- `apps/desktop/tsconfig.app.tsbuildinfo`
- `apps/desktop/tsconfig.node.tsbuildinfo`

→ restore those files.

## Manual

- [ ] Ownership JSON paths match disk intent
- [ ] README Phase 1D-P links resolve
- [ ] CHG-026 ≤ `tested`; CHG-027–030 remain `registered`
- [ ] No force-start control in Preflight contract docs

Status target after contract tests pass: CHG-026 → `tested` (not ready/released).
