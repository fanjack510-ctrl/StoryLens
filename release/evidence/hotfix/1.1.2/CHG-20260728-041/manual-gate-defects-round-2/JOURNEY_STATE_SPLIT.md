# JOURNEY_STATE_SPLIT

## Split sources
1. AnalysisRun.effective_status / raw_output.chapter_pipeline = awaiting_scene_boundary_confirmation
2. SceneBoundariesOverview.awaiting_confirmation (always true if confirmed+model+no draft)
3. ReaderJourneyRun for analysis_run=1 (old fixture, result_status=superseded, scene_revision_id=1)
4. SceneBoundaryReviewPanel confirmed_readonly local state

## Loop
Confirm page → 「开始阅读旅程分析」 fakes journeyStarted → URL tab=reader-journey
→ BookRoutePage gate uses awaitingSceneBoundaryConfirmation=true → 「去确认场景」
→ view=scene-boundary-review → create draft → confirm → new revision #N → repeat

## Reader Journey GET
HTTP 500 — SceneReaderJourneyProfileItem validation on MG fixture payload (not product journey algorithm; fixture mismatch). New journey must be created instead of serializing broken old profiles.
