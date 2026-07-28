"""Reader Journey progress tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    BoundaryRevision,
    BoundaryReviewSession,
    ChapterReaderJourneySummary,
    CloudBudgetReservation,
    ModelInvocation,
    ReaderJourneyPhase,
    ReaderJourneyRun,
    Scene,
    SceneReaderJourneyProfile,
)
from app.schemas.reader_journey import SCENE_CONTRACT_VERSION, SCENE_PROMPT_VERSION
from app.services.reader_journey_batch_planner import PLANNER_VERSION
from app.services.utc_datetime import ensure_utc_aware


USER_ERROR_MESSAGES = {
    "OUTPUT_TRUNCATED": "模型输出达到上限，当前批次未形成有效JSON",
    "JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED": (
        "单个Scene的读者旅程Profile输出仍超过上限，无法继续拆批"
    ),
    "JOURNEY_QUESTION_CHAIN_INVALID": (
        "章节开场Scene允许没有入场问题。当前结果触发了旧版问题生命周期校验，"
        "建议升级契约并优先离线恢复现有响应。"
    ),
    "STRUCTURAL_VALIDATION_FAILED": (
        "章节开场Scene允许没有入场问题。当前结果触发了旧版问题生命周期校验，"
        "建议升级契约并优先离线恢复现有响应。"
    ),
    "JOURNEY_CONTRACT_VALIDATION_CONFLICT": (
        "契约语义冲突（如 created_in_scene 位置错误）；请离线重放或升级契约"
    ),
}

OLD_CONTRACT_USER_MESSAGE = (
    "此运行使用旧版读者问题契约（v1.1）。章节首 Scene 允许空 reader_question_in，"
    "新建问题应写入 reader_question_created。可使用零费用的离线重放恢复已解析结果。"
)


@dataclass(frozen=True)
class ReaderJourneyProgress:
    journey_run: ReaderJourneyRun
    total_scene_count: int
    completed_scene_ids: list[int]
    remaining_scene_ids: list[int]
    completed_scene_count: int
    remaining_scene_count: int
    phase_count: int
    has_chapter_summary: bool
    request_count: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    currency: str = "CNY"
    reservation_released: bool = True
    recovery_safe: bool = False
    blind_resume_blocked: bool = False
    resume_block_reason: str | None = None
    resume_preflight: dict[str, object] | None = None
    user_error_message: str | None = None
    offline_replay_available: bool = False
    offline_replayable_scene_count: int = 0
    offline_replayable_invocation_ids: list[int] | None = None
    current_contract_version: str | None = None
    recoverable_contract_version: str | None = None

    def as_dict(self) -> dict[str, object]:
        details = {}
        raw = getattr(self.journey_run, "failure_details_json", None) or "{}"
        try:
            details = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            details = {}
        return {
            "journey_run_id": self.journey_run.id,
            "analysis_run_id": self.journey_run.analysis_run_id,
            "status": self.journey_run.status,
            "current_stage": self.journey_run.current_stage,
            "total_scene_count": self.total_scene_count,
            "completed_scene_count": self.completed_scene_count,
            "remaining_scene_count": self.remaining_scene_count,
            "completed_scene_ids": list(self.completed_scene_ids),
            "remaining_scene_ids": list(self.remaining_scene_ids),
            "phase_count": self.phase_count,
            "has_chapter_summary": self.has_chapter_summary,
            "retryable": self.journey_run.retryable,
            "failed_stage": self.journey_run.failed_stage,
            "root_error_code": self.journey_run.root_error_code,
            "root_error_message": self.journey_run.root_error_message,
            "failed_scene_id": self.journey_run.failed_scene_id,
            "failed_scene_ordinal": self.journey_run.failed_scene_ordinal,
            "failed_invocation_id": self.journey_run.failed_invocation_id,
            "completed_at": ensure_utc_aware(self.journey_run.completed_at),
            "planner_version": getattr(self.journey_run, "planner_version", None),
            "current_planner_version": PLANNER_VERSION,
            "scene_prompt_version": self.journey_run.scene_prompt_version,
            "scene_contract_version": self.journey_run.scene_contract_version,
            "recovery_safe": self.recovery_safe,
            "blind_resume_blocked": self.blind_resume_blocked,
            "resume_block_reason": self.resume_block_reason,
            "reservation_released": self.reservation_released,
            "request_count": self.request_count,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
            "currency": self.currency,
            "failure_details": details or None,
            "resume_preflight": self.resume_preflight,
            "user_error_message": self.user_error_message,
            "offline_replay_available": self.offline_replay_available,
            "offline_replayable_scene_count": self.offline_replayable_scene_count,
            "offline_replayable_invocation_ids": list(self.offline_replayable_invocation_ids or []),
            "current_contract_version": self.current_contract_version,
            "recoverable_contract_version": self.recoverable_contract_version,
        }


def load_revision_scenes(session: Session, analysis_run_id: int) -> tuple[BoundaryRevision | None, list[Scene]]:
    review = session.scalar(
        select(BoundaryReviewSession)
        .where(BoundaryReviewSession.analysis_run_id == analysis_run_id)
        .order_by(BoundaryReviewSession.id.desc())
    )
    if review is not None:
        revision = session.scalar(
            select(BoundaryRevision)
            .where(
                BoundaryRevision.review_session_id == review.id,
                BoundaryRevision.status == "confirmed",
            )
            .order_by(BoundaryRevision.id.desc())
        )
        if revision is not None:
            scenes = list(
                session.scalars(
                    select(Scene)
                    .where(Scene.boundary_revision_id == revision.id)
                    .order_by(Scene.ordinal)
                )
            )
            if scenes:
                return revision, scenes
    from app.services.scene_boundary_manual_review import run_scenes

    scenes = run_scenes(session, analysis_run_id)
    if scenes:
        return None, scenes
    return None, []


def is_scene_profile_complete(session: Session, journey_run_id: int, scene_id: int) -> bool:
    profile = session.scalar(
        select(SceneReaderJourneyProfile).where(
            SceneReaderJourneyProfile.reader_journey_run_id == journey_run_id,
            SceneReaderJourneyProfile.scene_id == scene_id,
            SceneReaderJourneyProfile.validation_status == "valid",
        )
    )
    if profile is None:
        return False
    if profile.artifact_id is None:
        return True
    evidence_count = session.scalar(
        select(func.count())
        .select_from(AnalysisEvidence)
        .where(AnalysisEvidence.artifact_id == profile.artifact_id)
    )
    return int(evidence_count or 0) >= 0


def scene_analysis_artifact(session: Session, run_id: int, scene_id: int) -> AnalysisArtifact | None:
    return session.scalar(
        select(AnalysisArtifact)
        .where(
            AnalysisArtifact.run_id == run_id,
            AnalysisArtifact.artifact_type == "scene_analysis",
            AnalysisArtifact.subject_id == str(scene_id),
            AnalysisArtifact.validation_status == "valid",
        )
        .order_by(AnalysisArtifact.id.desc())
    )


def journey_invocation_usage(session: Session, analysis_run_id: int) -> dict[str, object]:
    rows = list(
        session.scalars(
            select(ModelInvocation).where(
                ModelInvocation.run_id == analysis_run_id,
                ModelInvocation.task_type.like("reader_journey%"),
            )
        )
    )
    total_tokens = 0
    cost = 0.0
    currency = "CNY"
    for row in rows:
        total_tokens += int(row.total_tokens or 0)
        if row.estimated_cost is not None:
            cost += float(row.estimated_cost)
        if row.currency:
            currency = row.currency
    return {
        "request_count": len(rows),
        "total_tokens": total_tokens,
        "estimated_cost": round(cost, 6),
        "currency": currency,
    }


def has_active_reservation(session: Session, analysis_run_id: int) -> bool:
    row = session.scalar(
        select(CloudBudgetReservation).where(
            CloudBudgetReservation.run_id == analysis_run_id,
            CloudBudgetReservation.released_at.is_(None),
            CloudBudgetReservation.stage.like("reader_journey%"),
        )
    )
    return row is not None


def user_error_for_code(code: str | None) -> str | None:
    if not code:
        return None
    return USER_ERROR_MESSAGES.get(code)


def recovery_flags(
    journey_run: ReaderJourneyRun,
    *,
    completed_scene_count: int = 0,
    offline_replay_available: bool = False,
) -> tuple[bool, bool, str | None]:
    """Return (recovery_safe, blind_resume_blocked, block_reason).

    block_reason: contract_outdated | planner_outdated | offline_replay_required | None
    """
    run_planner = getattr(journey_run, "planner_version", None) or "1.0"
    run_contract = journey_run.scene_contract_version or "1.0"
    truncated = journey_run.root_error_code in {
        "OUTPUT_TRUNCATED",
        "JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED",
    }
    old_contract_failure = (
        run_contract.startswith("1.0")
        or (
            run_contract.startswith("1.1")
            and journey_run.root_error_code
            in {"JOURNEY_QUESTION_CHAIN_INVALID", "STRUCTURAL_VALIDATION_FAILED"}
        )
    )
    if journey_run.status not in {"failed", "scene_profiles_partial"}:
        return False, False, None

    # Offline replay already restored profiles — remaining work uses current v1.2 on resume.
    if (
        journey_run.status == "scene_profiles_partial"
        and completed_scene_count > 0
        and not offline_replay_available
    ):
        return True, False, None

    # Current server is v1.2 / planner 1.1: allow resume after semantics upgrade path.
    if (
        old_contract_failure
        and not offline_replay_available
        and SCENE_CONTRACT_VERSION >= "1.2"
        and PLANNER_VERSION >= "1.1"
        and (journey_run.retryable or journey_run.status == "scene_profiles_partial")
    ):
        return True, False, None

    if old_contract_failure and offline_replay_available:
        return False, True, "offline_replay_required"
    if old_contract_failure and SCENE_CONTRACT_VERSION < "1.2":
        return False, True, "contract_outdated"

    if journey_run.root_error_code == "JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED":
        recovery_safe = PLANNER_VERSION != run_planner or (
            journey_run.scene_contract_version != SCENE_CONTRACT_VERSION
        )
        return recovery_safe, not recovery_safe, None if recovery_safe else "planner_outdated"
    if truncated and PLANNER_VERSION == "1.0":
        return False, True, "planner_outdated"
    if truncated and run_planner == "1.0" and PLANNER_VERSION >= "1.1":
        return True, False, None
    return (
        bool(journey_run.retryable) or journey_run.status == "scene_profiles_partial",
        False,
        None,
    )

def reader_journey_progress(session: Session, journey_run: ReaderJourneyRun) -> ReaderJourneyProgress:
    from app.services.scene_boundary_manual_review import load_journey_bound_scenes

    try:
        _revision, scenes = load_journey_bound_scenes(session, journey_run)
    except Exception:
        _revision, scenes = load_revision_scenes(session, journey_run.analysis_run_id)
    completed: list[int] = []
    remaining: list[int] = []
    for scene in scenes:
        if is_scene_profile_complete(session, journey_run.id, scene.id):
            completed.append(scene.id)
        else:
            remaining.append(scene.id)
    phase_count = session.scalar(
        select(func.count())
        .select_from(ReaderJourneyPhase)
        .where(ReaderJourneyPhase.reader_journey_run_id == journey_run.id)
    )
    summary = session.scalar(
        select(ChapterReaderJourneySummary).where(
            ChapterReaderJourneySummary.reader_journey_run_id == journey_run.id
        )
    )
    usage = journey_invocation_usage(session, journey_run.analysis_run_id)
    from app.services.reader_journey_offline_replay import find_replayable_journey_invocations

    replay_candidates = []
    if journey_run.status in {"failed", "scene_profiles_partial"}:
        replay_candidates = find_replayable_journey_invocations(session, journey_run)
    offline_replay_available = len(replay_candidates) > 0
    replayable_scene_ids: set[int] = set()
    replayable_invocation_ids: list[int] = []
    for candidate in replay_candidates:
        replayable_invocation_ids.append(candidate.invocation_id)
        replayable_scene_ids.update(candidate.scene_ids)

    recovery_safe, blind_resume_blocked, resume_block_reason = recovery_flags(
        journey_run,
        completed_scene_count=len(completed),
        offline_replay_available=offline_replay_available,
    )

    user_message = user_error_for_code(journey_run.root_error_code)
    run_contract = journey_run.scene_contract_version or "1.0"
    if offline_replay_available and (
        run_contract.startswith("1.1")
        or journey_run.root_error_code
        in {"JOURNEY_QUESTION_CHAIN_INVALID", "STRUCTURAL_VALIDATION_FAILED"}
    ):
        user_message = OLD_CONTRACT_USER_MESSAGE
    elif run_contract.startswith("1.1") and journey_run.root_error_code == "JOURNEY_QUESTION_CHAIN_INVALID":
        user_message = OLD_CONTRACT_USER_MESSAGE

    resume_preflight = None
    if journey_run.status in {"failed", "scene_profiles_partial"} and recovery_safe:
        from app.services.staged_budget import (
            estimate_reader_journey_chapter_synthesis,
            estimate_reader_journey_scene_profiles,
            estimate_to_dict,
        )
        from app.services.reader_journey_batch_planner import (
            format_batch_plan_report,
            plan_scene_batches,
        )

        paragraphs = []
        if scenes:
            from app.db.models import Paragraph

            paragraphs = list(
                session.scalars(
                    select(Paragraph)
                    .where(Paragraph.chapter_id == journey_run.chapter_id)
                    .order_by(Paragraph.paragraph_index)
                )
            )
        pending = [scene for scene in scenes if scene.id in remaining]
        stage1 = estimate_reader_journey_scene_profiles(
            scenes,
            paragraphs,
            remaining_scene_ids=set(remaining),
        )
        stage2 = estimate_reader_journey_chapter_synthesis(scenes)
        batches = plan_scene_batches(pending, paragraphs=paragraphs)
        resume_preflight = {
            "remaining_scenes": len(remaining),
            "scene_batch_count": len(batches),
            "batch_plan": format_batch_plan_report(batches),
            "expected_requests": stage1.expected_request_count + stage2.expected_request_count,
            "worst_case_requests": stage1.worst_case_request_count + stage2.worst_case_request_count,
            "estimated_tokens": stage1.estimated_total_tokens + stage2.estimated_total_tokens,
            "worst_case_tokens": stage1.worst_case_total_tokens + stage2.worst_case_total_tokens,
            "estimated_cost": round(stage1.estimated_cost + stage2.estimated_cost, 6),
            "worst_case_cost": round(stage1.worst_case_cost + stage2.worst_case_cost, 6),
            "planner_version": PLANNER_VERSION,
            "scene_prompt_version": SCENE_PROMPT_VERSION,
            "scene_contract_version": SCENE_CONTRACT_VERSION,
            "stage1_scene_profiles": estimate_to_dict(stage1),
            "stage2_chapter_synthesis": estimate_to_dict(stage2),
            "currency": stage1.currency,
        }
    return ReaderJourneyProgress(
        journey_run=journey_run,
        total_scene_count=len(scenes),
        completed_scene_ids=completed,
        remaining_scene_ids=remaining,
        completed_scene_count=len(completed),
        remaining_scene_count=len(remaining),
        phase_count=int(phase_count or 0),
        has_chapter_summary=summary is not None,
        request_count=int(usage["request_count"]),
        total_tokens=int(usage["total_tokens"]),
        estimated_cost=float(usage["estimated_cost"]),
        currency=str(usage["currency"]),
        reservation_released=not has_active_reservation(session, journey_run.analysis_run_id),
        recovery_safe=recovery_safe,
        blind_resume_blocked=blind_resume_blocked,
        resume_block_reason=resume_block_reason,
        resume_preflight=resume_preflight,
        user_error_message=user_message,
        offline_replay_available=offline_replay_available,
        offline_replayable_scene_count=len(replayable_scene_ids),
        offline_replayable_invocation_ids=replayable_invocation_ids,
        current_contract_version=SCENE_CONTRACT_VERSION,
        recoverable_contract_version=SCENE_CONTRACT_VERSION if offline_replay_available else None,
    )


def sync_journey_run_counts(session: Session, journey_run: ReaderJourneyRun) -> ReaderJourneyProgress:
    progress = reader_journey_progress(session, journey_run)
    journey_run.total_scene_count = progress.total_scene_count
    journey_run.completed_scene_count = progress.completed_scene_count
    journey_run.remaining_scene_count = progress.remaining_scene_count
    journey_run.completed_scene_ids_json = json.dumps(progress.completed_scene_ids)
    journey_run.remaining_scene_ids_json = json.dumps(progress.remaining_scene_ids)
    return progress


def require_completed_scene_analysis(session: Session, run: AnalysisRun, scenes: list[Scene]) -> None:
    if run.status != "succeeded":
        raise ValueError("ANALYSIS_RUN_NOT_SUCCEEDED")
    for scene in scenes:
        artifact = scene_analysis_artifact(session, run.id, scene.id)
        if artifact is None:
            raise ValueError("SCENE_ANALYSIS_INCOMPLETE")


def find_recoverable_journey_run(
    session: Session,
    analysis_run_id: int,
    *,
    contract_major: str = "1",
) -> ReaderJourneyRun | None:
    rows = list(
        session.scalars(
            select(ReaderJourneyRun)
            .where(ReaderJourneyRun.analysis_run_id == analysis_run_id)
            .order_by(ReaderJourneyRun.id.desc())
        )
    )
    active_statuses = {
        "queued",
        "scene_profiles_running",
        "chapter_synthesis_running",
        "scene_profiles_partial",
    }
    for row in rows:
        major = (row.scene_contract_version or "1.0").split(".", 1)[0]
        if major != contract_major:
            continue
        if row.status in active_statuses:
            return row
        if row.status == "failed" and (
            row.retryable or recovery_flags(row)[0] or row.root_error_code == "OUTPUT_TRUNCATED"
        ):
            return row
    return None
