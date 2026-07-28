"""Manual scene boundary review routes (CHG-041)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.v1.router import error
from app.db.models import BoundaryRevision, Chapter
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
    SceneBoundaryRevisionSummary,
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
)

router = APIRouter(prefix="/api/v1", tags=["scene-boundaries"])


def _scene_boundary_http_error(exc: SceneBoundaryError):
    status = 409 if exc.error_code == "SCENE_REVISION_CONCURRENT_MODIFICATION" else 422
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
    )


@router.put("/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}")
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
    return {
        "revision_id": draft.id,
        "revision_etag": draft.revision_etag,
        "boundary_hash": draft.boundary_hash,
    }


@router.post("/chapters/{chapter_id}/scene-boundaries/draft/{revision_id}/restore-ai")
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
    return {
        "revision_id": draft.id,
        "revision_etag": draft.revision_etag,
        "scenes": scenes,
    }


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
    try:
        if body.start_journey:
            revision, journey = await confirm_scene_revision_and_start_journey_v1(
                session,
                revision_id,
                expected_etag=body.expected_etag,
                start_journey=True,
                journey_options=body.journey_options,
                session_factory=session_factory,
                gateway=gateway,
            )
            if journey is not None:
                journey_run_id = journey.id
                journey_started = True
        else:
            revision = confirm_scene_revision_v1(
                session, revision_id, expected_etag=body.expected_etag
            )
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
            )
        raise _scene_boundary_http_error(exc) from exc
    return SceneBoundaryConfirmResponse(
        revision_id=revision.id,
        revision_etag=revision.revision_etag,
        boundary_hash=revision.boundary_hash,
        journey_run_id=journey_run_id,
        journey_started=journey_started,
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
