# FINAL_REPORT — CHG-20260728-040

## STORYLENS 1.1.2 HOTFIX ISSUE 01 INVESTIGATION REPORT

CHANGE：  
CHG-20260728-040

ISSUE：  
INC-20260728-002

PUBLIC V1.1.1 BASE SHA：  
`38c85ab4eda0eaa03bd6a7bf8fda7d8deb11a5db`

PRIVATE V1.1.1 BASE SHA：  
`30d8dad8cd649e832999874f7bf16cc1661cf221`

PUBLIC HOTFIX INTEGRATION BRANCH：  
`hotfix/1.1.2`

PRIVATE HOTFIX INTEGRATION BRANCH：  
`hotfix/1.1.2`

PUBLIC ISSUE BRANCH：  
`fix/1.1.2-structured-output-truncation`

PRIVATE ISSUE BRANCH：  
`fix/1.1.2-structured-output-truncation`

PUBLIC ISSUE WORKTREE：  
`D:\Dstorylens-wt-hotfix-1.1.2-structured-output`

PRIVATE ISSUE WORKTREE：  
`D:\Dstorylens-private-engine-wt-hotfix-1.1.2-structured-output`

BASELINE UNIQUE：  
YES

V1.1.1 TAG MODIFIED：  
NO

V1.1.1 RELEASE MODIFIED：  
NO

INCIDENT SNAPSHOT：  
PASS

FORMAL DATABASE WRITES：  
0

REAL PROVIDER CALLS：  
0

FAILURE STAGE：  
`structured_output` (pipeline phase: `scene_boundary_adjudication`)

PROVIDER：  
`aliyun_qwen_plus`

MODEL：  
`qwen3.7-plus`

REQUEST MAX OUTPUT TOKENS：  
768

ACTUAL OUTPUT TOKENS：  
768

FINISH REASON：  
`length`

PARTIAL JSON RECEIVED：  
UNKNOWN (raw logging disabled; body not stored)

USAGE CAPTURED：  
YES (in `model_invocations`; UI detail shows “暂无用量明细”)

RESERVATION FINAL STATE：  
`released`

RETRY REUSES SAME PARAMETERS：  
YES (in-run truncation_retry keeps max_tokens=768)

ROOT CAUSE CATEGORY：  
A + H (+ contributing C); UI symptoms I/J

ROOT CAUSE CONFIDENCE：  
CONFIRMED

AFFECTED MODULES：  
`cloud_output_policy`, `structured_output`, `scene_pipeline` / `scene_boundary_adjudicator`, TasksPage usage/progress display

AFFECTED ANALYSIS TYPES：  
`scene_pipeline` assisted boundary adjudication (detection shares 768 ceiling); not native-overview 8192 path

REPRODUCIBLE WITH FIXTURE：  
NOT YET (plan written)

MINIMAL FIX RECOMMENDATION：  
Output-aware adjudication batching + modest adjudication output ceiling under user hard cap (4000) + truncation_retry must raise limit once; optional clearer UI usage/status copy. No DB migration.

DATABASE MIGRATION REQUIRED：  
NO

PUBLIC SOURCE MODIFIED：  
NO

PRIVATE SOURCE MODIFIED：  
NO

VERSION MODIFIED：  
NO

BUILD：  
NO

PUSH：  
NO

CHANGE STATUS：  
investigated

RELEASE POOL STATUS：  
pending

READY FOR IMPLEMENTATION PROMPT：  
YES

NEXT：  
CHG-20260728-040 IMPLEMENTATION — WAITING FOR REVIEW
