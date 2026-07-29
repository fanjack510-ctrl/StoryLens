# EXPLICIT_RUN_QUERY_TRACE — CHG-041 Round 6

## Frozen rule

If URL has `journeyRun=N`, page must prefer that run.

## Pre-fix gaps

1. Visualization rebuild ignored journey-bound included scenes filter → succeeded run looked “not generated”.
2. Selector previously dropped explicit URL hits when `scene_revision_id !== confirmed` (partially fixed in working tree).
3. Gate `confirmed_no_journey` could appear when candidates omitted the explicit id while GET still loading / viz null.
4. V2 finalize mixed prior analysis-run artifacts into the new journey.

## Allowed outcomes (target)

| State | UI |
|-------|----|
| succeeded | Show journey result |
| superseded | Show historical result + old-revision banner |
| failed | Show failure |
| running | Show progress |
| missing | 指定的阅读旅程不存在或已被删除 |

Must **not** map existing historical/polluted-but-succeeded runs to “尚未生成”.
