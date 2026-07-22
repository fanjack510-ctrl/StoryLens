import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AnalysisRun,
    BoundaryDetectionBatchCheckpoint,
    BoundaryReviewDecision,
    BoundaryReviewSession,
    BoundaryRevision,
    Chapter,
    ModelInvocation,
    Paragraph,
    Scene,
    AnalysisArtifact,
    AnalysisEvidence,
)
from app.model_gateway.gateway import ModelGateway
from app.schemas.scene import CompactTransitionCandidateDecision, SceneAnalysisResult
from app.services.compact_transition_adapter_v34 import deterministic_reason
from app.services.prompt_service import load_prompt
from app.services.structured_output import generate_validated
from app.services.scene_pipeline import (
    apply_scene_analysis_normalization,
    evidence_fields,
    scene_ranges,
    validate_scene_analysis,
)


def _validate_and_normalize_scene(
    value: SceneAnalysisResult,
    scene_key: str,
    allowed_ids: set[str],
) -> None:
    """Normalize evidence IDs in-place, then apply strict scene-analysis contract."""
    apply_scene_analysis_normalization(value, allowed_ids)
    validate_scene_analysis(value, scene_key, allowed_ids, True)


class BoundaryReviewIncomplete(ValueError):
    """Pending model candidates block confirmation."""

    def __init__(self, pending_transition_ids: list[str]):
        self.pending_transition_ids = list(pending_transition_ids)
        self.pending_count = len(self.pending_transition_ids)
        super().__init__(
            f"还有{self.pending_count}个候选边界尚未处理，请先完成审阅。"
        )

    def as_error_detail(self) -> dict[str, object]:
        return {
            "error_code": "BOUNDARY_REVIEW_INCOMPLETE",
            "message": str(self),
            "pending_count": self.pending_count,
            "pending_transition_ids": self.pending_transition_ids,
            "details": {
                "pending_count": self.pending_count,
                "pending_transition_ids": self.pending_transition_ids,
            },
            "user_action_hint": "请先处理所有待审候选。",
            "retryable": False,
        }


def _paragraphs(session: Session, chapter_id: int) -> list[Paragraph]:
    return list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter_id)
            .order_by(Paragraph.paragraph_index)
        )
    )


def _priority(decision: CompactTransitionCandidateDecision, adjudication: dict | None) -> str:
    if (
        decision.goal_relation in {"completed_then_new", "replaced", "interrupted"}
        or decision.confidence < 0.70
        or (
            adjudication is not None
            and bool(adjudication.get("accept")) != decision.boundary_candidate
        )
        or (adjudication or {}).get("scope_relation") == "local_subgoal_change"
    ):
        return "high"
    if decision.confidence <= 0.85 or decision.trigger_type in {"time", "location", "viewpoint"}:
        return "medium"
    return "low"


def create_review_session(session: Session, run: AnalysisRun) -> BoundaryReviewSession:
    existing = session.scalar(
        select(BoundaryReviewSession).where(BoundaryReviewSession.analysis_run_id == run.id)
    )
    if existing:
        return existing
    chapter = session.get(Chapter, int(run.subject_id))
    if chapter is None or chapter.section_type == "front_matter":
        raise ValueError("review requires a formal chapter")
    paragraphs = _paragraphs(session, chapter.id)
    position = {item.id: index for index, item in enumerate(paragraphs)}
    invocations = list(
        session.scalars(
            select(ModelInvocation)
            .where(ModelInvocation.run_id == run.id)
            .order_by(ModelInvocation.id)
        )
    )
    adjudications: dict[str, list[dict]] = {}
    for invocation in invocations:
        if invocation.invocation_kind != "boundary_candidate_adjudication":
            continue
        try:
            payload = json.loads(invocation.parsed_response_json or "{}")
        except json.JSONDecodeError:
            continue
        for item in payload.get("verdicts", []):
            adjudications.setdefault(str(item.get("transition_id")), []).append(item)
    review = BoundaryReviewSession(
        book_id=chapter.book_id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        prompt_version=run.prompt_version,
        provider=run.provider,
        model=run.model,
        status="pending",
    )
    session.add(review)
    session.flush()
    checkpoints = list(
        session.scalars(
            select(BoundaryDetectionBatchCheckpoint)
            .where(
                BoundaryDetectionBatchCheckpoint.run_id == run.id,
                BoundaryDetectionBatchCheckpoint.status.in_(
                    ["completed", "conflicted_completed"]
                ),
            )
            .order_by(BoundaryDetectionBatchCheckpoint.batch_index)
        )
    )
    seen_left: set[str] = set()
    seen_transition_ids: set[str] = set()
    ordinal = 1
    if checkpoints:
        for checkpoint in checkpoints:
            transition_map = json.loads(checkpoint.transition_map_json or "{}")
            issues = {
                item["transition_id"]: item
                for item in json.loads(checkpoint.issues_json or "[]")
            }
            payloads = (
                json.loads(checkpoint.valid_decisions_json or "[]")
                + json.loads(checkpoint.conflicted_decisions_json or "[]")
            )
            expected = json.loads(checkpoint.owned_transition_ids_json or "[]")
            by_id = {item["transition_id"]: item for item in payloads}
            for source_transition_id in expected:
                item = by_id.get(source_transition_id)
                if item is None:
                    continue
                parsed = CompactTransitionCandidateDecision.model_validate(item)
                issue = issues.get(source_transition_id)
                if not parsed.boundary_candidate and issue is None:
                    continue
                mapping = transition_map.get(source_transition_id) or {}
                left_id = mapping.get("left_paragraph_id")
                right_id = mapping.get("right_paragraph_id")
                if (
                    not left_id
                    or not right_id
                    or left_id in seen_left
                    or left_id not in position
                    or position[left_id] >= len(paragraphs) - 1
                ):
                    continue
                seen_left.add(left_id)
                transition_id = source_transition_id
                if transition_id in seen_transition_ids:
                    transition_id = f"W{checkpoint.window_index:03d}-{source_transition_id}"
                seen_transition_ids.add(transition_id)
                adjudication_list = adjudications.get(source_transition_id, [])
                adjudication = (
                    adjudication_list.pop(0)
                    if adjudication_list and issue is None
                    else None
                )
                session.add(
                    BoundaryReviewDecision(
                        review_session_id=review.id,
                        transition_id=transition_id,
                        left_paragraph_id=left_id,
                        right_paragraph_id=right_id,
                        model_candidate=True,
                        model_boundary_candidate=parsed.boundary_candidate,
                        model_confidence=parsed.confidence,
                        model_reason_code=deterministic_reason(parsed),
                        deterministic_reason=deterministic_reason(parsed),
                        deterministic_legal=deterministic_reason(parsed) is not None,
                        first_pass_json=parsed.model_dump_json(),
                        adjudication_result=(
                            json.dumps(adjudication, ensure_ascii=False)
                            if adjudication
                            else None
                        ),
                        review_priority=(
                            str(issue["review_priority"])
                            if issue
                            else _priority(parsed, adjudication)
                        ),
                        semantic_conflict=issue is not None,
                        conflict_code=(
                            str(issue["conflict_code"]) if issue else None
                        ),
                        enum_snapshot_json=json.dumps(
                            parsed.model_dump(mode="json"), ensure_ascii=False
                        ),
                        source_batch_index=checkpoint.batch_index,
                    )
                )
                ordinal += 1
    else:
        for invocation in invocations:
            if invocation.invocation_kind != "boundary_candidate_detection":
                continue
            try:
                payload = json.loads(invocation.parsed_response_json or "{}")
                mapped = json.loads(invocation.mapped_after_paragraph_ids_json or "[]")
            except json.JSONDecodeError:
                continue
            candidates = [
                item
                for item in payload.get("decisions", [])
                if item.get("boundary_candidate")
            ]
            for item, left_id in zip(candidates, mapped, strict=False):
                if (
                    left_id in seen_left
                    or left_id not in position
                    or position[left_id] >= len(paragraphs) - 1
                ):
                    continue
                seen_left.add(left_id)
                parsed = CompactTransitionCandidateDecision.model_validate(item)
                adjudication_list = adjudications.get(parsed.transition_id, [])
                adjudication = adjudication_list.pop(0) if adjudication_list else None
                session.add(
                    BoundaryReviewDecision(
                        review_session_id=review.id,
                        transition_id=f"T{ordinal:04d}",
                        left_paragraph_id=left_id,
                        right_paragraph_id=paragraphs[position[left_id] + 1].id,
                        model_candidate=True,
                        model_boundary_candidate=parsed.boundary_candidate,
                        model_confidence=parsed.confidence,
                        model_reason_code=deterministic_reason(parsed),
                        deterministic_reason=deterministic_reason(parsed),
                        deterministic_legal=deterministic_reason(parsed) is not None,
                        first_pass_json=parsed.model_dump_json(),
                        adjudication_result=(
                            json.dumps(adjudication, ensure_ascii=False)
                            if adjudication
                            else None
                        ),
                        review_priority=_priority(parsed, adjudication),
                        enum_snapshot_json=json.dumps(
                            parsed.model_dump(mode="json"), ensure_ascii=False
                        ),
                    )
                )
                ordinal += 1
    review.candidate_count = ordinal - 1
    run.status = "awaiting_boundary_review"
    session.commit()
    session.refresh(review)
    return review


def update_counts(session: Session, review: BoundaryReviewSession) -> None:
    rows = list(
        session.scalars(
            select(BoundaryReviewDecision).where(
                BoundaryReviewDecision.review_session_id == review.id
            )
        )
    )
    review.accepted_count = sum(item.user_decision == "accept" for item in rows)
    review.rejected_count = sum(item.user_decision == "reject" for item in rows)
    review.manually_added_count = sum(item.user_decision == "manually_added" for item in rows)


def preview_ranges(session: Session, review: BoundaryReviewSession):
    from app.services.scene_fragment_consolidation import (
        BoundaryMeta,
        consolidate_boundary_ids,
    )

    paragraphs = _paragraphs(session, review.chapter_id)
    decisions = list(
        session.scalars(
            select(BoundaryReviewDecision).where(
                BoundaryReviewDecision.review_session_id == review.id,
                BoundaryReviewDecision.final_boundary.is_(True),
            )
        )
    )
    positions = {item.id: item.paragraph_index for item in paragraphs}
    ids = sorted({item.left_paragraph_id for item in decisions}, key=positions.get)
    boundary_meta = {
        item.left_paragraph_id: BoundaryMeta(
            reason_codes=frozenset(
                [item.model_reason_code] if item.model_reason_code else []
            ),
            concise_reason=(
                item.deterministic_reason
                or item.manual_reason_type
                or item.user_reason
                or ""
            ),
        )
        for item in decisions
    }
    consolidated = consolidate_boundary_ids(paragraphs, ids, boundary_meta)
    return (
        paragraphs,
        consolidated,
        scene_ranges(
            paragraphs,
            consolidated,
            consolidate_short_fragments=False,
            boundary_meta=boundary_meta,
        ),
    )


def confirm_review(
    session: Session, review: BoundaryReviewSession, confirmed_by: str
) -> tuple[BoundaryRevision, list[Scene]]:
    if review.status in {"confirmed", "cancelled", "superseded"}:
        raise ValueError("review is not confirmable")
    decisions = list(
        session.scalars(
            select(BoundaryReviewDecision).where(
                BoundaryReviewDecision.review_session_id == review.id
            )
        )
    )
    if any(item.model_candidate and item.user_decision == "pending" for item in decisions):
        pending_ids = [
            item.transition_id
            for item in decisions
            if item.model_candidate and item.user_decision == "pending"
        ]
        raise BoundaryReviewIncomplete(pending_ids)
    for item in decisions:
        item.final_boundary = item.user_decision in {"accept", "manually_added"}
    session.flush()
    return _persist_confirmed_revision(session, review, confirmed_by)


def confirm_review_from_final_proposal(
    session: Session,
    review: BoundaryReviewSession,
    *,
    confirmed_by: str,
    proposal_fingerprint: str,
) -> tuple[BoundaryRevision, list[Scene], bool]:
    """Confirm using auto-built proposal. Returns (revision, scenes, idempotent_replay)."""
    from app.services.final_boundary_proposal import (
        apply_final_proposal_decisions,
        build_final_boundary_proposal,
    )

    if review.status == "confirmed":
        existing = session.scalar(
            select(BoundaryRevision)
            .where(BoundaryRevision.review_session_id == review.id)
            .order_by(desc(BoundaryRevision.id))
        )
        if existing is None:
            raise ValueError("review is confirmed without revision")
        run = session.get(AnalysisRun, review.analysis_run_id)
        run_marker: dict = {}
        if run is not None:
            try:
                run_marker = json.loads(run.raw_output or "{}")
                if not isinstance(run_marker, dict):
                    run_marker = {}
            except json.JSONDecodeError:
                run_marker = {}
        prior_fp = run_marker.get("final_proposal_fingerprint")
        if prior_fp == proposal_fingerprint:
            scenes = list(
                session.scalars(
                    select(Scene)
                    .where(Scene.boundary_revision_id == existing.id)
                    .order_by(Scene.ordinal)
                )
            )
            return existing, scenes, True
        raise ValueError("review is not confirmable")

    if review.status in {"cancelled", "superseded"}:
        raise ValueError("review is not confirmable")

    proposal = build_final_boundary_proposal(session, review)
    if proposal.validation_status != "valid":
        raise ValueError(proposal.unresolved_reason or "proposal unresolved")
    if proposal.proposal_fingerprint != proposal_fingerprint:
        raise ValueError("proposal fingerprint mismatch")

    apply_final_proposal_decisions(session, review, proposal)
    revision, scenes = _persist_confirmed_revision(session, review, confirmed_by)
    run = session.get(AnalysisRun, review.analysis_run_id)
    if run is not None:
        try:
            payload = json.loads(run.raw_output or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except json.JSONDecodeError:
            payload = {}
        payload["kind"] = payload.get("kind") or "chapter_pipeline"
        payload["final_proposal_fingerprint"] = proposal_fingerprint
        payload["boundary_review_mode"] = "confirm_only"
        run.raw_output = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        session.commit()
    return revision, scenes, False


def _persist_confirmed_revision(
    session: Session, review: BoundaryReviewSession, confirmed_by: str
) -> tuple[BoundaryRevision, list[Scene]]:
    paragraphs, boundary_ids, ranges = preview_ranges(session, review)
    revision_number = (
        session.scalar(
            select(func.max(BoundaryRevision.revision_number)).where(
                BoundaryRevision.review_session_id == review.id
            )
        )
        or 0
    ) + 1
    decisions = list(
        session.scalars(
            select(BoundaryReviewDecision).where(
                BoundaryReviewDecision.review_session_id == review.id
            )
        )
    )
    sources = {
        item.left_paragraph_id: (
            "user_added"
            if item.user_decision == "manually_added"
            else (
                "user_accepted_model_conflict"
                if item.semantic_conflict
                else "model_accepted"
            )
        )
        for item in decisions
        if item.final_boundary
    }
    revision = BoundaryRevision(
        review_session_id=review.id,
        chapter_id=review.chapter_id,
        analysis_run_id=review.analysis_run_id,
        revision_number=revision_number,
        final_boundaries_json=json.dumps(
            [
                {"after_paragraph_id": item, "source": sources.get(item, "model_accepted")}
                for item in boundary_ids
            ],
            ensure_ascii=False,
        ),
        confirmed_by=confirmed_by,
        coverage_rate=1.0,
    )
    session.add(revision)
    session.flush()
    chapter = session.get(Chapter, review.chapter_id)
    created = []
    for ordinal, (start, end) in enumerate(ranges, 1):
        included = [
            item
            for item in paragraphs
            if start.paragraph_index <= item.paragraph_index <= end.paragraph_index
        ]
        source = sources.get(end.id)
        scene = Scene(
            scene_key=f"B{chapter.book_id:04d}-C{chapter.chapter_index:04d}-R{revision.id:04d}-S{ordinal:04d}",
            book_id=chapter.book_id,
            chapter_id=chapter.id,
            ordinal=ordinal,
            start_paragraph_id=start.id,
            end_paragraph_id=end.id,
            content_hash=hashlib.sha256(
                "\n".join(item.normalized_text for item in included).encode()
            ).hexdigest(),
            created_by_run_id=review.analysis_run_id,
            boundary_detected=source is not None,
            boundary_confidence=1.0 if source else 0.0,
            boundary_reason_json="[]",
            boundary_revision_id=revision.id,
            boundary_source=source,
        )
        session.add(scene)
        created.append(scene)
    review.status = "confirmed"
    review.confirmed_by = confirmed_by
    review.completed_at = datetime.now(timezone.utc)
    update_counts(session, review)
    run = session.get(AnalysisRun, review.analysis_run_id)
    run.status = "boundary_confirmed"
    session.commit()
    return revision, created


async def analyze_confirmed_review(
    session_factory: sessionmaker[Session], gateway: ModelGateway, review_id: int,
) -> None:
    import asyncio

    from app.core.config import get_settings
    from app.services.budget_reservation import release_run_reservation
    from app.services.credentials.service import get_credential_store
    from app.services.provider_runtime_service import ProviderRuntimeService
    from app.services.scene_analysis_progress import (
        clear_scene_analysis_error_fields,
        is_scene_analysis_complete,
        persist_scene_analysis_failure,
    )
    from app.services.scene_analysis_provider_recovery import (
        STATUS_AWAITING_PROVIDER_RECOVERY,
        begin_provider_recovery_pause,
        check_recovery_limits,
        finalize_provider_recovery_exhausted,
        is_provider_transport_recoverable,
        load_recovery_state,
        policy_from_settings,
        resume_from_provider_recovery,
    )
    from app.services.staged_budget import STAGE_ANALYSIS
    from app.model_gateway.base import ProviderRequestError

    with session_factory() as session:
        review = session.get(BoundaryReviewSession, review_id)
        if review is None or review.status != "confirmed":
            raise ValueError("BOUNDARY_REVIEW_REQUIRED")
        run = session.get(AnalysisRun, review.analysis_run_id)
        if run is None or (run.sends_content_to_cloud and not run.cloud_consent):
            raise ValueError("CLOUD_CONSENT_REQUIRED")
        if run.status == "succeeded":
            from app.services.chapter_analysis_completion import (
                continue_chapter_after_scenes,
                is_chapter_analysis_complete,
                is_scene_pipeline_complete,
            )

            if is_chapter_analysis_complete(session, run):
                return
            if is_scene_pipeline_complete(session, run):
                session.commit()
                await continue_chapter_after_scenes(session_factory, gateway, run.id)
                return
            # Succeeded marker without full scene artifacts — continue scene loop below.
        revision = session.scalar(
            select(BoundaryRevision)
            .where(BoundaryRevision.review_session_id == review.id)
            .order_by(BoundaryRevision.id.desc())
        )
        scenes = list(
            session.scalars(
                select(Scene)
                .where(Scene.boundary_revision_id == revision.id)
                .order_by(Scene.ordinal)
            )
        )
        paragraphs = _paragraphs(session, review.chapter_id)
        by_id = {item.id: item for item in paragraphs}
        position = {item.id: index for index, item in enumerate(paragraphs)}
        prompt = load_prompt("scene_analysis", "v3.2")
        try:
            store = get_credential_store()
        except Exception:
            store = None
        resolved = ProviderRuntimeService.resolve_for_run(
            gateway,
            session,
            run,
            store,
            task_type="scene_analysis",
        )
        if not resolved.eligibility.get("eligible"):
            blockers = resolved.eligibility.get("blockers") or []
            code = (
                "PROVIDER_DISABLED"
                if "provider_disabled" in blockers
                else "SCENE_ANALYSIS_START_FAILED"
            )
            message = (
                "Provider已停用，拒绝发送请求"
                if code == "PROVIDER_DISABLED"
                else f"Scene Analysis资格检查失败: {','.join(map(str, blockers))}"
            )
            exc = ProviderRequestError(
                message,
                http_request_sent=False,
                error_code=code,
                exception_type="ProviderEligibilityError",
                provider=run.provider,
                model=run.model,
                phase="pre_send",
                retryable=False,
            )
            persist_scene_analysis_failure(session, run, exc, failed_scene=None)
            session.commit()
            release_run_reservation(session, run.id, stage=STAGE_ANALYSIS)
            raise exc

        policy = policy_from_settings(get_settings())
        prior_state = load_recovery_state(run)
        recovery_cycles = int(prior_state.get("recovery_cycles") or 0)
        recovery_started_at: datetime | None = None
        if prior_state.get("recovery_started_at"):
            try:
                recovery_started_at = datetime.fromisoformat(
                    str(prior_state["recovery_started_at"])
                )
            except ValueError:
                recovery_started_at = None

        if run.status == STATUS_AWAITING_PROVIDER_RECOVERY:
            resume_from_provider_recovery(run)
        else:
            clear_scene_analysis_error_fields(run)
            run.status = "scene_analysis_running"
        session.commit()
        current_scene: Scene | None = None
        try:
            while True:
                # Re-load after rollback / recovery so ORM state stays usable.
                scenes = list(
                    session.scalars(
                        select(Scene)
                        .where(Scene.boundary_revision_id == revision.id)
                        .order_by(Scene.ordinal)
                    )
                )
                paragraphs = _paragraphs(session, review.chapter_id)
                by_id = {item.id: item for item in paragraphs}
                position = {item.id: index for index, item in enumerate(paragraphs)}
                try:
                    for scene in scenes:
                        if is_scene_analysis_complete(session, run.id, scene):
                            continue
                        current_scene = scene
                        included = paragraphs[
                            position[scene.start_paragraph_id] : position[scene.end_paragraph_id] + 1
                        ]
                        snapshot = {
                            "scene_id": scene.scene_key,
                            "paragraphs": [
                                {"id": item.id, "text": item.normalized_text}
                                for item in included
                            ],
                        }
                        result = await generate_validated(
                            session=session,
                            gateway=gateway,
                            run_id=run.id,
                            provider_name=run.provider,
                            task_type="scene_analysis",
                            prompt=prompt,
                            schema=SceneAnalysisResult,
                            input_snapshot=snapshot,
                            user_content=prompt.user_template.format(
                                input_json=json.dumps(snapshot, ensure_ascii=False)
                            ),
                            business_validator=lambda value, scene=scene, included=included: (
                                _validate_and_normalize_scene(
                                    value, scene.scene_key, {item.id for item in included}
                                )
                            ),
                        )
                        artifact = AnalysisArtifact(
                            run_id=run.id,
                            artifact_type="scene_analysis",
                            subject_type="scene",
                            subject_id=str(scene.id),
                            schema_version="v1",
                            prompt_version="v3.2",
                            payload_json=result.model_dump_json(),
                            confidence=result.confidence,
                            validation_status="valid",
                        )
                        session.add(artifact)
                        session.flush()
                        for path, paragraph_id in evidence_fields(result):
                            paragraph = by_id[paragraph_id]
                            session.add(
                                AnalysisEvidence(
                                    artifact_id=artifact.id,
                                    field_path=path,
                                    paragraph_id=paragraph_id,
                                    paragraph_hash=hashlib.sha256(
                                        paragraph.raw_text.encode()
                                    ).hexdigest(),
                                )
                            )
                        # Per-scene commit boundary: never roll back completed scenes.
                        session.commit()
                    run = session.get(AnalysisRun, review.analysis_run_id)
                    recovery_state = load_recovery_state(run) if run is not None else {}
                    clear_scene_analysis_error_fields(run)
                    from app.services.chapter_analysis_completion import (
                        continue_chapter_after_scenes,
                        mark_scenes_complete_awaiting_journey,
                    )

                    mark_scenes_complete_awaiting_journey(session, run)
                    if recovery_state.get("recovery_audits"):
                        # Preserve recovery audits alongside pipeline marker.
                        from app.services.chapter_analysis_completion import _store_marker

                        _store_marker(
                            run,
                            recovery_cycles=recovery_state.get("recovery_cycles"),
                            recovery_started_at=recovery_state.get("recovery_started_at"),
                            recovery_audits=recovery_state.get("recovery_audits"),
                        )
                    session.commit()
                    await continue_chapter_after_scenes(
                        session_factory, gateway, review.analysis_run_id
                    )
                    return
                except Exception as exc:
                    session.rollback()
                    run = session.get(AnalysisRun, review.analysis_run_id)
                    if run is None:
                        raise
                    if not is_provider_transport_recoverable(exc):
                        persist_scene_analysis_failure(
                            session, run, exc, failed_scene=current_scene
                        )
                        session.commit()
                        raise

                    if recovery_started_at is None:
                        recovery_started_at = datetime.now(timezone.utc)
                    next_cycle = recovery_cycles + 1
                    stop_reason = check_recovery_limits(
                        session,
                        run,
                        policy,
                        next_cycle=next_cycle,
                        recovery_started_at=recovery_started_at,
                    )
                    if stop_reason is not None:
                        finalize_provider_recovery_exhausted(
                            session,
                            run,
                            exc,
                            failed_scene=current_scene,
                            stop_reason=stop_reason,
                            recovery_cycle=recovery_cycles,
                            policy=policy,
                        )
                        session.commit()
                        raise

                    recovery_cycles = next_cycle
                    begin_provider_recovery_pause(
                        session,
                        run,
                        exc,
                        failed_scene=current_scene,
                        recovery_cycle=recovery_cycles,
                        policy=policy,
                        recovery_started_at=recovery_started_at,
                    )
                    session.commit()

                    # Circuit breaker cooldown — then retry only pending Scenes.
                    if policy.circuit_cooldown_seconds > 0:
                        await asyncio.sleep(policy.circuit_cooldown_seconds)
                    run = session.get(AnalysisRun, review.analysis_run_id)
                    if run is None:
                        raise
                    resume_from_provider_recovery(run)
                    session.commit()
                    # Continue outer while: completed artifacts are skipped.
        finally:
            if run is not None:
                release_run_reservation(session, run.id, stage=STAGE_ANALYSIS)

