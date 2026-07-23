"""Mock Run recovery + checkpoint validation (Phase 2A Agent O).

Startup scans mark interrupted only — never silent auto-resume.
Resume requires explicit user/test call after prechecks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisArtifact, AnalysisRun, AnalysisRunStage, BookSnapshot
from app.narrative_core.enums import RunStatus, SnapshotStatus, StageStatus
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.create_run import (
    MOCK_RUN_METADATA_SCHEMA,
    MOCK_RUN_METADATA_VERSION,
)
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode
from app.narrative_core.run_shell_contract.mock_lab import MOCK_ENGINE_ID, MOCK_LAB_SOURCE
from app.narrative_core.run_shell_contract.recovery import (
    CHECKPOINT_SCHEMA,
    CHECKPOINT_VERSION,
    DEFAULT_RECOVERY_SCAN_POLICY,
    MockCheckpointRef,
    MockRecoveryDecision,
    MockResumePlan,
    RecoveryScanPolicy,
    decide_lab_disabled_recovery,
    engine_version_mismatch_decision,
)
from app.narrative_core.run_shell_contract.stage_lifecycle import ORDERED_MOCK_STAGE_KEYS
from app.narrative_core.services.mock_run_audit import MockRunAuditSink
from app.narrative_core.services.mock_run_idempotency import (
    MockRunServiceError,
    raise_mock_run_error,
)
from app.narrative_core.services.mock_whole_book_engine import MOCK_ENGINE_VERSION

MOCK_RUN_SIDECAR_SCHEMA = "mock_run_recovery_sidecar"
MOCK_RUN_SIDECAR_VERSION = "1.0.0"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_mock_lab_run(run: AnalysisRun) -> bool:
    if run.analysis_type and "whole_book" in str(run.analysis_type):
        return True
    if run.task_type in {"whole_book_mock", "mock_whole_book", "whole_book_native"}:
        return True
    if run.client_request_id and str(run.client_request_id).startswith("mock_lab:"):
        return True
    # Heuristic: staged whole-book runs with mock engine marker in prompt_version.
    if run.prompt_version and "mock" in str(run.prompt_version).lower():
        return True
    return False


def _ordered_stage_keys() -> tuple[str, ...]:
    return tuple(k.value for k in ORDERED_MOCK_STAGE_KEYS)


@dataclass(frozen=True, slots=True)
class CheckpointValidationResult:
    ok: bool
    ref: MockCheckpointRef | None
    error_code: MockRunErrorCode | None
    detail_code: str | None = None


class CheckpointValidator:
    """Validate mock whole-book stage checkpoints without reading novel body."""

    expected_schema = CHECKPOINT_SCHEMA
    expected_version = CHECKPOINT_VERSION

    def validate_payload(
        self,
        payload: Mapping[str, Any] | str | None,
        *,
        run_id: int,
        run_stage_id: int | None = None,
        stage_key: str | None = None,
        attempt: int | None = None,
        engine_id: str = MOCK_ENGINE_ID,
        engine_version: str = MOCK_ENGINE_VERSION,
        configuration_fingerprint: str | None = None,
        snapshot_id: int | None = None,
        require_resumable: bool = True,
    ) -> CheckpointValidationResult:
        data, parse_error = self._parse(payload)
        if parse_error is not None:
            return CheckpointValidationResult(
                ok=False,
                ref=None,
                error_code=MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID,
                detail_code=parse_error,
            )

        schema = str(data.get("schema") or data.get("checkpoint_schema") or "").strip()
        version = str(data.get("version") or data.get("checkpoint_version") or "").strip()
        if schema != self.expected_schema or version != self.expected_version:
            return CheckpointValidationResult(
                ok=False,
                ref=MockCheckpointRef(
                    schema=schema or "missing",
                    version=version or "missing",
                    stage_key=stage_key,
                    attempt=int(attempt or data.get("attempt") or 0),
                    compatible=False,
                ),
                error_code=MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID,
                detail_code="CHECKPOINT_SCHEMA_OR_VERSION_MISMATCH",
            )

        payload_run_id = data.get("run_id")
        if payload_run_id is not None and int(payload_run_id) != int(run_id):
            return CheckpointValidationResult(
                ok=False,
                ref=None,
                error_code=MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID,
                detail_code="CHECKPOINT_RUN_ID_MISMATCH",
            )

        payload_stage_id = data.get("run_stage_id")
        if (
            run_stage_id is not None
            and payload_stage_id is not None
            and int(payload_stage_id) != int(run_stage_id)
        ):
            return CheckpointValidationResult(
                ok=False,
                ref=None,
                error_code=MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID,
                detail_code="CHECKPOINT_RUN_STAGE_ID_MISMATCH",
            )

        payload_stage_key = data.get("stage_key")
        if stage_key is not None and payload_stage_key not in (None, stage_key):
            return CheckpointValidationResult(
                ok=False,
                ref=None,
                error_code=MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID,
                detail_code="CHECKPOINT_STAGE_KEY_MISMATCH",
            )

        payload_attempt = data.get("attempt")
        if attempt is not None and payload_attempt is not None and int(payload_attempt) != int(attempt):
            return CheckpointValidationResult(
                ok=False,
                ref=None,
                error_code=MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID,
                detail_code="CHECKPOINT_ATTEMPT_MISMATCH",
            )

        payload_engine_id = str(data.get("engine_id") or engine_id)
        payload_engine_version = str(data.get("engine_version") or "")
        if payload_engine_id != engine_id:
            return CheckpointValidationResult(
                ok=False,
                ref=None,
                error_code=MockRunErrorCode.MOCK_RUN_ENGINE_VERSION_MISMATCH,
                detail_code="CHECKPOINT_ENGINE_ID_MISMATCH",
            )
        if payload_engine_version and payload_engine_version != engine_version:
            return CheckpointValidationResult(
                ok=False,
                ref=None,
                error_code=MockRunErrorCode.MOCK_RUN_ENGINE_VERSION_MISMATCH,
                detail_code="CHECKPOINT_ENGINE_VERSION_MISMATCH",
            )

        payload_cfg = data.get("configuration_fingerprint")
        if (
            configuration_fingerprint is not None
            and payload_cfg is not None
            and str(payload_cfg) != str(configuration_fingerprint)
        ):
            return CheckpointValidationResult(
                ok=False,
                ref=None,
                error_code=MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID,
                detail_code="CHECKPOINT_CONFIGURATION_MISMATCH",
            )

        payload_snapshot = data.get("snapshot_id") or data.get("book_snapshot_id")
        if (
            snapshot_id is not None
            and payload_snapshot is not None
            and int(payload_snapshot) != int(snapshot_id)
        ):
            return CheckpointValidationResult(
                ok=False,
                ref=None,
                error_code=MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID,
                detail_code="CHECKPOINT_SNAPSHOT_MISMATCH",
            )

        integrity = data.get("integrity_hash")
        if integrity:
            expected = self.compute_integrity_hash(
                {k: v for k, v in data.items() if k != "integrity_hash"}
            )
            if str(integrity) != expected:
                return CheckpointValidationResult(
                    ok=False,
                    ref=None,
                    error_code=MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID,
                    detail_code="CHECKPOINT_INTEGRITY_HASH_MISMATCH",
                )

        resumable = data.get("resumable", True)
        if require_resumable and resumable is False:
            return CheckpointValidationResult(
                ok=False,
                ref=None,
                error_code=MockRunErrorCode.MOCK_RUN_NOT_RECOVERABLE,
                detail_code="CHECKPOINT_NOT_RESUMABLE",
            )

        # Never treat corrupted/invalid payloads as completed.
        if data.get("status") == "completed" and not data.get("completed_output_ref"):
            # Soft warning path: still compatible if schema ok, but mark detail.
            pass

        ref = MockCheckpointRef(
            schema=schema,
            version=version,
            stage_key=str(payload_stage_key or stage_key) if (payload_stage_key or stage_key) else None,
            attempt=int(payload_attempt if payload_attempt is not None else (attempt or 0)),
            compatible=True,
        )
        return CheckpointValidationResult(ok=True, ref=ref, error_code=None)

    @staticmethod
    def compute_integrity_hash(payload: Mapping[str, Any]) -> str:
        # Exclude body-like keys if present.
        forbidden = {
            "full_text",
            "novel_body",
            "prompt",
            "system_prompt",
            "evidence_full_text",
        }
        cleaned = {k: v for k, v in payload.items() if k not in forbidden}
        blob = json.dumps(cleaned, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @staticmethod
    def build_checkpoint(
        *,
        run_id: int,
        run_stage_id: int,
        stage_key: str,
        attempt: int,
        engine_id: str = MOCK_ENGINE_ID,
        engine_version: str = MOCK_ENGINE_VERSION,
        configuration_fingerprint: str,
        snapshot_id: int,
        resumable: bool = True,
        completed_output_ref: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": CHECKPOINT_SCHEMA,
            "version": CHECKPOINT_VERSION,
            "run_id": run_id,
            "run_stage_id": run_stage_id,
            "stage_key": stage_key,
            "attempt": attempt,
            "engine_id": engine_id,
            "engine_version": engine_version,
            "configuration_fingerprint": configuration_fingerprint,
            "snapshot_id": snapshot_id,
            "resumable": resumable,
            "completed_output_ref": completed_output_ref,
            "source": MOCK_LAB_SOURCE,
            "mock": True,
            "non_production": True,
        }
        if extra:
            for key, value in extra.items():
                if key in {
                    "full_text",
                    "novel_body",
                    "prompt",
                    "system_prompt",
                    "api_key",
                    "credential",
                }:
                    continue
                payload[key] = value
        payload["integrity_hash"] = CheckpointValidator.compute_integrity_hash(payload)
        return payload

    def _parse(
        self, payload: Mapping[str, Any] | str | None
    ) -> tuple[dict[str, Any], str | None]:
        if payload is None:
            return {}, "CHECKPOINT_MISSING"
        if isinstance(payload, str):
            raw = payload.strip()
            if not raw:
                return {}, "CHECKPOINT_EMPTY"
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {}, "CHECKPOINT_CORRUPTED_JSON"
            if not isinstance(parsed, dict):
                return {}, "CHECKPOINT_NOT_OBJECT"
            return parsed, None
        if isinstance(payload, Mapping):
            return dict(payload), None
        return {}, "CHECKPOINT_INVALID_TYPE"


class MockRunRecoveryService:
    """Recovery service implementing Phase 2A-P MockRunRecoveryService Protocol."""

    def __init__(
        self,
        session: Session,
        *,
        lab_enabled: bool = True,
        current_engine_id: str = MOCK_ENGINE_ID,
        current_engine_version: str = MOCK_ENGINE_VERSION,
        audit_sink: MockRunAuditSink | None = None,
        policy: RecoveryScanPolicy = DEFAULT_RECOVERY_SCAN_POLICY,
        validator: CheckpointValidator | None = None,
        explicit_resume_allowed: bool = False,
    ) -> None:
        self._session = session
        self._lab_enabled = lab_enabled
        self._engine_id = current_engine_id
        self._engine_version = current_engine_version
        self._audit = audit_sink or MockRunAuditSink(emit_logs=False)
        self._policy = policy
        self._validator = validator or CheckpointValidator()
        self._explicit_resume_allowed = explicit_resume_allowed
        self._resume_executed: set[int] = set()

    def allow_explicit_resume(self, enabled: bool = True) -> None:
        """Gate for user click / test call. Startup must leave this False."""
        self._explicit_resume_allowed = enabled

    def scan_recoverable_runs(self) -> tuple[int, ...]:
        """Find mock lab runs that look recoverable (running/interrupted/paused)."""
        runs = list(
            self._session.scalars(
                select(AnalysisRun).where(
                    AnalysisRun.status.in_(
                        [
                            RunStatus.RUNNING.value,
                            RunStatus.INTERRUPTED.value,
                            RunStatus.PAUSED.value,
                            "queued",
                        ]
                    )
                )
            )
        )
        recoverable: list[int] = []
        for run in runs:
            if not _is_mock_lab_run(run):
                continue
            stages = list(
                self._session.scalars(
                    select(AnalysisRunStage).where(AnalysisRunStage.run_id == run.id)
                )
            )
            if not stages:
                # Phase 1A compatibility: no stages — still report for interrupt marking.
                recoverable.append(int(run.id))
                continue
            if any(
                StageStatus(s.status)
                in {
                    StageStatus.RUNNING,
                    StageStatus.INTERRUPTED,
                    StageStatus.PAUSED,
                }
                for s in stages
            ) or run.status in {
                RunStatus.RUNNING.value,
                RunStatus.INTERRUPTED.value,
                RunStatus.PAUSED.value,
            }:
                recoverable.append(int(run.id))
        return tuple(sorted(set(recoverable)))

    def mark_process_interrupted(self, run_id: int) -> MockRecoveryDecision:
        run = self._require_run(run_id)
        if not _is_mock_lab_run(run):
            return MockRecoveryDecision(
                run_id=run_id,
                recoverable=False,
                reason_code=MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET,
                marked_interrupted=False,
                resume_plan=None,
                lab_enabled=self._lab_enabled,
            )

        previous = run.status
        stages = list(
            self._session.scalars(
                select(AnalysisRunStage).where(AnalysisRunStage.run_id == run_id)
            )
        )
        if not stages:
            # Phase 1A / no-stage compatibility: leave to legacy sidecar path semantics.
            # Soft-mark interrupted when still active, without inventing stages.
            if run.status in {
                RunStatus.RUNNING.value,
                "queued",
                "boundary_candidates_running",
                "scene_analysis_running",
            }:
                run.status = RunStatus.INTERRUPTED.value
                run.error_code = "PROCESS_INTERRUPTED"
                run.error_message = "应用重启时任务仍在运行"
                run.completed_at = None
                self._session.commit()
            self._audit.interrupted(run_id, previous_state=previous)
            return MockRecoveryDecision(
                run_id=run_id,
                recoverable=False,
                reason_code=None,
                marked_interrupted=True,
                resume_plan=None,
                lab_enabled=self._lab_enabled,
            )

        for stage in stages:
            if StageStatus(stage.status) == StageStatus.RUNNING:
                stage.status = StageStatus.INTERRUPTED.value
                stage.error_code = "PROCESS_INTERRUPTED"
                stage.error_message = "应用重启时阶段仍在运行"
                stage.completed_at = None
            # completed / pending / paused / failed unchanged

        if run.status not in {
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        }:
            run.status = RunStatus.INTERRUPTED.value
            run.error_code = "PROCESS_INTERRUPTED"
            run.error_message = "应用重启时任务仍在运行；阶段可 resume"
            run.completed_at = None

        self._session.commit()
        self._audit.interrupted(run_id, previous_state=previous)

        if not self._lab_enabled:
            return decide_lab_disabled_recovery(run_id)

        return MockRecoveryDecision(
            run_id=run_id,
            recoverable=True,
            reason_code=None,
            marked_interrupted=True,
            resume_plan=None,
            lab_enabled=self._lab_enabled,
        )

    def validate_checkpoint(self, run_id: int) -> MockCheckpointRef:
        run = self._require_run(run_id)
        stages = list(
            self._session.scalars(
                select(AnalysisRunStage)
                .where(AnalysisRunStage.run_id == run_id)
                .order_by(AnalysisRunStage.stage_order)
            )
        )
        if not stages:
            return MockCheckpointRef(
                schema=CHECKPOINT_SCHEMA,
                version=CHECKPOINT_VERSION,
                stage_key=None,
                attempt=0,
                compatible=True,
            )

        target = None
        for stage in stages:
            if StageStatus(stage.status) in {
                StageStatus.RUNNING,
                StageStatus.INTERRUPTED,
                StageStatus.PAUSED,
                StageStatus.FAILED,
            }:
                target = stage
                break
        if target is None:
            # All completed / pending — use last completed checkpoint if any.
            completed = [
                s for s in stages if StageStatus(s.status) == StageStatus.COMPLETED
            ]
            target = completed[-1] if completed else stages[0]

        result = self._validator.validate_payload(
            target.checkpoint_json,
            run_id=run_id,
            run_stage_id=target.id,
            stage_key=target.stage_key,
            attempt=target.attempt_count,
            engine_id=self._engine_id,
            engine_version=self._engine_version,
            configuration_fingerprint=run.configuration_fingerprint,
            snapshot_id=run.book_snapshot_id,
        )
        if not result.ok or result.ref is None:
            raise_mock_run_error(
                result.error_code or MockRunErrorCode.MOCK_RUN_CHECKPOINT_INVALID,
                detail_code=result.detail_code,
                run_id=run_id,
                stage_key=target.stage_key,
            )
        return result.ref

    def build_resume_plan(self, run_id: int) -> MockResumePlan:
        run = self._require_run(run_id)
        self._precheck_or_raise(run, require_lab=True, for_resume_plan=True)
        stages = list(
            self._session.scalars(
                select(AnalysisRunStage)
                .where(AnalysisRunStage.run_id == run_id)
                .order_by(AnalysisRunStage.stage_order)
            )
        )
        if not stages:
            plan = MockResumePlan(
                run_id=run_id,
                resume_from_stage_key=None,
                skip_completed_stages=(),
                reset_downstream_stage_keys=(),
            )
            self._audit.recovery_planned(run_id, actor="recovery", detail_code="NO_STAGES")
            return plan

        completed = [
            s.stage_key
            for s in stages
            if StageStatus(s.status) == StageStatus.COMPLETED
        ]
        resume_from = None
        for stage in stages:
            status = StageStatus(stage.status)
            if status in {
                StageStatus.INTERRUPTED,
                StageStatus.PAUSED,
                StageStatus.FAILED,
                StageStatus.RUNNING,
                StageStatus.PENDING,
            }:
                resume_from = stage.stage_key
                break

        ordered = _ordered_stage_keys()
        reset_downstream: tuple[str, ...] = ()
        if resume_from and resume_from in ordered:
            idx = ordered.index(resume_from)
            # Do not reset completed upstream; only unfinished downstream stay pending.
            reset_downstream = tuple(
                k
                for k in ordered[idx + 1 :]
                if k not in completed
            )

        # Validate checkpoint for resume_from stage when present.
        if resume_from:
            self.validate_checkpoint(run_id)

        plan = MockResumePlan(
            run_id=run_id,
            resume_from_stage_key=resume_from,
            skip_completed_stages=tuple(completed),
            reset_downstream_stage_keys=reset_downstream,
        )
        self._audit.recovery_planned(
            run_id,
            actor="recovery",
            detail_code=f"resume_from:{resume_from or 'none'}",
        )
        return plan

    def resume_recoverable_run(self, run_id: int) -> MockRecoveryDecision:
        """Explicit resume only. Does not auto-start executor / consume budget."""
        if not self._explicit_resume_allowed:
            return MockRecoveryDecision(
                run_id=run_id,
                recoverable=False,
                reason_code=MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                marked_interrupted=False,
                resume_plan=None,
                lab_enabled=self._lab_enabled,
            )
        if not self._lab_enabled:
            decision = decide_lab_disabled_recovery(run_id)
            self._audit.recovery_rejected(
                run_id, actor="recovery", detail_code=MockRunErrorCode.MOCK_LAB_DISABLED.value
            )
            return decision

        run = self._require_run(run_id)
        try:
            self._precheck_or_raise(run, require_lab=True, for_resume_plan=False)
            plan = self.build_resume_plan(run_id)
        except MockRunServiceError as exc:
            self._audit.recovery_rejected(
                run_id, actor="recovery", detail_code=exc.code.value
            )
            return MockRecoveryDecision(
                run_id=run_id,
                recoverable=False,
                reason_code=exc.code,
                marked_interrupted=run.status == RunStatus.INTERRUPTED.value,
                resume_plan=None,
                lab_enabled=self._lab_enabled,
            )

        # Mark plan accepted; do NOT silently continue execution here.
        previous = run.status
        if run.status in {
            RunStatus.INTERRUPTED.value,
            RunStatus.PAUSED.value,
            RunStatus.FAILED.value,
        }:
            # Transition to running only as "resume accepted"; executor start is caller's job.
            run.status = RunStatus.RUNNING.value
            run.error_code = None
            run.error_message = None
            run.completed_at = None
            if plan.resume_from_stage_key:
                for stage in self._session.scalars(
                    select(AnalysisRunStage).where(AnalysisRunStage.run_id == run_id)
                ):
                    if stage.stage_key == plan.resume_from_stage_key and StageStatus(
                        stage.status
                    ) in {
                        StageStatus.INTERRUPTED,
                        StageStatus.PAUSED,
                        StageStatus.FAILED,
                    }:
                        stage.status = StageStatus.RUNNING.value
                        stage.error_code = None
                        stage.error_message = None
                        stage.completed_at = None
            self._session.commit()

        self._resume_executed.add(run_id)
        self._audit.resumed(run_id, actor="user_or_test", previous_state=previous)
        return MockRecoveryDecision(
            run_id=run_id,
            recoverable=True,
            reason_code=None,
            marked_interrupted=False,
            resume_plan=plan,
            lab_enabled=True,
        )

    def reject_unrecoverable_run(
        self, run_id: int, reason: MockRunErrorCode
    ) -> MockRecoveryDecision:
        run = self._require_run(run_id)
        if run.status not in {
            RunStatus.COMPLETED.value,
            RunStatus.CANCELLED.value,
            RunStatus.FAILED.value,
        }:
            run.status = RunStatus.FAILED.value
            run.error_code = reason.value
            run.error_message = "Mock run marked unrecoverable"
            run.completed_at = _utc_now()
            self._session.commit()
        self._audit.recovery_rejected(run_id, actor="recovery", detail_code=reason.value)
        return MockRecoveryDecision(
            run_id=run_id,
            recoverable=False,
            reason_code=reason,
            marked_interrupted=False,
            resume_plan=None,
            lab_enabled=self._lab_enabled,
        )

    def was_silently_resumed(self, run_id: int) -> bool:
        """Startup path must never set this; only explicit resume may."""
        return run_id in self._resume_executed and self._explicit_resume_allowed

    def _require_run(self, run_id: int) -> AnalysisRun:
        run = self._session.get(AnalysisRun, run_id)
        if run is None:
            raise_mock_run_error(MockRunErrorCode.MOCK_RUN_NOT_FOUND, run_id=run_id)
        return run

    def _precheck_or_raise(
        self,
        run: AnalysisRun,
        *,
        require_lab: bool,
        for_resume_plan: bool,
    ) -> None:
        if not _is_mock_lab_run(run):
            raise_mock_run_error(
                MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET, run_id=run.id
            )
        if require_lab and not self._lab_enabled:
            raise_mock_run_error(MockRunErrorCode.MOCK_LAB_DISABLED, run_id=run.id)

        if run.book_snapshot_id is None:
            raise_mock_run_error(
                MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID,
                run_id=run.id,
                detail_code="SNAPSHOT_MISSING",
            )
        snapshot = self._session.get(BookSnapshot, run.book_snapshot_id)
        if snapshot is None:
            raise_mock_run_error(
                MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID,
                run_id=run.id,
                detail_code="SNAPSHOT_MISSING",
            )
        if snapshot.snapshot_status != SnapshotStatus.COMPLETED.value:
            raise_mock_run_error(
                MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID,
                run_id=run.id,
                detail_code="SNAPSHOT_NOT_COMPLETED",
            )

        # Engine id/version markers: model = mock:<engine_id>@<version>
        # prompt_version may also carry engine_version for Lab runs.
        run_engine_id = MOCK_ENGINE_ID
        run_engine_version = run.prompt_version or MOCK_ENGINE_VERSION
        if run.model and str(run.model).startswith("mock:"):
            rest = str(run.model)[5:]
            if "@" in rest:
                run_engine_id, run_engine_version = rest.split("@", 1)
            else:
                run_engine_id = rest
        if run_engine_id != self._engine_id or run_engine_version != self._engine_version:
            raise_mock_run_error(
                MockRunErrorCode.MOCK_RUN_ENGINE_VERSION_MISMATCH, run_id=run.id
            )

        # configuration fingerprint: if both present must match.
        # (run field is source of truth; checkpoint checked in validate_checkpoint)

        stages = list(
            self._session.scalars(
                select(AnalysisRunStage).where(AnalysisRunStage.run_id == run.id)
            )
        )
        for stage in stages:
            if StageStatus(stage.status) != StageStatus.COMPLETED:
                continue
            if stage.output_artifact_id is None:
                # Completed stage must retain output artifact reference.
                artifact = self._session.scalars(
                    select(AnalysisArtifact).where(
                        AnalysisArtifact.run_id == run.id,
                        AnalysisArtifact.subject_id == stage.stage_key,
                    )
                ).first()
                if artifact is None and not for_resume_plan:
                    raise_mock_run_error(
                        MockRunErrorCode.MOCK_RUN_NOT_RECOVERABLE,
                        run_id=run.id,
                        stage_key=stage.stage_key,
                        detail_code="COMPLETED_OUTPUT_MISSING",
                    )


class MockRunStartupRecoveryAdapter:
    """Adapter for sidecar startup: scan + mark interrupted only.

    Does not modify shared main.py. Integration wires this adapter.
    Never auto-resumes, never starts tasks, never consumes synthetic budget.
    """

    integration_issue = (
        "Shared apps/api/app/main.py startup still calls mark_interrupted_runs_failed; "
        "Integration should optionally invoke MockRunStartupRecoveryAdapter.reconcile() "
        "for mock lab runs without enabling auto-resume."
    )

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        lab_enabled: bool = False,
        audit_sink: MockRunAuditSink | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._lab_enabled = lab_enabled
        self._audit = audit_sink or MockRunAuditSink(emit_logs=False)
        self.last_marked: tuple[int, ...] = ()
        self.auto_resume_invoked = False
        self.budget_consumed = False
        self.task_started = False

    def reconcile(self) -> tuple[int, ...]:
        session = self._session_factory()
        try:
            recovery = MockRunRecoveryService(
                session,
                lab_enabled=self._lab_enabled,
                audit_sink=self._audit,
                explicit_resume_allowed=False,
            )
            run_ids = recovery.scan_recoverable_runs()
            marked: list[int] = []
            for run_id in run_ids:
                decision = recovery.mark_process_interrupted(run_id)
                if decision.marked_interrupted:
                    marked.append(run_id)
            # Hard guarantees for startup path.
            self.auto_resume_invoked = False
            self.budget_consumed = False
            self.task_started = False
            self.last_marked = tuple(marked)
            return self.last_marked
        finally:
            session.close()


__all__ = [
    "CHECKPOINT_SCHEMA",
    "CHECKPOINT_VERSION",
    "CheckpointValidationResult",
    "CheckpointValidator",
    "MOCK_RUN_METADATA_SCHEMA",
    "MOCK_RUN_METADATA_VERSION",
    "MOCK_RUN_SIDECAR_SCHEMA",
    "MOCK_RUN_SIDECAR_VERSION",
    "MockRunRecoveryService",
    "MockRunStartupRecoveryAdapter",
]
