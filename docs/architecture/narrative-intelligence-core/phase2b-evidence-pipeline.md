# Phase 2B Evidence Pipeline

## Types

- `EvidenceCandidate`
- `EvidenceSelectionResult`
- `EvidenceValidationReport`
- `EvidenceCoverageReport`

## EvidenceCandidate fields

`candidate_id`, `book_snapshot_id`, `snapshot_chapter_id`, `snapshot_paragraph_id`, `stable_paragraph_id`, `paragraph_content_hash`, `start_offset`, `end_offset`, `evidence_role`, `target_module_key`, `target_output_ref`, `extraction_method`, `confidence`, `source_context_unit_id`

## evidence_role

`support` | `contradict` | `context`

## Validator checks

1. Snapshot consistency
2. Chapter consistency
3. Paragraph exists
4. Paragraph hash
5. Offset bounds
6. Preview integrity
7. Evidence role
8. Target output exists
9. No cross-book
10. **Derived summary cannot be final original evidence**

## Policy

Important conclusions require evidence; without evidence stay incomplete/candidate; insufficient evidence never auto-canonical; contradictory evidence → Conflict Candidate. Validator does not call models and does not mutate asset state.
