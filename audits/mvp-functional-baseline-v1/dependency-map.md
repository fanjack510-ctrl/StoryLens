# MVP Functional Baseline — Dependency Map

Generated: 2026-07-17 (Phase 1C-C.2.2-Baseline). Based on real imports/routes, not filenames alone.

## A. Book input chain

```
POST /api/v1/books/import
  → apps/api/app/api/v1/router.py::upload_book
  → book_service.import_book
       → extractors.extract_document
       → domain.ingestion.detect_chapters
       → Book / Chapter / Paragraph persistence (db/models.py)
GET /api/v1/books/{id}/chapters
GET /api/v1/chapters/{id}/paragraphs
  → desktop: LibraryPage → BookWorkspacePage (Structured text / StartAnalysisDialog)
```

**Stable IDs:** `Paragraph.id = B####-C####-P####`

## B. Scene analysis chain

```
POST /api/v1/chapters/{id}/analysis-runs
  → analysis.py::create_analysis_run
       → provider_eligibility + cloud_consent
       → budget_reservation.reserve_budget(STAGE_BOUNDARY) [cloud]
       → AnalysisRun row
       → background execute_scene_pipeline
            → structured_output.generate_validated (boundary v3.5)
            → boundary_detection_checkpoints
            → scene_boundary_adjudicator
            → boundary_review_service.create_review_session
            → status awaiting_boundary_review

POST /api/v1/boundary-reviews/{id}/confirm
  → confirm_review → BoundaryRevision + Scene rows
  → reserve_budget(STAGE_ANALYSIS) or boundary_confirmed_budget_blocked
  → analyze_confirmed_review
       → generate_validated(SceneAnalysisResult v3.1)
       → AnalysisArtifact(scene_analysis) + AnalysisEvidence
```

**Resume / recovery:**
- Detection: `continue-from-checkpoints` / `recover`
- Scene analysis: `resume-scene-analysis`, `replay-scene-analysis-offline`

## C. Reader Journey chain

```
POST /api/v1/analysis-runs/{run_id}/reader-journey
  → reader_journey.py
  → execute_reader_journey
       → reserve STAGE_READER_JOURNEY_SCENE
       → plan_scene_batches → generate_validated(SceneReaderJourneyBatchResult)
       → SceneReaderJourneyProfile + Artifact + Evidence
       → apply_deterministic_qin / enrich_hook_structure
       → reserve STAGE_READER_JOURNEY_CHAPTER
       → generate_validated(ChapterReaderJourneySynthesisResult)
       → ReaderJourneyPhase + ChapterReaderJourneySummary

POST .../semantic-recalibrate  (zero HTTP)
GET .../reader-journey → _serialize_result + build_reader_journey_visualization
       → reader_journey_visual_calibration (v1.1)
```

## D. Text ↔ journey mapping chain

```
Paragraph.id
  ⇄ Scene.start/end_paragraph_id
  ⇄ AnalysisEvidence.paragraph_id
  ⇄ JourneySceneNode.paragraph_range + evidence_paragraph_ids
  ⇄ ReaderJourneyPhase.start/end_scene_ordinal
  ⇄ Question Cluster / Hook / Payoff markers

Frontend:
  useJourneySelection (URL: tab, mode, scene, paragraph, metric, cluster)
  StructuredChapterTextPane (scroll spy + evidence flash)
  ReaderJourneyWorkspace (curve/phase/cluster selection)
  ReaderJourneySyncWorkspace (orchestration)
```

## E. Reliability chain

```
Preflight (zero HTTP)
  → CloudBudgetReservation + RequestGateDecision
  → ModelInvocation (per generate_validated)
  → Partial status (boundary_candidates_partial / scene_analysis_partial / scene_profiles_partial)
  → Failure fields on AnalysisRun / ReaderJourneyRun
  → Offline replay from parsed_response_json
  → Resume (same run, skip completed units)
  → Idempotency via client_request_id
```

## F. User viewing chain (current multi-page, not single-page)

```
/library → LibraryPage
/books/:bookId → BookWorkspacePage (+ BoundaryReviewPanel, StartAnalysisDialog)
/tasks → TasksPage (poll runs, recovery cards)
/analysis-runs/:runId/results → AnalysisResultsPage
  ├─ tabs: structure | evidence | history | overview | journey
  └─ when visualization present + tab=reader-journey
       → ReaderJourneySyncWorkspace (full-page swap)
```

**Not implemented:** Phase 1C-C.2.3 single-page Chapter Analysis Workspace.

## Key module → downstream table

| Module | Downstream |
|--------|------------|
| `book_service` | models Book/Chapter/Paragraph |
| `scene_pipeline` | structured_output, checkpoints, boundary_review_service |
| `boundary_review_service` | Scene, BoundaryRevision, scene analysis via structured_output |
| `structured_output` | ModelGateway, prompt_service, ModelInvocation |
| `reader_journey_pipeline` | validation, batch_planner, engagement, semantic calibrate helpers |
| `reader_journey_visualization` | visual_calibration, engagement formula, DB profiles/phases/summary |
| `AnalysisResultsPage` | analysisApi, SyncWorkspace / classic 3-pane |
| `ReaderJourneySyncWorkspace` | useJourneySelection, TextPane, JourneyWorkspace |

## Version pins (code vs golden sample)

| Item | Code default | JourneyRun #2 stored |
|------|--------------|----------------------|
| Scene prompt | v1.3 | v1.3 |
| Scene contract | 1.3 | 1.3 |
| Chapter prompt | v1.1 | **v1** |
| Chapter contract | 1.1 | **1.0** |
| Formula | 1.0 | 1.0 |
| Planner | 1.1 | 1.1 |
| Visualization | 1.1 | regenerated 1.1 offline |

Gap: JourneyRun #2 chapter synthesis versions lag code defaults; scene-side calibration to 1.3 is confirmed.
