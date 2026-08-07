# MEDIUM_CHAPTER_FUNCTIONS — CHG-20260807-055

DATE：2026-08-07

## Completeness

| Field | Value |
|---|---|
| INPUT CHAPTERS | 42 |
| RESULT CHAPTERS | 42 |
| MISSING CHAPTERS | **0** |
| DUPLICATE CHAPTER RESULTS | **0** |
| INVALID ENUM COUNT | **0** |
| CF batches（actual） | 6（= ceil(42/8)） |

Allowed enums only：setup / escalation / climax / resolution / transition / side_story / flashback / empty / non_mainline / unknown.

## Primary distribution（full book）

See `MEDIUM_DEEP_REVIEW.json` → `cf_primary_dist`.

## Spot check（20 chapters）

Front 5 + mid ~10 + last 5 recorded in `MEDIUM_DEEP_REVIEW.json` → `cf_samples`.

- primary/secondary within allowed enum set
- no missing orders in sample set

## Verdict

CHAPTER FUNCTIONS：**PASS**
