"""Manual scene boundary review routes (CHG-041)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.v1.router import error
from app.db.models import AnalysisRun, BoundaryRevision, Chapter
from app.db.session import get_db, get_session_factory
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.registry import get_model_gateway
from app.schemas.scene_boundaries import (
    SceneBoundariesOverviewResponse,
    SceneBoundaryConfirmRequest,
    SceneBoundaryConfirmResponse,
    SceneBoundaryDiffResponse,
    SceneBoundaryDraftCreateResponse,
    SceneBoundaryDraftSaveRequest,
    SceneBoundaryDraftSaveResponse,
    SceneBoundaryRevisionSummary,
    SceneBoundarySplitRequest,
    SceneBoundarySplitResponse,
    ScenePartitionItem,
)
from app.services.scene_boundary_manual_review import (
    SceneBoundaryError,
    compute_diff_summary_v1,
    confirm_scene_revision_and_start_journey_v1,
    confirm_scene_revision_v1,
    create_or_get_scene_boundary_draft_v1,
    discard_scene_boundary_draft_v1,
    get_scene_boundaries_overview_v1,
    parse_partition_json,
    restore_ai_partition_into_draft_v1,
    save_scene_boundary_draft_v1,
    split_scene_at_paragraph_v1,
)

router = APIRouter(prefix="/api/v1", tags=["scene-boundaries"])


def _scene_boundary_http_error(exc: SceneBoundaryError):
    if exc.error_code == "SCENE_REVISION_CONCURRENT_MODIFICATION":
        status = 409
    elif exc.error_code == "SCENE_REVISION_NOT_FOUND":
        status = 404
    else:
        status = 422
    return error(status, exc.error_code, str(exc))


def _chapter_or_404(session: Session, chapter_id: int) -> Chapter:
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise error(404, "CHAPTER_NOT_FOUND", "章节不存在")
    return chapter


def _revision_or_404(session: Session, revision_id: int, chapter_id: int) -> BoundaryRevision:
    revision = session.get(BoundaryRevision, revision_id)
    if revision is None or revision.chapter_id != chapter_id:
        raise error(404, "SCENE_REVISION_NOT_FOUND", "场景边界修订不存在")
    return revision


def _pack_overview(raw: dict) -> SceneBoundariesOverviewResponse:
    def pack(item: dict | None) -> SceneBoundaryRevisionSummary | None:
        if item is None:
            return None
        return SceneBoundaryRevisionSummary(
            revision_id=item["revision_id"],
            revision_number=item["revision_number"],
            status=item["status"],
            source=item["source"],
            revision_etag=item["revision_etag"],
            boundary_hash=item["boundary_hash"],
            chapter_text_hash=item["chapter_text_hash"],
            scenes=[ScenePartitionItem(**scene) for scene in item["scenes"]],
            confirmed_at=item.get("confirmed_at"),
        )

    return SceneBoundariesOverviewResponse(
        chapter_id=raw["chapter_id"],
        chapter_text_hash=raw["chapter_text_hash"],
        confirmed_revision=pack(raw.get("confirmed_revision")),
        draft_revision=pack(raw.get("draft_revision")),
        model_revision=pack(raw.get("model_revision")),
        awaiting_confirmation=bool(raw.get("awaiting_confirmation")),
    )


@router.get(
    "/chapters/{chapter_id}/scene-boundaries",
    response_model=SceneBoundariesOverviewResponse,
)
def get_scene_boundaries(chapter_id: int, session: Session = Depends(get_db)):
    _chapter_or_404(session, chapter_id)
    return _pack_overview(get_scene_boundaries_overview_v1(session, chapter_id))


@router.post(
    "/chapters/{chapter_id}/scene-boundaries/draft",
    response_model=SceneBoundaryDraftCreateResponse,
    status_code=201,
)
def create_scene_boundary_draft(chapter_id: int, session: Session = Depends(get_db)):
    _chapter_or_404(session, chapter_id)
    try:
        draft = create_or_get_scene_boundary_draft_v1(session, chapter_id)
        session.commit()
    except SceneBoundaryError as exc:
        raise _scene_boundary_http_error(exc) from exc
    scenes = parse_partition_json(draft.final_boundaries_json)
    return SceneBoundaryDraftCreateResponse(
        revision_id=draft.id,
        revision_etag=draft.revision_etag,
        scenes=[ScenePartitionItem(**item) for item in scenes],
        boundary_hash=draft.boundary_hash,
        status=draft.status,
        updated_at=str(draft.updated_at) if draft.updated_at else None,
    )


@router.put(
    "/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}",
    response_model=SceneBoundaryDraftSaveResponse,
)
def save_scene_boundary_draft(
    chapter_id: int,
    revision_id: int,
    body: SceneBoundaryDraftSaveRequest,
    session: Session = Depends(get_db),
):
    _revision_or_404(session, revision_id, chapter_id)
    try:
        draft = save_scene_boundary_draft_v1(
            session,
            revision_id,
            [item.model_dump() for item in body.scenes],
            expected_etag=body.expected_etag,
        )
        session.commit()
    except SceneBoundaryError as exc:
        raise _scene_boundary_http_error(exc) from exc
    scenes = parse_partition_json(draft.final_boundaries_json)
    return SceneBoundaryDraftSaveResponse(
        revision_id=draft.id,
        revision_etag=draft.revision_etag,
        boundary_hash=draft.boundary_hash or "",
        scenes=[ScenePartitionItem(**item) for item in scenes],
        status=draft.status,
        updated_at=str(draft.updated_at) if draft.updated_at else None,
    )


@router.post(
    "/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}/split",
    response_model=SceneBoundarySplitResponse,
)
def split_scene_boundary_draft(
    chapter_id: int,
    revision_id: int,
    body: SceneBoundarySplitRequest,
    session: Session = Depends(get_db),
):
    _revision_or_404(session, revision_id, chapter_id)
    try:
        result = split_scene_at_paragraph_v1(
            session,
            chapter_id,
            revision_id,
            boundary_after_paragraph_id=body.boundary_after_paragraph_id,
            expected_etag=body.expected_etag,
            client_request_id=body.client_request_id,
            scene_order=body.scene_order,
        )
        session.commit()
    except SceneBoundaryError as exc:
        raise _scene_boundary_http_error(exc) from exc
    return SceneBoundarySplitResponse(
        revision_id=result["revision_id"],
        revision_etag=result["revision_etag"],
        boundary_hash=result["boundary_hash"],
        scenes=[ScenePartitionItem(**item) for item in result["scenes"]],
        diff_summary=result.get("diff_summary") or {},
        updated_at=result.get("updated_at"),
        already_split=bool(result.get("already_split")),
        status=str(result.get("status") or "draft"),
    )


@router.post(
    "/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}/restore-ai",
    response_model=SceneBoundaryDraftCreateResponse,
)
def restore_ai_partition(
    chapter_id: int,
    revision_id: int,
    session: Session = Depends(get_db),
):
    _revision_or_404(session, revision_id, chapter_id)
    try:
        draft = restore_ai_partition_into_draft_v1(session, revision_id)
        session.commit()
    except SceneBoundaryError as exc:
        raise _scene_boundary_http_error(exc) from exc
    scenes = parse_partition_json(draft.final_boundaries_json)
    return SceneBoundaryDraftCreateResponse(
        revision_id=draft.id,
        revision_etag=draft.revision_etag,
        scenes=[ScenePartitionItem(**item) for item in scenes],
        boundary_hash=draft.boundary_hash,
        status=draft.status,
        updated_at=str(draft.updated_at) if draft.updated_at else None,
    )


@router.post(
    "/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}/confirm",
    response_model=SceneBoundaryConfirmResponse,
)
async def confirm_scene_boundary(
    chapter_id: int,
    revision_id: int,
    body: SceneBoundaryConfirmRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_db),
    session_factory=Depends(get_session_factory),
    gateway: ModelGateway = Depends(get_model_gateway),
):
    _revision_or_404(session, revision_id, chapter_id)
    journey_run_id: int | None = None
    journey_started = False
    journey_status: str | None = None
    already_confirmed = False
    journey_error_code: str | None = None
    journey_error_message: str | None = None
    try:
        if body.start_journey:
            from app.services.reader_journey_pipeline import execute_reader_journey

            # Queue only in-request; execute asynchronously so Confirm+Start can
            # return a routable journey_run_id immediately (same pattern as create).
            revision, journey, already_confirmed, journey_error_code = (
                await confirm_scene_revision_and_start_journey_v1(
                    session,
                    revision_id,
                    expected_etag=body.expected_etag,
                    start_journey=True,
                    journey_options=body.journey_options,
                    session_factory=None,
                    gateway=None,
                )
            )
            if journey is not None:
                journey_run_id = journey.id
                journey_status = journey.status
                if journey.status in {
                    "queued",
                    "running",
                    "scene_profiles_running",
                    "chapter_synthesis_running",
                }:
                    background.add_task(
                        execute_reader_journey, session_factory, gateway, journey.id
                    )
                    journey_started = True
                elif journey.status == "succeeded" and journey_error_code is None:
                    journey_started = True
            if journey_error_code:
                journey_error_message = {
                    "SCENE_CONFIRMED_JOURNEY_NOT_STARTED": "阅读旅程任务未能启动。",
                    "JOURNEY_START_FAILED": "阅读旅程任务启动失败。",
                    "JOURNEY_TASK_ALREADY_ACTIVE": "阅读旅程任务已在进行中。",
                }.get(journey_error_code, "阅读旅程任务未能启动。")
        else:
            from app.services.chapter_analysis_completion import (
                mark_scenes_complete_awaiting_journey,
            )

            revision, already_confirmed = confirm_scene_revision_v1(
                session, revision_id, expected_etag=body.expected_etag
            )
            run = session.get(AnalysisRun, revision.analysis_run_id)
            if run is not None:
                mark_scenes_complete_awaiting_journey(session, run)
            session.commit()
    except SceneBoundaryError as exc:
        if exc.error_code == "SCENE_CONFIRMED_JOURNEY_NOT_STARTED":
            session.commit()
            revision = session.get(BoundaryRevision, revision_id)
            return SceneBoundaryConfirmResponse(
                revision_id=revision.id if revision else revision_id,
                revision_etag=revision.revision_etag if revision else "",
                boundary_hash=revision.boundary_hash if revision else "",
                journey_run_id=None,
                journey_started=False,
                already_confirmed=False,
                journey_error_code=exc.error_code,
                journey_error_message="阅读旅程任务未能启动。",
            )
        raise _scene_boundary_http_error(exc) from exc
    return SceneBoundaryConfirmResponse(
        revision_id=revision.id,
        revision_etag=revision.revision_etag,
        boundary_hash=revision.boundary_hash or "",
        journey_run_id=journey_run_id,
        journey_started=journey_started,
        journey_status=journey_status,
        already_confirmed=already_confirmed,
        journey_error_code=journey_error_code,
        journey_error_message=journey_error_message,
    )


@router.post("/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}/discard", status_code=204)
def discard_scene_boundary_draft(
    chapter_id: int,
    revision_id: int,
    session: Session = Depends(get_db),
):
    _revision_or_404(session, revision_id, chapter_id)
    try:
        discard_scene_boundary_draft_v1(session, revision_id)
        session.commit()
    except SceneBoundaryError as exc:
        raise _scene_boundary_http_error(exc) from exc
    return None


@router.get(
    "/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}/diff",
    response_model=SceneBoundaryDiffResponse,
)
def get_scene_boundary_diff(
    chapter_id: int,
    revision_id: int,
    session: Session = Depends(get_db),
):
    _revision_or_404(session, revision_id, chapter_id)
    try:
        diff = compute_diff_summary_v1(session, revision_id)
    except SceneBoundaryError as exc:
        raise _scene_boundary_http_error(exc) from exc
    return SceneBoundaryDiffResponse(**diff)
