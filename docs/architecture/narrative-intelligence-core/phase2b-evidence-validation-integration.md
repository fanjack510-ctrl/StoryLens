# Phase 2B Evidence Validation Integration

**Change:** CHG-20260723-040
**Modules:** `evidence_validator_runtime_adapter.py`, `whole_book_evidence_validator.py`, `whole_book_module_output_validator.py`

## Bridge (Integration)

`DefaultEvidenceValidatorRuntimeAdapter` satisfies Agent R `EvidenceValidator` Protocol while delegating to Agent Q `DefaultEvidenceValidator`:

| Protocol method | Delegates to |
|---------------|--------------|
| `validate(candidates, ctx)` | `DefaultEvidenceValidator.validate(candidates, view)` |
| `register_view(view)` | Snapshot-scoped `EvidenceValidatorSnapshotView` cache |

View resolution order:

1. `views_by_snapshot[book_snapshot_id]`
2. Registered `snapshot_view` if snapshot matches
3. Synthesized view from `EvidenceValidationContext` (fixture/unit path)

Composition root wires adapter into `DefaultModuleOutputValidator(evidence_validator=evidence_adapter)`.

## Snapshot view registration

E2E scenarios requiring paragraph-hash validation call:

```python
validator = DefaultEvidenceValidator(validatorsession)
view = validator.build_view_from_session(book_id=..., book_snapshot_id=...)
runtime.register_evidence_view(view)
```

Without registration, fixture path may synthesize view — insufficient for hash mismatch tests.

## Output validation gates

`DefaultModuleOutputValidator.validate` checks:

| Gate | Rejection markers (Fake E2E) |
|------|------------------------------|
| Schema | `schema_error` |
| References | `invalid_ref` |
| Evidence sufficiency | `evidence_insufficient`, bad paragraph hash |
| Snapshot binding | `snapshot_mismatch`, `cross_book` |
| Duplicates / conflicts | `duplicate`, `conflict` |

`require_evidence_for_acceptance=True` enforces evidence on acceptance path. Test `test_scenario_validation_rejection` covers seven rejection markers plus bad hash.

## Coverage report

After validation, `build_coverage_report` produces required/evidenced claims ratio attached to `ModulePipelineResultDTO.evidence_coverage`. Q `EvidenceCoverageCalculator` remains available for harnesses; not bypassed.

## Privacy

Evidence validation uses paragraph IDs and content hashes only — no full paragraph bodies in validation reports. Context bundle public dict excludes `full_text` (mapper round-trip test).

See [phase2b-evidence-validator-implementation.md](./phase2b-evidence-validator-implementation.md), [phase2b-evidence-pipeline.md](./phase2b-evidence-pipeline.md).
