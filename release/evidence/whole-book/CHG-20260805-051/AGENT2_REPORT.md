# V1.2.0 RELEASE DEBT AGENT 2 REPORT

CHANGE：
CHG-20260805-051

PUBLIC BASE HEAD：
d5cb364667a298538cc545f742197a17056a90ce

PUBLIC PRODUCT HEAD：
d5cb364667a298538cc545f742197a17056a90ce

PUBLIC FINAL HEAD：
d5cb364667a298538cc545f742197a17056a90ce (uncommitted working tree on `feature/v120-release-debt-desktop`)

BRANCH：
feature/v120-release-debt-desktop

WORKTREE：
D:\Dstorylens-wt-v120-debt-agent2

---

## SCENE BOUNDARY NAVIGATION：
PASS

SCENE REVIEW TARGET：
scene

JOURNEY CTA REGRESSION：
PASS

Root cause: `mapUrlToActiveTab` prioritized `tab=reader-journey` over `view=scene-boundary-review`.
Product fix: `resolveWorkspaceLayout.ts` — scene-boundary-review wins before journey deep-link.
`openSceneBoundaryReview` already clears `tab` and preserves book/chapter/analysisRun/journeyRun identity.

---

## READER JOURNEY VERIFIED CONTRACT：
PRESERVED

READER JOURNEY FAILED TEST FILES BEFORE：
17

READER JOURNEY FAILED TEST FILES AFTER：
0

OBSOLETE VITEST UPDATED：
- Scene Inspector tab IA → `scene-detail-insight-panel` / `scene-dimension-insight-text`
- Phase score label `阅读动力` → `综合阅读`
- Phase card CSS `min-height` 96px → 112px
- awaiting journey → `chapter-analysis-journey-pending` (not unified-recovery-card)
- composite lens one_line_summary copy lock
- runtime_capabilities `apiClient` mock via `importOriginal`
- autoDiscover: reset `readerJourney` mock between cases (test isolation)

REAL PRODUCT REGRESSIONS FIXED：
- P2 scene-boundary-review → scene tab mapping (`resolveWorkspaceLayout.ts`)

---

## READER OFFSET HIGHLIGHT：
DEFERRED

DEV DIAGNOSTICS FUZZY：
DEFERRED

DEFERRED ITEMS AFFECT PRODUCTION：
NO

Evidence: `wholeBookFreeEvidence.wb221` + `wholeBookFreeProduct` PASS; production dist has INDEX_NO_DEV=True, JS_DEV_ROUTE_HITS=0.

---

## TYPECHECK：
PASS

DESKTOP PRODUCTION BUILD：
PASS

TARGETED VITEST：
- SceneBoundaryNavigation + journeyNav + 17 former fail files: 19 files / 137 tests PASS
- readerJourney directed suite (+ resume/journeyNav): 62 files / 502 tests PASS
- Whole-Book Evidence / restore / Free product: 3 files / 44 tests PASS

PRODUCT CODE MODIFIED：
YES

TEST CODE MODIFIED：
YES

REAL PROVIDER CALLS：
0

FORMAL DATABASE WRITES：
0

PROTECTED WIP MODIFIED：
NO

PUBLIC CLEAN：
NO

CHANGE STATUS：
tested

READY FOR INTEGRATION：
YES
