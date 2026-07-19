# Phase 1D-B2 Final Certification Report v1

**Verdict:** `REAL_CANARY_PASSED`  
**Batch:** `phase-1db2-r13-20260719T022027Z`  
**Database:** `canary-v13.sqlite3`  
**Sealed at:** 2026-07-19T03:31:19.394125+00:00

## Summary

- 8/8 full pipeline runs PASS
- Provider `aliyun_qwen_plus` / model `qwen3.7-plus` / auto_route=`False`
- HTTP requests: 164 (reported=163, conservative=1, unknown=0)
- Certification accounted cost: **1.85226 CNY** (cap 100)
- Reader Journey Profiles: 48; evidence_paragraph_ids max=16; over16=0
- Main DB invariance: unchanged_counts=True, sha_equal=True
- Checker: PASS; `phase_1d_c_allowed=True`

## Fixture plan

| Run | Fixture | Repeat |
|-----|---------|--------|
| 1 | C3-long-action | None |
| 2 | A2-medium-action | None |
| 3 | B2-medium-description | None |
| 4 | A1-short-dialogue | None |
| 5 | B3-long-payoff | None |
| 6 | C1-short-info | None |
| 7 | C3-long-action | 1 |
| 8 | B3-long-payoff | 5 |

## Versions

```json
{
  "scene_analysis_prompt": "v3.2",
  "reader_journey_scene_prompt": "v1.6",
  "reader_journey_scene_contract": "1.3",
  "reader_journey_chapter_prompt": "v1.2",
  "reader_journey_chapter_contract": "1.2",
  "transport_retry": "v1.0.4",
  "journey_repair_resilience": "v1.0.5",
  "journey_targeted_repair": "v1.0.6",
  "journey_adaptive_phase_contract": "v1.0.7",
  "canary_conservative_usage_accounting": "v1.0.8",
  "scene_analysis_provider_recovery": "v1.0.9",
  "global_model_invocation_policy": "v1.1.0",
  "reader_journey_evidence_budget": "v1.1.1",
  "change_package": "reader-journey-evidence-budget-change-v1.1.1"
}
```

## Change packages

- `single-chapter-pipeline-change-v1.0.1`
- `single-chapter-journey-change-v1.0.2`
- `single-chapter-journey-change-v1.0.3`
- `provider-transport-change-v1.0.4`
- `journey-repair-resilience-change-v1.0.5`
- `journey-targeted-repair-change-v1.0.6`
- `journey-adaptive-phase-contract-change-v1.0.7`
- `canary-conservative-usage-accounting-change-v1.0.8`
- `scene-analysis-provider-recovery-change-v1.0.9`
- `global-model-invocation-policy-change-v1.1.0`
- `reader-journey-evidence-budget-change-v1.1.1`

## Frozen file aggregate

`d492f69074f193fb196012a701378e852889b8c7d17fb2b3244dc6aceda8f4df`

See `phase-1db2-certified-file-hashes-v1.json`.

## Defect closure

DEFECT-CANARY-006 … 016 → all `CLOSED_VERIFIED` in `phase-1db2-defect-closure-register-v1.json`.

## Handoff

Phase 1D-C may proceed to Certified Single-Chapter Release Candidate validation **without** real model calls unless separately authorized.
