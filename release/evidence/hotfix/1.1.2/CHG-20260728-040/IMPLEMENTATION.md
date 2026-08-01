# IMPLEMENTATION — CHG-20260728-040

## Scope delivered

Public:
- Output-bounded adjudication batching (`MAX_TARGET=10`, context-only neighbors)
- `compute_scene_boundary_output_budget_v1` (no fixed 768 for adjudication)
- Adaptive truncation retry with strictly increasing limits
- AnalysisArtifact checkpoints for validated batches (no migration)
- API progress + usage aggregation fields
- TasksPage boundary progress + usage copy
- Prompt `scene_boundary_adjudication` v1.1.2

Private:
- Pure helper mirror under `storylens_private_engine.scene_boundary`
- Parity unit test

## Not done / boundaries

- No VERSION / installer / push / real provider
- No merge into `hotfix/1.1.2`
- Vitest ran via junctioned node_modules from integration worktree
