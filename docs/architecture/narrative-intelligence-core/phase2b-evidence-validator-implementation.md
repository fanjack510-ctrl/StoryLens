# Phase 2B Evidence Validator Implementation

## DefaultEvidenceValidator

File: `apps/api/app/narrative_core/services/whole_book_evidence_validator.py`

Checks: Book · Snapshot · Chapter · Paragraph · stable paragraph id · paragraph hash · offsets · role · target module · target output · context unit · derived/raw · duplicates

## Guarantees

1. No model calls
2. No database writes
3. No Asset mutation
4. No auto-canonical
5. Explicit codes for hash mismatch, offset OOB, missing target, cross-book, cross-snapshot
6. `from_derived_summary=True` → `DERIVED_SUMMARY_AS_FINAL_EVIDENCE`
7. Reuses Phase 2B-P `validate_evidence_candidate` plus Snapshot-backed extras
