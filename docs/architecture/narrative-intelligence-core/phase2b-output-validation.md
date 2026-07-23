# Phase 2B Output Validation

## Ordered pipeline

1. Provider Response  
2. JSON/Schema Parse  
3. Module DTO Validation  
4. Reference Validation  
5. Evidence Validation  
6. Book/Snapshot Isolation  
7. Duplicate Detection  
8. Conflict Candidate Detection  
9. Candidate Asset/Relation Build  
10. Artifact Build  
11. Result Projection  

## On validation failure

- Do not auto-write Candidate
- Do not mark Artifact success
- Return stable error
- Keep safe diagnostic summary (no full model raw text)
- Retry only under allowed policy + budget

## ModuleOutputValidationReport

`schema_valid`, `references_valid`, `evidence_valid`, `snapshot_valid`, `duplicate_summary`, `conflict_summary`, `missing_fields`, `invalid_refs`, `evidence_coverage`, `warnings`, `accepted`, `retry_recommended`

`accepted=false` ⇒ no candidate persistence.
