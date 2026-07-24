# Phase 2B Module Candidate Builder

Class: `ModuleCandidateBuilder`

## Outputs

- `AssetCandidateCommand`
- `RelationCandidateCommand`
- `EvidenceCandidateCommand`
- `ConflictCandidateCommand`
- `StageArtifactPayload`

## Rules

1. Commands/DTOs only — no ORM.
2. Candidate-only `review_status`.
3. `mock=false` reserved for future real-engine fixtures; Agent R Fake path remains synthetic.
4. Output fingerprint + run/stage/snapshot/module/engine/prompt versions required via `CandidatePersistenceContract`.
5. Evidence refs attached.
6. No auto confirm / lock / canonical overwrite.
7. Rejected validation → empty build (`rejected=true`).
