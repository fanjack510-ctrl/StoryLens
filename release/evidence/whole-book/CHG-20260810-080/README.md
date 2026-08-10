# CHG-20260810-080 Evidence

## CURRENT SHELL RESULT ROOT CAUSE

Skeleton copy such as:
- `阶段1` / `阶段 1`
- `悬念@1`
- `主角处于阶段起点`
- `第1至60章围绕目标、阻力与选择形成完整阶段`

comes from **E. local merge fallback** (`materialize_from_intermediates` in `pipeline.py`) after deterministic window extraction primitives (`悬念@`, `阶段起点`).

Formal hierarchical path previously allowed `force_local=True` when synthesis units failed, then persisted that scaffold as a completed formal V2 result **without** `result_origin=real_provider` tagging.

**Not** legacy migration / fixture / mock adapter for the formal Free create path after CHG-078 — the formal pipeline is Hierarchical V2, but local merge could still materialize scaffold text into the official result.

## Fixes in CHG-080
- Formal gateway sets `disallow_local_merge=True` (no silent scaffold completion).
- `AnalysisMetadata.result_origin` + product_flags enrichment / scaffold heuristic.
- Formal UI: 「重新分析 V2」confirm → new run id → hierarchical V2; old result preserved.

REAL PROVIDER CALLS: 0
