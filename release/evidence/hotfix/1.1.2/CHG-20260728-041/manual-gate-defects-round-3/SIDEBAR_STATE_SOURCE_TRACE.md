# SIDEBAR STATE SOURCE TRACE — Round 3

Sidebar / progress panel binds to `useCurrentPageAnalysisProgress` → `analysisRunId` from URL (`analysisRun=1`).

It does **not** take `journeyRun` from URL.

Elapsed time derives from AnalysisRun timestamps (`started_at` seeded at fixture creation), so a fresh Confirm+Start still shows ~1 hour if the parent analysis run was created with the fixture.

Journey 1/3 counts can mix:
- Analysis progress “scene analysis” framing
- Or journey run 2 `total_scene_count=3` after rematerialize

Unified selector must feed sidebar the same journey run id + started_at as the main pane.
