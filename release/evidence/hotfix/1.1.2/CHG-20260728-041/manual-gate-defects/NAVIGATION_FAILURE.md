# NAVIGATION_FAILURE

## Current URL
`/books/1?chapter=1&analysisRun=1&view=result&tab=reader-journey`

## Actual UI
`SceneBoundaryReviewPanel` title **调整场景边界**

## Mount points (pre-fix)
1. `BookRoutePage` auto `setReviewOpen(true)` when `sceneBoundaryReviewActive` — full-shell overlay `shell-boundary-review`
2. `BookRoutePage` journey tab also renders `SceneBoundaryReviewPanel` when `awaitingSceneBoundaryConfirmation`

## Primary CTA
`resolveChapterPrimaryAction` label **继续确认场景** → opens review overlay / journey tab, not a dedicated `view=scene-boundary-review` route.

## Defect
DEFECT-041-01: scene boundary editor incorrectly owned by reader-journey information architecture.
