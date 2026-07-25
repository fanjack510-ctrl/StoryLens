"""Build WholeBookInsightsInputV1-shaped payload from persisted chapter analyses."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    Book,
    Chapter,
    ReaderJourneyRun,
    Scene,
    SceneReaderJourneyProfile,
)
from app.services.chapter_analysis_completion import (
    chapter_completion_payload,
    is_chapter_analysis_complete,
)

INPUT_SCHEMA = "storylens.whole_book_insights.input.v1"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _scene_analysis_by_scene(session: Session, run_id: int) -> dict[int, dict[str, Any]]:
    rows = session.scalars(
        select(AnalysisArtifact).where(
            AnalysisArtifact.run_id == run_id,
            AnalysisArtifact.artifact_type == "scene_analysis",
            AnalysisArtifact.subject_type == "scene",
        )
    ).all()
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        try:
            scene_id = int(row.subject_id)
        except ValueError:
            continue
        payload = _parse_json(row.payload_json, {})
        if isinstance(payload, dict):
            out[scene_id] = payload
    return out


def _latest_completed_run(session: Session, chapter_id: int) -> AnalysisRun | None:
    runs = session.scalars(
        select(AnalysisRun)
        .where(
            AnalysisRun.subject_type == "chapter",
            AnalysisRun.subject_id == str(chapter_id),
            AnalysisRun.task_type == "scene_pipeline",
        )
        .order_by(AnalysisRun.id.desc())
    ).all()
    for run in runs:
        if is_chapter_analysis_complete(session, run):
            return run
    return None


def _usable_journey_profile(profile: SceneReaderJourneyProfile) -> bool:
    if profile.validation_status != "valid":
        return False
    scores = (profile.tension_score, profile.hook_score, profile.payoff_score)
    return all(isinstance(item, int) and 0 <= item <= 100 for item in scores)


def _build_deep_link(
    *,
    chapter_id: int,
    scene_id: int | None,
    evidence_paragraph_ids: list[str],
) -> dict[str, Any]:
    paragraph_id = evidence_paragraph_ids[0] if evidence_paragraph_ids else None
    return {
        "chapter_id": chapter_id,
        "scene_id": scene_id,
        "paragraph_id": paragraph_id,
        "chapter_level": paragraph_id is None,
    }


def _scene_payload(
    *,
    chapter_id: int,
    scene: Scene,
    profile: SceneReaderJourneyProfile,
    scene_analysis: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _parse_json(profile.payload_json, {})
    hooks = payload.get("hooks") if isinstance(payload, dict) else []
    payoffs = payload.get("payoffs") if isinstance(payload, dict) else []
    risk_points = payload.get("risk_points") if isinstance(payload, dict) else []
    evidence_ids = (
        list(payload.get("evidence_paragraph_ids") or [])
        if isinstance(payload, dict)
        else []
    )
    if not evidence_ids:
        evidence_ids = _parse_json(getattr(profile, "payload_json", None), {}).get(
            "evidence_paragraph_ids", []
        )
    function_tags: list[str] = []
    if scene_analysis:
        raw_tags = scene_analysis.get("function_tags") or []
        if isinstance(raw_tags, list):
            function_tags = [str(item) for item in raw_tags if str(item).strip()]
    return {
        "scene_id": scene.id,
        "scene_ordinal": scene.ordinal,
        "tension_score": profile.tension_score,
        "hook_score": profile.hook_score,
        "payoff_score": profile.payoff_score,
        "hooks": hooks if isinstance(hooks, list) else [],
        "payoffs": payoffs if isinstance(payoffs, list) else [],
        "risk_points": risk_points if isinstance(risk_points, list) else [],
        "evidence_paragraph_ids": evidence_ids if isinstance(evidence_ids, list) else [],
        "payload_json": profile.payload_json,
        "function_tags": function_tags,
        "deep_link": _build_deep_link(
            chapter_id=chapter_id,
            scene_id=scene.id,
            evidence_paragraph_ids=evidence_ids if isinstance(evidence_ids, list) else [],
        ),
    }


def build_whole_book_insights_input(session: Session, book_id: int) -> dict[str, Any]:
    book = session.get(Book, book_id)
    if book is None:
        raise ValueError("book_not_found")

    chapters = list(
        session.scalars(
            select(Chapter)
            .where(Chapter.book_id == book_id, Chapter.section_type == "chapter")
            .order_by(Chapter.chapter_index)
        ).all()
    )
    if not chapters:
        chapters = list(
            session.scalars(
                select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index)
            ).all()
        )

    chapter_rows: list[dict[str, Any]] = []
    valid_count = 0

    for chapter in chapters:
        run = _latest_completed_run(session, chapter.id)
        completion = chapter_completion_payload(session, run) if run else None
        chapter_entry: dict[str, Any] = {
            "chapter_id": chapter.id,
            "chapter_index": chapter.chapter_index,
            "chapter_title": chapter.chapter_title or chapter.title,
            "display_title": chapter.display_title or chapter.title,
            "analysis_run_id": run.id if run else None,
            "analysis_status": run.status if run else None,
            "effective_status": completion["effective_status"] if completion else None,
            "completed_at": _iso(run.completed_at if run else None),
            "is_valid": False,
            "stale": False,
            "scenes": [],
        }

        if run is None or completion is None or completion["effective_status"] != "completed":
            chapter_rows.append(chapter_entry)
            continue

        journey = session.scalar(
            select(ReaderJourneyRun)
            .where(ReaderJourneyRun.analysis_run_id == run.id)
            .order_by(ReaderJourneyRun.id.desc())
        )
        if journey is None or journey.status != "succeeded":
            chapter_rows.append(chapter_entry)
            continue

        scenes = list(
            session.scalars(
                select(Scene)
                .where(Scene.created_by_run_id == run.id)
                .order_by(Scene.ordinal)
            ).all()
        )
        profiles = {
            row.scene_id: row
            for row in session.scalars(
                select(SceneReaderJourneyProfile).where(
                    SceneReaderJourneyProfile.reader_journey_run_id == journey.id
                )
            ).all()
        }
        scene_analysis = _scene_analysis_by_scene(session, run.id)

        scene_rows: list[dict[str, Any]] = []
        for scene in scenes:
            profile = profiles.get(scene.id)
            if profile is None or not _usable_journey_profile(profile):
                continue
            scene_rows.append(
                _scene_payload(
                    chapter_id=chapter.id,
                    scene=scene,
                    profile=profile,
                    scene_analysis=scene_analysis.get(scene.id),
                )
            )

        chapter_entry["scenes"] = scene_rows
        chapter_entry["is_valid"] = len(scene_rows) > 0
        if chapter_entry["is_valid"]:
            valid_count += 1
        chapter_rows.append(chapter_entry)

    return {
        "schema": INPUT_SCHEMA,
        "book_id": book.id,
        "book_title": book.title,
        "chapters": chapter_rows,
        "coverage": {
            "total_chapters": len(chapter_rows),
            "valid_chapters": valid_count,
            "invalid_chapters": len(chapter_rows) - valid_count,
        },
        "generated_at": _iso(datetime.now(timezone.utc)),
    }
