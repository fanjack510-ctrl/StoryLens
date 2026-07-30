# CHG-20260730-015 RC4 FAILURE CONSISTENCY REPORT

```text
CHG-20260730-015 RC4 FAILURE CONSISTENCY REPORT

CHANGE：
CHG-20260730-015

INCIDENT：
INC-20260730-007

PUBLIC BASE HEAD：
678e0b1aff1ca827a48520474d2f8a3fc660dacc

PUBLIC FINAL HEAD：
07b4045e42c027cf2147f972c8ab6b51abe21ee4

ROOT CAUSE：
H + M(JOURNEY_START_BEFORE_REMATERIALIZED_SCENE_ARTIFACTS) + I + K

FAILED TASK ID：
analysis_run=7 / journey_run=5 / chapter=1304

ANALYSIS RUN ID：
7

JOURNEY RUN ID：
5

CONFIRMED REVISION ID：
13

CONFIRMED SCENE COUNT：
3

ACTUAL PROVIDER CALL COUNT：
8 (boundary+scene_analysis; journey profiles=0)

COMPLETED SCENE RESULTS：
0 at failure time; 3 after 04:53:23 UTC (too late)

FAILURE STAGE：
scene_analysis (require artifacts before journey profiles)

FAILURE CODE：
PIPELINE_UNEXPECTED_ERROR / SCENE_ANALYSIS_INCOMPLETE

FAILURE REQUEST ID：
n/a (no journey provider call)

FINISH REASON：
n/a

SCENE ANALYSIS ACTUALLY COMPLETED：
NO (at fail); YES later for 68/69/70

JOURNEY SYNTHESIS ACTUALLY STARTED：
NO

SINGLE CURRENT RUN SOURCE：
PASS (FE composite/progress aligned; failed≠interrupted)

STAGE COMPLETION AFTER COMMIT：
PASS (confirm no longer marks succeeded before artifacts)

ZERO OF THREE SHOWN AS COMPLETE：
NO (guarded)

FAILED SHOWN AS INTERRUPTED：
NO (guarded)

FAILED SHOWN AS PAUSED：
NO

FAILURE STAGE DISPLAY：
PASS (WAITING_SCENE_ANALYSIS / scene_analysis)

CONTINUE ONLY WHEN RECOVERABLE：
PASS (JOURNEY_INTERRUPTED only)

OLD RUN CONTAMINATION：
ABSENT

ACCIDENT DATABASE REPLAY：
PASS (read-only forensic; wait-gate unit)

PYTEST：
test_rc4_post_confirm_scene_analysis_chg015 + CHG-013 11 passed

VITEST：
compositeRunLifecycle 8 passed

TYPECHECK：
not re-baselined this round

HTTP E2E：
PASS (confirm wait-gate); live MG fixture URLs pending seed

REFRESH RESULT：
PASS (status derived)

API RESTART RESULT：
PASS (WAITING persists starting)

REAL PROVIDER CALLS THIS ROUND：
0

FORMAL DATABASE WRITES：
0

VERSION MODIFIED：
NO

BUILD：
NO

INSTALLER：
NO

PUSH：
NO

TAG：
NO

RELEASE：
NO

PUBLIC CLEAN：
YES

CHANGE STATUS：
tested

RC.4 INSTALLED ACCEPTANCE：
FAILED

RELEASE TRAIN STATUS：
blocked-awaiting-rc4-failure-consistency-retest

MANUAL UI READY：
YES

DATABASE：
%TEMP%\storylens-mg-chg015-rc4-failure\database\storylens-mg-chg015.db

API URL：
http://127.0.0.1:18049

FRONTEND URL：
http://127.0.0.1:1428

SCENE FAILURE URL：
(seed during MG)

SYNTHESIS FAILURE URL：
(seed during MG)

RECOVERABLE INTERRUPTED URL：
(seed during MG)

SUCCESS URL：
(seed during MG)

NEXT：
MG-CHG-20260730-015 MANUAL UI ACCEPTANCE
```
