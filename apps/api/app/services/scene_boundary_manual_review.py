"""Manual scene boundary review lifecycle (CHG-041)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    BoundaryReviewSession,
    BoundaryRevision,
    Chapter,
    Paragraph,
    ReaderJourneyRun,
    Scene,
    SceneReaderJourneyProfile,
)
from app.services.scene_boundary_partition_ops import (
    add_boundary,
    delete_boundary,
    delete_scene_merge,
    move_boundary,
    set_included,
)

PARTITION_VERSION = 1


class SceneBoundaryError(Exception):
    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_chapter_text_hash_v1(session: Session, chapter_id: int) -> str:
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    joined = "\n".join(item.normalized_text or item.raw_text for item in paragraphs)
    return hashlib.sha256(joined.encode()).hexdigest()


def compute_scene_boundary_hash_v1(
    chapter_id: int,
    chapter_text_hash: str,
    scenes: list[dict],
) -> str:
    ordered = sorted(scenes, key=lambda item: int(item["scene_order"]))
    payload = {
        "chapter_id": chapter_id,
        "chapter_text_hash": chapter_text_hash,
        "partition_version": PARTITION_VERSION,
        "scenes": [
            {
                "scene_order": int(item["scene_order"]),
                "start_paragraph_id": item["start_paragraph_id"],
                "end_paragraph_id": item["end_paragraph_id"],
                "included_in_journey": bool(item.get("included_in_journey", True)),
            }
            for item in ordered
        ],
    }
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def compute_scene_journey_input_hash_v1(
    *,
    chapter_text_hash: str,
    scene_text_hash: str,
    included_in_journey: bool,
    journey_prompt_version: str,
    journey_contract_version: str,
    provider_id: str,
    model_id: str,
    # Backward-compatible optional identity fields (not used alone for reuse).
    chapter_id: int | None = None,
    scene_order: int | None = None,
    start_paragraph_id: str | None = None,
    end_paragraph_id: str | None = None,
    content_hash: str | None = None,
) -> str:
    del chapter_id, scene_order, start_paragraph_id, end_paragraph_id
    payload = {
        "chapter_text_hash": chapter_text_hash,
        "scene_text_hash": scene_text_hash or content_hash or "",
        "included_in_journey": included_in_journey,
        "journey_prompt_version": journey_prompt_version,
        "journey_contract_version": journey_contract_version,
        "provider_id": provider_id,
        "model_id": model_id,
        "version": 1,
    }
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _paragraph_ids(session: Session, chapter_id: int) -> list[str]:
    return list(
        session.scalars(
            select(Paragraph.id)
            .where(Paragraph.chapter_id == chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )


def _scene_content_hash(session: Session, start_id: str, end_id: str) -> str:
    start = session.get(Paragraph, start_id)
    end = session.get(Paragraph, end_id)
    if start is None or end is None:
        return ""
    chapter_id = start.chapter_id
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(
                Paragraph.chapter_id == chapter_id,
                Paragraph.paragraph_index >= start.paragraph_index,
                Paragraph.paragraph_index <= end.paragraph_index,
            )
            .order_by(Paragraph.paragraph_index)
        )
    )
    joined = "\n".join(item.normalized_text or item.raw_text for item in paragraphs)
    return hashlib.sha256(joined.encode()).hexdigest()


def scenes_from_scene_rows(scenes: list[Scene]) -> list[dict]:
    return [
        {
            "scene_order": scene.ordinal,
            "start_paragraph_id": scene.start_paragraph_id,
            "end_paragraph_id": scene.end_paragraph_id,
            "included_in_journey": bool(getattr(scene, "included_in_journey", True)),
        }
        for scene in sorted(scenes, key=lambda item: item.ordinal)
    ]


def parse_partition_json(raw: str) -> list[dict]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        payload = raw
    if isinstance(payload, dict) and "scenes" in payload:
        return list(payload["scenes"])
    if isinstance(payload, list):
        return []
    return []


def dump_partition_json(scenes: list[dict], *, boundaries: list[dict] | None = None) -> str:
    ordered = sorted(scenes, key=lambda item: int(item["scene_order"]))
    payload: dict[str, Any] = {
        "partition_version": PARTITION_VERSION,
        "scenes": ordered,
    }
    if boundaries is not None:
        payload["boundaries"] = boundaries
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _new_etag() -> str:
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()


def validate_scene_partition_v1(
    session: Session,
    chapter_id: int,
    scenes: list[dict],
    *,
    expected_chapter_text_hash: str | None = None,
) -> None:
    if not scenes:
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY")
    paragraph_ids = _paragraph_ids(session, chapter_id)
    if not paragraph_ids:
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY")
    if expected_chapter_text_hash is not None:
        current = compute_chapter_text_hash_v1(session, chapter_id)
        if current != expected_chapter_text_hash:
            raise SceneBoundaryError("SCENE_PARTITION_CHAPTER_CHANGED")
    pos = {pid: index for index, pid in enumerate(paragraph_ids)}
    ordered = sorted(scenes, key=lambda item: int(item["scene_order"]))
    if [int(item["scene_order"]) for item in ordered] != list(range(1, len(ordered) + 1)):
        raise SceneBoundaryError("SCENE_PARTITION_ORDER_INVALID")
    if not any(bool(item.get("included_in_journey", True)) for item in ordered):
        raise SceneBoundaryError("SCENE_PARTITION_NO_JOURNEY_SCENE")
    prev_end: int | None = None
    for item in ordered:
        start_id = item["start_paragraph_id"]
        end_id = item["end_paragraph_id"]
        if start_id not in pos or end_id not in pos:
            raise SceneBoundaryError("SCENE_PARTITION_PARAGRAPH_MISSING")
        start_i = pos[start_id]
        end_i = pos[end_id]
        if start_i > end_i:
            raise SceneBoundaryError("SCENE_PARTITION_ORDER_INVALID")
        if end_i - start_i < 0:
            raise SceneBoundaryError("SCENE_PARTITION_EMPTY_SCENE")
        if prev_end is not None:
            if start_i != prev_end + 1:
                if start_i <= prev_end:
                    raise SceneBoundaryError("SCENE_PARTITION_OVERLAP")
                raise SceneBoundaryError("SCENE_PARTITION_GAP")
        prev_end = end_i
    if prev_end != len(paragraph_ids) - 1:
        raise SceneBoundaryError("SCENE_PARTITION_GAP")


def get_confirmed_revision(session: Session, chapter_id: int) -> BoundaryRevision | None:
    return _confirmed_revision(session, chapter_id)


def _confirmed_revision(session: Session, chapter_id: int) -> BoundaryRevision | None:
    return session.scalar(
        select(BoundaryRevision)
        .where(
            BoundaryRevision.chapter_id == chapter_id,
            BoundaryRevision.status == "confirmed",
        )
        .order_by(BoundaryRevision.id.desc())
    )


def _draft_revision(session: Session, chapter_id: int) -> BoundaryRevision | None:
    return session.scalar(
        select(BoundaryRevision)
        .where(
            BoundaryRevision.chapter_id == chapter_id,
            BoundaryRevision.status == "draft",
        )
        .order_by(BoundaryRevision.id.desc())
    )


def _model_revision(session: Session, chapter_id: int) -> BoundaryRevision | None:
    return session.scalar(
        select(BoundaryRevision)
        .where(
            BoundaryRevision.chapter_id == chapter_id,
            BoundaryRevision.source == "model",
            BoundaryRevision.status.in_(["confirmed", "superseded"]),
        )
        .order_by(BoundaryRevision.id.desc())
    )


def _next_revision_number(session: Session, chapter_id: int, review_session_id: int | None) -> int:
    if review_session_id is not None:
        current = session.scalar(
            select(func.max(BoundaryRevision.revision_number)).where(
                BoundaryRevision.review_session_id == review_session_id
            )
        )
        return int(current or 0) + 1
    current = session.scalar(
        select(func.max(BoundaryRevision.revision_number)).where(
            BoundaryRevision.chapter_id == chapter_id,
            BoundaryRevision.review_session_id.is_(None),
        )
    )
    return int(current or 0) + 1


def _get_or_create_partition_session(
    session: Session, run: AnalysisRun, chapter: Chapter
) -> BoundaryReviewSession:
    existing = session.scalar(
        select(BoundaryReviewSession)
        .where(BoundaryReviewSession.analysis_run_id == run.id)
        .order_by(BoundaryReviewSession.id.desc())
    )
    if existing is not None:
        if existing.status not in {"partition_ready", "confirmed"}:
            existing.status = "partition_ready"
        return existing
    review = BoundaryReviewSession(
        book_id=chapter.book_id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        prompt_version=run.prompt_version,
        provider=run.provider,
        model=run.model,
        status="partition_ready",
    )
    session.add(review)
    session.flush()
    return review


def revision_scenes(session: Session, revision_id: int) -> list[Scene]:
    return list(
        session.scalars(
            select(Scene)
            .where(Scene.boundary_revision_id == revision_id)
            .order_by(Scene.ordinal)
        )
    )


def run_scenes(session: Session, run_id: int) -> list[Scene]:
    return list(
        session.scalars(
            select(Scene).where(Scene.created_by_run_id == run_id).order_by(Scene.ordinal)
        )
    )


def ensure_legacy_confirmed_revision_v1(session: Session, chapter_id: int) -> BoundaryRevision | None:
    existing = _confirmed_revision(session, chapter_id)
    if existing is not None:
        return existing
    scenes = list(
        session.scalars(
            select(Scene).where(Scene.chapter_id == chapter_id).order_by(Scene.ordinal)
        )
    )
    if not scenes:
        return None
    run_id = scenes[0].created_by_run_id
    run = session.get(AnalysisRun, run_id)
    if run is None:
        return None
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        return None
    review = _get_or_create_partition_session(session, run, chapter)
    chapter_hash = compute_chapter_text_hash_v1(session, chapter_id)
    partition = scenes_from_scene_rows(scenes)
    boundary_hash = compute_scene_boundary_hash_v1(chapter_id, chapter_hash, partition)
    revision = BoundaryRevision(
        review_session_id=review.id,
        chapter_id=chapter_id,
        analysis_run_id=run_id,
        revision_number=_next_revision_number(session, chapter_id, review.id),
        final_boundaries_json=dump_partition_json(partition),
        confirmed_by="legacy-migration",
        status="confirmed",
        source="legacy",
        chapter_text_hash=chapter_hash,
        boundary_hash=boundary_hash,
        revision_etag=_new_etag(),
    )
    session.add(revision)
    session.flush()
    for scene in scenes:
        if scene.boundary_revision_id is None:
            scene.boundary_revision_id = revision.id
            if not hasattr(scene, "included_in_journey") or scene.included_in_journey is None:
                scene.included_in_journey = True
    return revision


def ensure_ai_model_revision_after_scenes_v1(
    session: Session, run: AnalysisRun
) -> BoundaryRevision | None:
    chapter_id = int(run.subject_id)
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        return None
    existing_model = session.scalar(
        select(BoundaryRevision)
        .where(
            BoundaryRevision.analysis_run_id == run.id,
            BoundaryRevision.source == "model",
        )
        .order_by(BoundaryRevision.id.desc())
    )
    if existing_model is not None:
        return existing_model
    scenes = run_scenes(session, run.id)
    if not scenes:
        return None
    review = _get_or_create_partition_session(session, run, chapter)
    chapter_hash = compute_chapter_text_hash_v1(session, chapter_id)
    partition = scenes_from_scene_rows(scenes)
    validate_scene_partition_v1(session, chapter_id, partition, expected_chapter_text_hash=chapter_hash)
    boundary_hash = compute_scene_boundary_hash_v1(chapter_id, chapter_hash, partition)
    revision = BoundaryRevision(
        review_session_id=review.id,
        chapter_id=chapter_id,
        analysis_run_id=run.id,
        revision_number=_next_revision_number(session, chapter_id, review.id),
        final_boundaries_json=dump_partition_json(partition),
        confirmed_by="model-pipeline",
        status="confirmed",
        source="model",
        chapter_text_hash=chapter_hash,
        boundary_hash=boundary_hash,
        revision_etag=_new_etag(),
    )
    session.add(revision)
    session.flush()
    for scene in scenes:
        scene.boundary_revision_id = revision.id
        scene.included_in_journey = True
        scene.boundary_source = scene.boundary_source or "model_accepted"
    return revision


def create_or_get_scene_boundary_draft_v1(
    session: Session,
    chapter_id: int,
    *,
    confirmed_by: str = "user",
) -> BoundaryRevision:
    draft = _draft_revision(session, chapter_id)
    if draft is not None:
        return draft
    base = _confirmed_revision(session, chapter_id)
    if base is None:
        base = ensure_legacy_confirmed_revision_v1(session, chapter_id)
    if base is None:
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY", "No confirmed revision to fork")
    scenes = parse_partition_json(base.final_boundaries_json)
    if not scenes:
        rows = revision_scenes(session, base.id)
        scenes = scenes_from_scene_rows(rows)
    chapter_hash = compute_chapter_text_hash_v1(session, chapter_id)
    partition = deepcopy_partition(scenes)
    validate_scene_partition_v1(session, chapter_id, partition, expected_chapter_text_hash=chapter_hash)
    review = session.get(BoundaryReviewSession, base.review_session_id) if base.review_session_id else None
    if review is None:
        run = session.get(AnalysisRun, base.analysis_run_id)
        chapter = session.get(Chapter, chapter_id)
        if run is None or chapter is None:
            raise SceneBoundaryError("SCENE_PARTITION_EMPTY")
        review = _get_or_create_partition_session(session, run, chapter)
    revision = BoundaryRevision(
        review_session_id=review.id,
        chapter_id=chapter_id,
        analysis_run_id=base.analysis_run_id,
        revision_number=_next_revision_number(session, chapter_id, review.id),
        final_boundaries_json=dump_partition_json(partition),
        confirmed_by=confirmed_by,
        status="draft",
        source="user",
        based_on_revision_id=base.id,
        chapter_text_hash=chapter_hash,
        boundary_hash=compute_scene_boundary_hash_v1(chapter_id, chapter_hash, partition),
        revision_etag=_new_etag(),
    )
    session.add(revision)
    session.flush()
    return revision


def deepcopy_partition(scenes: list[dict]) -> list[dict]:
    return [dict(item) for item in sorted(scenes, key=lambda x: int(x["scene_order"]))]


def save_scene_boundary_draft_v1(
    session: Session,
    revision_id: int,
    scenes: list[dict],
    *,
    expected_etag: str,
) -> BoundaryRevision:
    revision = session.get(BoundaryRevision, revision_id)
    if revision is None or revision.status != "draft":
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY")
    if revision.revision_etag != expected_etag:
        raise SceneBoundaryError("SCENE_REVISION_CONCURRENT_MODIFICATION")
    chapter_hash = compute_chapter_text_hash_v1(session, revision.chapter_id)
    if revision.chapter_text_hash and revision.chapter_text_hash != chapter_hash:
        raise SceneBoundaryError("SCENE_PARTITION_CHAPTER_CHANGED")
    validate_scene_partition_v1(
        session, revision.chapter_id, scenes, expected_chapter_text_hash=chapter_hash
    )
    revision.final_boundaries_json = dump_partition_json(scenes)
    revision.chapter_text_hash = chapter_hash
    revision.boundary_hash = compute_scene_boundary_hash_v1(
        revision.chapter_id, chapter_hash, scenes
    )
    revision.revision_etag = _new_etag()
    revision.updated_at = _now()
    return revision


def discard_scene_boundary_draft_v1(session: Session, revision_id: int) -> None:
    revision = session.get(BoundaryRevision, revision_id)
    if revision is None or revision.status != "draft":
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY")
    session.delete(revision)


def restore_ai_partition_into_draft_v1(session: Session, revision_id: int) -> BoundaryRevision:
    draft = session.get(BoundaryRevision, revision_id)
    if draft is None or draft.status != "draft":
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY")
    model = _model_revision(session, draft.chapter_id)
    if model is None:
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY", "No AI model revision")
    scenes = parse_partition_json(model.final_boundaries_json)
    if not scenes:
        scenes = scenes_from_scene_rows(revision_scenes(session, model.id))
    return save_scene_boundary_draft_v1(
        session,
        revision_id,
        deepcopy_partition(scenes),
        expected_etag=draft.revision_etag,
    )


def _materialize_scenes_for_revision(
    session: Session,
    revision: BoundaryRevision,
    scenes: list[dict],
    *,
    based_on_revision_id: int | None,
) -> list[Scene]:
    chapter = session.get(Chapter, revision.chapter_id)
    run = session.get(AnalysisRun, revision.analysis_run_id)
    if chapter is None or run is None:
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY")
    old_scenes = revision_scenes(session, based_on_revision_id) if based_on_revision_id else []
    old_by_hash = {item.content_hash: item for item in old_scenes}
    created: list[Scene] = []
    for item in sorted(scenes, key=lambda x: int(x["scene_order"])):
        ordinal = int(item["scene_order"])
        content_hash = _scene_content_hash(
            session, item["start_paragraph_id"], item["end_paragraph_id"]
        )
        source_scene = old_by_hash.get(content_hash)
        scene = Scene(
            scene_key=(
                f"B{chapter.book_id:04d}-C{chapter.chapter_index:04d}-"
                f"R{revision.id:04d}-S{ordinal:04d}"
            ),
            book_id=chapter.book_id,
            chapter_id=chapter.id,
            ordinal=ordinal,
            start_paragraph_id=item["start_paragraph_id"],
            end_paragraph_id=item["end_paragraph_id"],
            content_hash=content_hash,
            created_by_run_id=run.id,
            boundary_detected=True,
            boundary_confidence=1.0,
            boundary_reason_json="[]",
            boundary_revision_id=revision.id,
            boundary_source="user_edited" if source_scene is None else "user_accepted",
            included_in_journey=bool(item.get("included_in_journey", True)),
            source_scene_id=source_scene.id if source_scene else None,
        )
        session.add(scene)
        session.flush()
        if source_scene is not None:
            # Carry scene_analysis artifacts so unchanged spans remain journey-ready.
            for artifact in session.scalars(
                select(AnalysisArtifact).where(
                    AnalysisArtifact.run_id == run.id,
                    AnalysisArtifact.artifact_type == "scene_analysis",
                    AnalysisArtifact.subject_id == str(source_scene.id),
                )
            ):
                clone = AnalysisArtifact(
                    run_id=run.id,
                    artifact_type=artifact.artifact_type,
                    subject_type=artifact.subject_type,
                    subject_id=str(scene.id),
                    schema_version=artifact.schema_version,
                    prompt_version=artifact.prompt_version,
                    payload_json=artifact.payload_json,
                    confidence=artifact.confidence,
                    validation_status=artifact.validation_status,
                )
                session.add(clone)
                session.flush()
                for evidence in session.scalars(
                    select(AnalysisEvidence).where(AnalysisEvidence.artifact_id == artifact.id)
                ):
                    session.add(
                        AnalysisEvidence(
                            artifact_id=clone.id,
                            field_path=evidence.field_path,
                            paragraph_id=evidence.paragraph_id,
                            paragraph_hash=evidence.paragraph_hash,
                        )
                    )
        created.append(scene)
    return created


def confirm_scene_revision_v1(
    session: Session,
    revision_id: int,
    *,
    expected_etag: str,
    confirmed_by: str = "user",
) -> BoundaryRevision:
    revision = session.get(BoundaryRevision, revision_id)
    if revision is None:
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY")
    if revision.status == "confirmed":
        if revision.revision_etag == expected_etag or not expected_etag:
            return revision
        raise SceneBoundaryError("SCENE_REVISION_CONCURRENT_MODIFICATION")
    if revision.status != "draft":
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY")
    if revision.revision_etag != expected_etag:
        raise SceneBoundaryError("SCENE_REVISION_CONCURRENT_MODIFICATION")
    scenes = parse_partition_json(revision.final_boundaries_json)
    chapter_hash = compute_chapter_text_hash_v1(session, revision.chapter_id)
    validate_scene_partition_v1(
        session, revision.chapter_id, scenes, expected_chapter_text_hash=chapter_hash
    )
    for old in session.scalars(
        select(BoundaryRevision).where(
            BoundaryRevision.chapter_id == revision.chapter_id,
            BoundaryRevision.status == "confirmed",
            BoundaryRevision.id != revision.id,
        )
    ):
        old.status = "superseded"
        old.superseded_at = _now()
    for journey in session.scalars(
        select(ReaderJourneyRun).where(
            ReaderJourneyRun.chapter_id == revision.chapter_id,
            ReaderJourneyRun.result_status == "current",
        )
    ):
        journey.result_status = "superseded"
    revision.status = "confirmed"
    revision.confirmed_by = confirmed_by
    revision.confirmed_at = _now()
    revision.chapter_text_hash = chapter_hash
    revision.boundary_hash = compute_scene_boundary_hash_v1(
        revision.chapter_id, chapter_hash, scenes
    )
    revision.revision_etag = _new_etag()
    based_on = revision.based_on_revision_id
    _materialize_scenes_for_revision(session, revision, scenes, based_on_revision_id=based_on)
    return revision


def bind_journey_to_revision(
    session: Session,
    journey: ReaderJourneyRun,
    revision: BoundaryRevision,
    scenes: list[Scene],
) -> None:
    included = [scene for scene in scenes if bool(getattr(scene, "included_in_journey", True))]
    chapter_hash = revision.chapter_text_hash or compute_chapter_text_hash_v1(
        session, revision.chapter_id
    )
    input_hashes = {
        str(scene.id): compute_scene_journey_input_hash_v1(
            chapter_text_hash=chapter_hash,
            scene_text_hash=scene.content_hash,
            included_in_journey=True,
            journey_prompt_version=journey.scene_prompt_version,
            journey_contract_version=journey.scene_contract_version,
            provider_id=journey.provider_name,
            model_id=journey.model_name,
        )
        for scene in included
    }
    journey.scene_revision_id = revision.id
    journey.scene_revision_no = revision.revision_number
    journey.scene_boundary_hash = revision.boundary_hash
    journey.chapter_text_hash = revision.chapter_text_hash
    journey.included_scene_ids_json = json.dumps([scene.id for scene in included])
    journey.included_scene_input_hashes_json = json.dumps(input_hashes, ensure_ascii=False)
    journey.result_status = "current"
    journey.total_scene_count = len(included)
    journey.remaining_scene_count = len(included)
    journey.completed_scene_count = 0
    journey.completed_scene_ids_json = "[]"
    journey.remaining_scene_ids_json = json.dumps([scene.id for scene in included])


async def confirm_scene_revision_and_start_journey_v1(
    session: Session,
    revision_id: int,
    *,
    expected_etag: str,
    start_journey: bool,
    journey_options: dict[str, Any] | None = None,
    session_factory=None,
    gateway=None,
) -> tuple[BoundaryRevision, ReaderJourneyRun | None]:
    del journey_options
    revision = confirm_scene_revision_v1(
        session, revision_id, expected_etag=expected_etag, confirmed_by="user"
    )
    session.flush()
    if not start_journey:
        return revision, None
    from app.services.chapter_analysis_completion import ensure_auto_reader_journey_row

    run = session.get(AnalysisRun, revision.analysis_run_id)
    if run is None:
        raise SceneBoundaryError("SCENE_CONFIRMED_JOURNEY_NOT_STARTED")
    journey = ensure_auto_reader_journey_row(session, run)
    if journey is None:
        raise SceneBoundaryError("SCENE_CONFIRMED_JOURNEY_NOT_STARTED")
    scenes = revision_scenes(session, revision.id)
    bind_journey_to_revision(session, journey, revision, scenes)
    session.commit()
    if session_factory is not None and gateway is not None:
        from app.services.reader_journey_pipeline import execute_reader_journey

        await execute_reader_journey(session_factory, gateway, journey.id)
    return revision, journey


def get_scene_boundaries_overview_v1(session: Session, chapter_id: int) -> dict[str, Any]:
    ensure_legacy_confirmed_revision_v1(session, chapter_id)
    confirmed = _confirmed_revision(session, chapter_id)
    draft = _draft_revision(session, chapter_id)
    model = _model_revision(session, chapter_id)
    chapter_hash = compute_chapter_text_hash_v1(session, chapter_id)

    def _pack(revision: BoundaryRevision | None) -> dict[str, Any] | None:
        if revision is None:
            return None
        scenes = parse_partition_json(revision.final_boundaries_json)
        if not scenes:
            scenes = scenes_from_scene_rows(revision_scenes(session, revision.id))
        return {
            "revision_id": revision.id,
            "revision_number": revision.revision_number,
            "status": revision.status,
            "source": revision.source,
            "revision_etag": revision.revision_etag,
            "boundary_hash": revision.boundary_hash,
            "chapter_text_hash": revision.chapter_text_hash,
            "scenes": scenes,
            "confirmed_at": revision.confirmed_at.isoformat() if revision.confirmed_at else None,
        }

    return {
        "chapter_id": chapter_id,
        "chapter_text_hash": chapter_hash,
        "confirmed_revision": _pack(confirmed),
        "draft_revision": _pack(draft),
        "model_revision": _pack(model),
        "awaiting_confirmation": confirmed is not None and draft is None and model is not None,
    }


def compute_diff_summary_v1(
    session: Session,
    revision_id: int,
    *,
    against_revision_id: int | None = None,
) -> dict[str, Any]:
    revision = session.get(BoundaryRevision, revision_id)
    if revision is None:
        raise SceneBoundaryError("SCENE_PARTITION_EMPTY")
    left_scenes = parse_partition_json(revision.final_boundaries_json)
    if not left_scenes:
        left_scenes = scenes_from_scene_rows(revision_scenes(session, revision.id))
    against_id = against_revision_id or revision.based_on_revision_id
    if against_id is None:
        return {"changes": [], "scene_count_delta": len(left_scenes)}
    base = session.get(BoundaryRevision, against_id)
    if base is None:
        return {"changes": [], "scene_count_delta": len(left_scenes)}
    right_scenes = parse_partition_json(base.final_boundaries_json)
    if not right_scenes:
        right_scenes = scenes_from_scene_rows(revision_scenes(session, base.id))
    changes: list[dict[str, Any]] = []
    for index, left in enumerate(left_scenes):
        right = right_scenes[index] if index < len(right_scenes) else None
        if right is None:
            changes.append({"type": "added_scene", "scene_order": left["scene_order"]})
            continue
        if (
            left["start_paragraph_id"] != right["start_paragraph_id"]
            or left["end_paragraph_id"] != right["end_paragraph_id"]
        ):
            changes.append(
                {
                    "type": "boundary_moved",
                    "scene_order": left["scene_order"],
                    "from": {
                        "start": right["start_paragraph_id"],
                        "end": right["end_paragraph_id"],
                    },
                    "to": {
                        "start": left["start_paragraph_id"],
                        "end": left["end_paragraph_id"],
                    },
                }
            )
        if bool(left.get("included_in_journey", True)) != bool(
            right.get("included_in_journey", True)
        ):
            changes.append(
                {
                    "type": "included_changed",
                    "scene_order": left["scene_order"],
                    "included": bool(left.get("included_in_journey", True)),
                }
            )
    if len(left_scenes) < len(right_scenes):
        for extra in right_scenes[len(left_scenes) :]:
            changes.append({"type": "removed_scene", "scene_order": extra["scene_order"]})
    return {
        "revision_id": revision_id,
        "against_revision_id": against_id,
        "changes": changes,
        "scene_count_delta": len(left_scenes) - len(right_scenes),
    }


def find_reusable_scene_journey_profile(
    session: Session,
    *,
    chapter_id: int,
    scene_journey_input_hash: str,
) -> SceneReaderJourneyProfile | None:
    journeys = list(
        session.scalars(
            select(ReaderJourneyRun)
            .where(
                ReaderJourneyRun.chapter_id == chapter_id,
                ReaderJourneyRun.result_status == "current",
            )
            .order_by(ReaderJourneyRun.id.desc())
        )
    )
    for journey in journeys:
        try:
            mapping = json.loads(journey.included_scene_input_hashes_json or "{}")
        except json.JSONDecodeError:
            mapping = {}
        for scene_id, digest in mapping.items():
            if digest == scene_journey_input_hash:
                return session.scalar(
                    select(SceneReaderJourneyProfile).where(
                        SceneReaderJourneyProfile.reader_journey_run_id == journey.id,
                        SceneReaderJourneyProfile.scene_id == int(scene_id),
                        SceneReaderJourneyProfile.validation_status == "valid",
                    )
                )
    return None


def plan_scene_reuse(
    session: Session,
    journey_run: ReaderJourneyRun,
    scenes: list[Scene],
) -> dict[int, SceneReaderJourneyProfile | None]:
    try:
        stored = json.loads(journey_run.included_scene_input_hashes_json or "{}")
    except json.JSONDecodeError:
        stored = {}
    plan: dict[int, SceneReaderJourneyProfile | None] = {}
    for scene in scenes:
        if not bool(getattr(scene, "included_in_journey", True)):
            continue
        digest = stored.get(str(scene.id)) or compute_scene_journey_input_hash_v1(
            chapter_text_hash=journey_run.chapter_text_hash
            or compute_chapter_text_hash_v1(session, scene.chapter_id),
            scene_text_hash=scene.content_hash,
            included_in_journey=True,
            journey_prompt_version=journey_run.scene_prompt_version,
            journey_contract_version=journey_run.scene_contract_version,
            provider_id=journey_run.provider_name,
            model_id=journey_run.model_name,
        )
        profile = find_reusable_scene_journey_profile(
            session,
            chapter_id=scene.chapter_id,
            scene_journey_input_hash=digest,
        )
        plan[scene.id] = profile
    return plan


def load_journey_bound_scenes(
    session: Session, journey_run: ReaderJourneyRun
) -> tuple[BoundaryRevision | None, list[Scene]]:
    revision_id = journey_run.scene_revision_id
    if revision_id is not None:
        revision = session.get(BoundaryRevision, revision_id)
        if revision is None:
            raise SceneBoundaryError("JOURNEY_SCENE_REVISION_MISMATCH")
        if journey_run.scene_boundary_hash and revision.boundary_hash != journey_run.scene_boundary_hash:
            raise SceneBoundaryError("JOURNEY_SCENE_REVISION_MISMATCH")
        if journey_run.chapter_text_hash and revision.chapter_text_hash != journey_run.chapter_text_hash:
            raise SceneBoundaryError("JOURNEY_SCENE_REVISION_MISMATCH")
        try:
            included_ids = json.loads(journey_run.included_scene_ids_json or "[]")
        except json.JSONDecodeError:
            included_ids = []
        scenes = revision_scenes(session, revision_id)
        if included_ids:
            allowed = {int(item) for item in included_ids}
            scenes = [scene for scene in scenes if scene.id in allowed]
        else:
            scenes = [
                scene
                for scene in scenes
                if bool(getattr(scene, "included_in_journey", True))
            ]
        return revision, scenes
    legacy = ensure_legacy_confirmed_revision_v1(session, journey_run.chapter_id)
    if legacy is None:
        raise SceneBoundaryError("SCENE_REVISION_REQUIRED")
    journey_run.result_status = "legacy_revision_unresolved"
    scenes = revision_scenes(session, legacy.id)
    scenes = [scene for scene in scenes if bool(getattr(scene, "included_in_journey", True))]
    return legacy, scenes


# Re-export partition ops for API convenience
__all__ = [
    "SceneBoundaryError",
    "compute_scene_boundary_hash_v1",
    "compute_scene_journey_input_hash_v1",
    "validate_scene_partition_v1",
    "create_or_get_scene_boundary_draft_v1",
    "save_scene_boundary_draft_v1",
    "discard_scene_boundary_draft_v1",
    "restore_ai_partition_into_draft_v1",
    "confirm_scene_revision_v1",
    "confirm_scene_revision_and_start_journey_v1",
    "ensure_legacy_confirmed_revision_v1",
    "ensure_ai_model_revision_after_scenes_v1",
    "move_boundary",
    "add_boundary",
    "delete_boundary",
    "delete_scene_merge",
    "set_included",
    "get_scene_boundaries_overview_v1",
    "compute_diff_summary_v1",
    "find_reusable_scene_journey_profile",
    "plan_scene_reuse",
    "bind_journey_to_revision",
    "revision_scenes",
    "load_journey_bound_scenes",
    "compute_chapter_text_hash_v1",
    "get_confirmed_revision",
    "run_scenes",
]
