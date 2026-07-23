# Phase 2A Frontend Mock Run Lab

## Surface

Isolated `WholeBookMockRunLab` using existing Preflight, Mode/Module selectors, Stage Plan, Run Progress, Result Projection, Evidence Drawer, Structure Map.

## Flow

Load Preflight → show production start still disabled → if dev+Lab show separate “启动 Mock 验证运行” → create Mock Run → Progress → poll → partial results → pause/resume/retry/cancel → Evidence → Structure Map.

## Rules

Mock vs production buttons strictly separate; banner “开发验证，不是真实分析”; production build hidden; not in formal nav; no formal Pro copy; mock results not described as real; every page shows mock/non-production; network fail-closed; never invent allowed_actions or derive Run status.
