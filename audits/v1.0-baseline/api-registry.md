# V1.0 Baseline — API Registry (summary)

**Base:** `http://127.0.0.1:8000`  
**Prefix:** `/api/v1`  
**Entry:** `apps/api/app/main.py`

Full parameter/response documentation: `docs/architecture/07-api-reference.md`.

## Health & system

| Method | Path |
|--------|------|
| GET | `/health` |
| GET | `/api/v1/system/capabilities` |
| GET | `/api/v1/system/diagnostics` |
| GET | `/api/v1/dashboard/summary` |

## Books / chapters / paragraphs

| Method | Path |
|--------|------|
| POST | `/api/v1/books/import` |
| POST | `/api/v1/books/chapter-detection/preview` |
| GET | `/api/v1/books` |
| GET | `/api/v1/books/{book_id}` |
| GET | `/api/v1/books/{book_id}/import-diagnostics` |
| POST | `/api/v1/books/{book_id}/reparse-preview` |
| POST | `/api/v1/books/{book_id}/reparse` |
| POST | `/api/v1/books/{book_id}/reparse-with-file-preview` |
| POST | `/api/v1/books/{book_id}/reparse-with-file` |
| GET | `/api/v1/books/{book_id}/chapters` |
| GET | `/api/v1/chapters/{chapter_id}/paragraphs` |

## Analysis runs / scenes

| Method | Path |
|--------|------|
| GET | `/api/v1/analysis-runs` |
| POST | `/api/v1/analysis-runs/preflight` |
| POST | `/api/v1/analysis-runs/full-pipeline-preflight` |
| POST | `/api/v1/chapters/{chapter_id}/analysis-runs` |
| GET | `/api/v1/analysis-runs/{run_id}` |
| POST | `/api/v1/analysis-runs/{run_id}/retry` |
| GET/POST | `/api/v1/analysis-runs/{run_id}/recovery-preflight` / `recover/preflight` |
| POST | `/api/v1/analysis-runs/{run_id}/continue-from-checkpoints` |
| GET | `/api/v1/analysis-runs/{run_id}/recovery-plan` |
| POST | `/api/v1/analysis-runs/{run_id}/recover` |
| GET/POST | `/api/v1/analysis-runs/{run_id}/resume-scene-analysis/preflight` |
| POST | `/api/v1/analysis-runs/{run_id}/resume-scene-analysis` |
| POST | `/api/v1/analysis-runs/{run_id}/replay-scene-analysis-offline` |
| POST | `/api/v1/analysis-runs/{run_id}/scene-analysis/offline-replay` |
| GET | `/api/v1/chapters/{chapter_id}/scenes` |
| GET | `/api/v1/analysis-runs/{run_id}/scenes` |
| GET | `/api/v1/analysis-runs/{run_id}/model-invocations` |
| GET | `/api/v1/analysis-runs/{run_id}/results` |
| GET | `/api/v1/analysis-runs/{run_id}/results/export` |
| GET | `/api/v1/scenes/{scene_id}` |
| GET | `/api/v1/scenes/{scene_id}/analysis` |
| GET | `/api/v1/scenes/{scene_id}/analysis-artifacts` |
| GET | `/api/v1/scenes/{scene_id}/paragraphs` |
| GET | `/api/v1/artifacts/{artifact_id}/evidence` |

## Boundary review

| Method | Path |
|--------|------|
| GET | `/api/v1/books/{book_id}/chapters/{chapter_id}/boundary-review` |
| POST | `/api/v1/analysis-runs/{run_id}/boundary-review/start` |
| PUT | `/api/v1/boundary-reviews/{review_id}/decisions/{transition_id}` |
| POST | `/api/v1/boundary-reviews/{review_id}/manual-boundaries` |
| DELETE | `/api/v1/boundary-reviews/{review_id}/manual-boundaries/{transition_id}` |
| GET | `/api/v1/boundary-reviews/{review_id}/scene-preview` |
| GET | `/api/v1/boundary-reviews/{review_id}/scene-analysis-preflight` |
| POST | `/api/v1/boundary-reviews/{review_id}/confirm` |
| POST | `/api/v1/boundary-reviews/{review_id}/cancel` |

## Reader Journey

| Method | Path |
|--------|------|
| POST | `/api/v1/analysis-runs/{run_id}/reader-journey/preflight` |
| POST | `/api/v1/analysis-runs/{run_id}/reader-journey` |
| GET | `/api/v1/analysis-runs/{run_id}/reader-journey` |
| GET | `/api/v1/reader-journey-runs/{journey_run_id}/progress` |
| POST | `/api/v1/reader-journey-runs/{journey_run_id}/resume` |
| POST | `/api/v1/reader-journey-runs/{journey_run_id}/scene-profiles/offline-replay` |
| POST | `/api/v1/reader-journey-runs/{journey_run_id}/semantic-recalibrate` |
| POST | `/api/v1/reader-journey-runs/{journey_run_id}/cancel` |
| GET | `/api/v1/reader-journey-runs/{journey_run_id}/export` |

## Desktop / providers / budget

| Method | Path |
|--------|------|
| GET/PUT | `/api/v1/settings/cloud` |
| GET/PUT | `/api/v1/settings/cloud-budget` |
| GET/PUT | `/api/v1/settings/desktop` |
| GET | `/api/v1/cloud-pricing/status` |
| GET | `/api/v1/cloud-usage/summary` |
| GET | `/api/v1/model-providers` |
| GET | `/api/v1/model-providers/{name}/health` |
| GET/PUT | `/api/v1/model-providers/{name}/configuration` |
| POST | `/api/v1/model-providers/{name}/connect\|disconnect\|enable\|disable` |
| POST | `/api/v1/model-providers/{name}/validate-configuration` |
| POST | `/api/v1/model-providers/{name}/transport-diagnostic` |
| POST | `/api/v1/model-providers/{name}/test` |
| POST | `/api/v1/model-providers/{name}/test/preflight` |
| DELETE | `/api/v1/model-providers/{name}/credentials` |
| GET | `/api/v1/model-routing/preview` |
| POST | `/api/v1/local-model/start\|stop` |
| GET | `/api/v1/local-model/status` |
| GET | `/api/v1/local-model/log-directory` |

## Notes

- Async work uses FastAPI `BackgroundTasks` only (no Celery/Redis).
- `POST .../recover` is owned by the unified recovery router (`analysis_recovery.py`).
