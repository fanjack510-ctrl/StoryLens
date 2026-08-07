# REAL_OUTPUT_SAMPLE_REVIEW — CHG-20260807-054

短样本：明朝那些事儿（前 6 章）
Run：1 / formal / completed

## Overview
- 9 claims 齐全（`sample_overview_claim_count=9`）
- result_origin=formal；claims 绑定 materialize 后的 entity/asset/evidence ids

## Characters / Events
- 真实执行：`GatewayWindowAnalysisTransport` → orchestrator unit `window:1` → materialize
- **不是** Fixture-only / 静态 materialize / Overview 假生成 / 旧 Asset 重用
- entity_count=8；asset_version_count=24

## Structure
- StructureStagesResultV2；stage `synthesize_structure_stages=completed`
- coverage_scope 绑定 full_selected_range（与 Free pipeline expected scope 一致）

## Chapter Functions
- ChapterFunctionsResultV2；stage `synthesize_chapter_functions=completed`
- 与 Overview/Structure 同 Run / Snapshot / Revision

## Project Result / Finalize
- stages `project_result` + `finalize` completed；run.status=completed
