# MEDIUM_OUTPUT_REVIEW — CHG-20260807-055

DATE：2026-08-07

## Overview

Claims present for genre, core setting, protagonist（何晓月）, goals, main conflict, core question, final resolution, important characters, key events.
`result_origin=formal`，`provider_id=aliyun_qwen_plus`，`model_name=qwen3.7-plus`.

Spot-check：named entities from overview/entity list appear in source text（e.g. 何晓月、上官飞、叶秋水、柳晓青）.
No clear fabricated protagonist or inverted ending found in automated/manual light review.

| Field | Value |
|---|---|
| MAJOR HALLUCINATION COUNT | **0** |

## Characters / Events

- Entities sampled（≥5）：present in source text（see `MEDIUM_RUN.json` / `MEDIUM_DEEP_REVIEW.json`）.
- Materialization completed；asset versions created.
- Event assets are exposed via narrative asset materialization（overview key_event_asset_ids non-empty）.

## Structure

- Stage synthesis completed；product stage **PASS**.
- Observed stages use citation boundaries（start/end citation_ids）.
- Product DTO `chapter_range` showed `[null, null]` for sampled stages — **not** treated as L3 blocking product defect（citations present；no start>end / oob / severe reverse proven）. Classified **L3_OUTPUT_QUALITY / L3_NON_BLOCKING** observation for later polish if chapter-order ranges are required in UI.

## Stability（natural）

| Metric | Count |
|---|---|
| HTTP ERRORS | 0 |
| TIMEOUTS | 0 |
| MALFORMED OUTPUTS | 0 |
| SCHEMA FAILURES | 0 |
| TRUNCATIONS | 0 |
| RETRY CALLS | 0 |
| REPAIR CALLS | 0 |
| FAILED PROVIDER CALLS | 0 |

## Verdict

REAL OUTPUT QUALITY：**PASS**（with non-blocking structure chapter_range observation）
