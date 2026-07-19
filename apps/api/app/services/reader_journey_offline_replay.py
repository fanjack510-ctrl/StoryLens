"""Offline Reader Journey replay from stored invocations (zero HTTP)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun,
    ModelInvocation,
    Paragraph,
    ReaderJourneyRun,
    SceneReaderJourneyProfile,
)
from app.schemas.reader_journey import (
    SCENE_CONTRACT_VERSION,
    SCENE_PROMPT_VERSION,
    SceneReaderJourneyBatchResult,
)
from app.services.reader_journey_contract_migrate import migrate_v11_batch_dict_to_v12
from app.services.reader_journey_pipeline import _paragraph_ids_for_scene, _persist_profile
from app.services.reader_journey_progress import (
    is_scene_profile_complete,
    load_revision_scenes,
    sync_journey_run_counts,
)
from app.services.reader_journey_validation import validate_scene_batch_result
from app.services.validation_errors import StructuralValidationError

REPLAYABLE_EMPTY_Q_IN_CODES = {
    "JOURNEY_QUESTION_CHAIN_INVALID",
    "STRUCTURAL_VALIDATION_FAILED",
    "BUSINESS_VALIDATION_FAILED",
}
REPLAYABLE_EMPTY_Q_IN_MESSAGE = "reader_question_in 不得全部为空"


@dataclass(frozen=True)
class ReplayCandidate:
    invocation_id: int
    scene_ids: list[int]
    migrated_from_contract_version: str
    eligible_reason: str


def _parse_snapshot(inv: ModelInvocation) -> dict[str, Any]:
    try:
        payload = json.loads(inv.input_snapshot_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _owned_scene_ids(snapshot: dict[str, Any]) -> list[int]:
    raw = snapshot.get("owned_scene_ids_json")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [int(item) for item in parsed]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    profiles_target = snapshot.get("profiles_target")
    if isinstance(profiles_target, list):
        ids = []
        for item in profiles_target:
            if isinstance(item, dict) and item.get("scene_id") is not None:
                ids.append(int(item["scene_id"]))
        return ids
    return []


def _load_scene_paragraph_ids(
    session: Session,
    journey_run: ReaderJourneyRun,
    scene_ids: list[int],
) -> dict[int, set[str]]:
    analysis_run = session.get(AnalysisRun, journey_run.analysis_run_id)
    if analysis_run is None:
        return {}
    _revision, scenes = load_revision_scenes(session, analysis_run.id)
    scene_by_id = {scene.id: scene for scene in scenes}
    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == journey_run.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    position = {item.id: index for index, item in enumerate(paragraphs)}
    result: dict[int, set[str]] = {}
    for scene_id in scene_ids:
        scene = scene_by_id.get(scene_id)
        if scene is None:
            continue
        result[scene_id] = _paragraph_ids_for_scene(scene, paragraphs, position)
    return result


def _invocation_has_replayable_failure(inv: ModelInvocation) -> bool:
    message = (inv.error_message or "").strip()
    code = inv.error_code or ""
    if REPLAYABLE_EMPTY_Q_IN_MESSAGE in message:
        return True
    if code in REPLAYABLE_EMPTY_Q_IN_CODES and REPLAYABLE_EMPTY_Q_IN_MESSAGE in message:
        return True
    if code == "JOURNEY_QUESTION_CHAIN_INVALID" and "不得全部为空" in message:
        return True
    return False


def _parse_and_validate_batch(
    session: Session,
    journey_run: ReaderJourneyRun,
    inv: ModelInvocation,
    *,
    prior_summaries: list[str] | None = None,
    prior_high_strength_outs: list[str] | None = None,
) -> tuple[SceneReaderJourneyBatchResult, str] | tuple[None, str]:
    if not inv.parsed_response_json:
        return None, "missing parsed_response_json"
    try:
        raw = json.loads(inv.parsed_response_json)
    except json.JSONDecodeError as exc:
        return None, f"invalid parsed JSON: {exc}"
    if not isinstance(raw, dict):
        return None, "parsed payload not an object"
    contract = str(raw.get("contract_version", "1.1"))
    if contract.startswith("1.1") or contract == "1.1":
        migrated, migrated_from = migrate_v11_batch_dict_to_v12(raw)
    elif contract.startswith("1.2"):
        migrated = raw
        migrated_from = contract
    else:
        return None, f"unsupported contract_version {contract}"

    try:
        batch = SceneReaderJourneyBatchResult.model_validate(migrated)
    except Exception as exc:
        return None, f"schema validation failed: {exc}"

    snapshot = _parse_snapshot(inv)
    scene_ids = _owned_scene_ids(snapshot)
    if not scene_ids:
        scene_ids = [profile.scene_id for profile in batch.profiles]
    paragraph_ids_by_scene = _load_scene_paragraph_ids(session, journey_run, scene_ids)
    try:
        validate_scene_batch_result(
            batch,
            expected_scene_ids=set(scene_ids),
            paragraph_ids_by_scene=paragraph_ids_by_scene,
            prior_summaries=prior_summaries,
            prior_high_strength_outs=prior_high_strength_outs,
        )
    except StructuralValidationError as exc:
        return None, f"{exc.error_code}: {exc}"
    return batch, migrated_from


def find_replayable_journey_invocations(
    session: Session,
    journey_run: ReaderJourneyRun,
) -> list[ReplayCandidate]:
    analysis_run = session.get(AnalysisRun, journey_run.analysis_run_id)
    if analysis_run is None:
        return []
    invocations = list(
        session.scalars(
            select(ModelInvocation)
            .where(
                ModelInvocation.run_id == analysis_run.id,
                ModelInvocation.task_type == "reader_journey_scene",
                ModelInvocation.parsed_response_json.is_not(None),
            )
            .order_by(ModelInvocation.id.desc())
        )
    )
    candidates: list[ReplayCandidate] = []
    claimed_scenes: set[int] = set()
    for inv in invocations:
        if inv.http_status_code not in (None, 200) and inv.status != "failed":
            continue
        if inv.status == "failed" and not _invocation_has_replayable_failure(inv):
            if not inv.parsed_response_json:
                continue
        batch, migrated_from = _parse_and_validate_batch(
            session,
            journey_run,
            inv,
        )
        if batch is None:
            continue
        snapshot = _parse_snapshot(inv)
        scene_ids = _owned_scene_ids(snapshot) or [p.scene_id for p in batch.profiles]
        pending = [
            sid
            for sid in scene_ids
            if sid not in claimed_scenes
            and not is_scene_profile_complete(session, journey_run.id, sid)
        ]
        if not pending:
            continue
        eligible = _invocation_has_replayable_failure(inv) or migrated_from.startswith("1.1")
        if not eligible and inv.status != "succeeded":
            continue
        candidates.append(
            ReplayCandidate(
                invocation_id=inv.id,
                scene_ids=pending,
                migrated_from_contract_version=migrated_from,
                eligible_reason="empty_q_in_v11" if migrated_from.startswith("1.1") else "v12_valid",
            )
        )
        claimed_scenes.update(pending)
    # Present in ascending invocation order for stable reporting, but keep latest-first claim.
    candidates.sort(key=lambda item: item.invocation_id)
    return candidates


def offline_replay_journey_profiles(
    session: Session,
    journey_run_id: int,
    *,
    invocation_ids: list[int] | None = None,
) -> dict[str, Any]:
    journey_run = session.get(ReaderJourneyRun, journey_run_id)
    if journey_run is None:
        raise ValueError("READER_JOURNEY_RUN_NOT_FOUND")

    candidates = find_replayable_journey_invocations(session, journey_run)
    if invocation_ids is not None:
        allowed = set(invocation_ids)
        candidates = [item for item in candidates if item.invocation_id in allowed]

    paragraphs = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == journey_run.chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    by_id = {item.id: item for item in paragraphs}

    replayed_scene_ids: list[int] = []
    source_invocation_ids: list[int] = []
    migrated_from: str | None = None
    idempotent = True
    errors: list[str] = []

    prior_summaries = [
        row.scene_value_summary
        for row in session.scalars(
            select(SceneReaderJourneyProfile)
            .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id)
            .order_by(SceneReaderJourneyProfile.scene_ordinal)
        )
    ]
    prior_outs: list[str] = []

    for candidate in candidates:
        inv = session.get(ModelInvocation, candidate.invocation_id)
        if inv is None:
            continue
        batch, from_version = _parse_and_validate_batch(
            session,
            journey_run,
            inv,
            prior_summaries=prior_summaries,
            prior_high_strength_outs=prior_outs,
        )
        if batch is None:
            errors.append(f"invocation {inv.id}: validation failed after migrate")
            continue
        migrated_from = migrated_from or from_version
        source_invocation_ids.append(inv.id)
        paragraph_ids_by_scene = _load_scene_paragraph_ids(session, journey_run, candidate.scene_ids)
        for profile in batch.profiles:
            if profile.scene_id not in candidate.scene_ids:
                continue
            if is_scene_profile_complete(session, journey_run.id, profile.scene_id):
                continue
            allowed = paragraph_ids_by_scene.get(profile.scene_id, set())
            try:
                validate_scene_batch_result(
                    SceneReaderJourneyBatchResult(profiles=[profile]),
                    expected_scene_ids={profile.scene_id},
                    paragraph_ids_by_scene={profile.scene_id: allowed},
                    prior_summaries=prior_summaries,
                    prior_high_strength_outs=prior_outs,
                )
            except StructuralValidationError as exc:
                errors.append(f"scene {profile.scene_id}: {exc.error_code}")
                continue
            persisted = _persist_profile(
                session,
                journey_run,
                profile,
                paragraphs_by_id=by_id,
                genre=journey_run.genre,
            )
            if persisted is None:
                idempotent = idempotent and True
                continue
            idempotent = False
            replayed_scene_ids.append(profile.scene_id)
            prior_summaries.append(profile.scene_value_summary.strip())
            prior_outs.extend(
                item.question for item in profile.reader_question_out if item.strength >= 50
            )

    progress = sync_journey_run_counts(session, journey_run)
    if progress.remaining_scene_count == 0 and journey_run.status in {"failed", "scene_profiles_partial"}:
        journey_run.status = "scene_profiles_partial" if progress.completed_scene_count < progress.total_scene_count else journey_run.status
    if replayed_scene_ids and progress.remaining_scene_count < progress.total_scene_count:
        if journey_run.status == "failed" and progress.remaining_scene_count > 0:
            journey_run.status = "scene_profiles_partial"
            journey_run.retryable = True
        elif journey_run.status == "failed" and progress.remaining_scene_count == 0:
            journey_run.retryable = True

    if replayed_scene_ids or (idempotent and progress.completed_scene_count > 0):
        previous_contract = journey_run.scene_contract_version
        previous_prompt = journey_run.scene_prompt_version
        details: dict[str, Any] = {}
        try:
            details = json.loads(journey_run.failure_details_json or "{}")
        except json.JSONDecodeError:
            details = {}
        audits = details.get("resume_audit")
        audit_list = audits if isinstance(audits, list) else ([audits] if audits else [])
        audit_list.append(
            {
                "original_scene_contract_version": previous_contract,
                "original_scene_prompt_version": previous_prompt,
                "resumed_scene_contract_version": SCENE_CONTRACT_VERSION,
                "prompt_version": SCENE_PROMPT_VERSION,
                "planner_version": getattr(journey_run, "planner_version", None) or "1.1",
                "resume_reason": "offline_replay_contract_semantics_upgrade",
                "source_invocation_ids": source_invocation_ids,
                "replayed_scene_ids": replayed_scene_ids,
            }
        )
        details["resume_audit"] = audit_list
        journey_run.failure_details_json = json.dumps(details, ensure_ascii=False)
        journey_run.scene_contract_version = SCENE_CONTRACT_VERSION
        journey_run.scene_prompt_version = SCENE_PROMPT_VERSION
        if journey_run.status == "scene_profiles_partial":
            journey_run.retryable = True
            # Clear blocking empty-q_in pointer once opening scene is restored.
            if progress.completed_scene_count > 0:
                journey_run.root_error_code = None
                journey_run.root_error_message = None
                journey_run.failed_scene_id = None
                journey_run.failed_scene_ordinal = None
                journey_run.failed_invocation_id = None
                journey_run.failed_stage = None
                journey_run.completed_at = None

    session.commit()

    # Refresh counts after version/status updates for accurate response.
    progress = sync_journey_run_counts(session, journey_run)
    session.commit()

    return {
        "journey_run_id": journey_run_id,
        "replayed_scene_ids": replayed_scene_ids,
        "completed_count": progress.completed_scene_count,
        "remaining_count": progress.remaining_scene_count,
        "source_invocation_ids": source_invocation_ids,
        "migrated_from_contract_version": migrated_from,
        "current_contract_version": SCENE_CONTRACT_VERSION,
        "http_requests": 0,
        "tokens": 0,
        "cost": 0.0,
        "idempotent_replay": idempotent and not replayed_scene_ids,
        "errors": errors,
    }
