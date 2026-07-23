"""Mock Whole-Book Run creation and control service (Phase 2A Agent M).

Creation order is frozen. Pre-create failures leave no Run/Stage/Artifact/Asset.
Uses Phase 1A AnalysisRun / Stages only — no second Run system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, AnalysisRunStage, Book, BookSnapshot
from app.narrative_core.enums import (
    AnalysisScopeType,
    AnalysisType,
    RunStatus,
    SnapshotStatus,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.actions import (
    MockRunAction,
    action_allowed_for_state,
)
from app.narrative_core.run_shell_contract.create_run import (
    CREATE_MOCK_RUN_SEQUENCE,
    CreateMockWholeBookRunRequest,
    CreateMockWholeBookRunResult,
    MockProfile,
)
from app.narrative_core.run_shell_contract.errors import MockRunErrorCode, mock_run_error
from app.narrative_core.run_shell_contract.idempotency import (
    DEFAULT_MOCK_RUN_CONCURRENCY_POLICY,
    occupies_active_slot,
)
from app.narrative_core.run_shell_contract.mock_lab import MOCK_ENGINE_ID
from app.narrative_core.run_shell_contract.stage_lifecycle import (
    build_stage_retry_impact,
)
from app.narrative_core.services.in_process_mock_run_task_registry import (
    InProcessMockRunTaskRegistry,
    get_default_mock_run_task_registry,
)
from app.narrative_core.services.mock_lab_authorization_service import (
    MockLabAuthorizationDenied,
    MockLabAuthorizationService,
)
from app.narrative_core.services.mock_run_metadata import (
    build_mock_run_metadata,
    hash_create_payload,
    parse_metadata_json,
    serialize_metadata,
    MockRunMetadataError,
)
from app.narrative_core.services.mock_run_state_service import (
    MockRunStateError,
    MockRunStateService,
    map_db_status_to_view,
)
from app.narrative_core.services.mock_whole_book_engine import (
    MOCK_ENGINE_VERSION,
    MockWholeBookAnalysisEngine,
)
from app.narrative_core.services.run_stage_service import RunStageService
from app.narrative_core.services.whole_book_stage_plan import (
    build_whole_book_stage_plan,
    stage_definitions_to_run_stage_keys,
)


class MockWholeBookRunError(Exception):
    def __init__(
        self,
        code: MockRunErrorCode,
        *,
        run_id: int | None = None,
        stage_key: str | None = None,
        detail_code: str | None = None,
    ) -> None:
        self.error = mock_run_error(
            code, run_id=run_id, stage_key=stage_key, detail_code=detail_code
        )
        super().__init__(self.error.message)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MockWholeBookRunService:
    """Lab-only whole-book mock run lifecycle service."""

    CREATE_SEQUENCE = CREATE_MOCK_RUN_SEQUENCE

    def __init__(
        self,
        session: Session,
        *,
        auth: MockLabAuthorizationService | None = None,
        stage_service: RunStageService | None = None,
        state_service: MockRunStateService | None = None,
        task_registry: InProcessMockRunTaskRegistry | None = None,
        engine: MockWholeBookAnalysisEngine | None = None,
    ) -> None:
        self._session = session
        self._auth = auth or MockLabAuthorizationService()
        self._stages = stage_service or RunStageService(session)
        self._state = state_service or MockRunStateService(session)
        self._registry = task_registry or get_default_mock_run_task_registry()
        self._engine = engine or MockWholeBookAnalysisEngine()

    # ----- Authorization helpers -----

    def authorize(
        self,
        *,
        loopback: bool,
        request_marker_present: bool,
        declare_mock_lab: bool = True,
        snapshot_completed: bool = True,
    ) -> None:
        try:
            self._auth.require(
                loopback=loopback,
                request_marker_present=request_marker_present,
                requested_engine_id=MOCK_ENGINE_ID,
                engine_is_mock=True,
                engine_non_production=True,
                capability_context_is_lab=True,
                snapshot_completed=snapshot_completed,
                declare_mock_lab=declare_mock_lab,
            )
        except MockLabAuthorizationDenied as exc:
            raise MockWholeBookRunError(exc.error.code) from exc

    # ----- Create -----

    def create_run(
        self,
        request: CreateMockWholeBookRunRequest,
        *,
        loopback: bool,
        request_marker_present: bool,
        declare_mock_lab: bool = True,
        auto_start: bool = False,
    ) -> CreateMockWholeBookRunResult:
        # 1. authorize
        self.authorize(
            loopback=loopback,
            request_marker_present=request_marker_present,
            declare_mock_lab=declare_mock_lab,
        )

        # Idempotency lookup before any writes
        existing = self._find_by_idempotency_key(request.idempotency_key)
        if existing is not None:
            return self._idempotent_result(existing, request)

        # 2. validate snapshot
        book, snapshot = self._validate_snapshot(request.book_id, request.book_snapshot_id)

        # 3. validate request (mode / modules / fingerprints / body keys)
        mode, modules = self._validate_request(request)

        # 4. resolve modules
        resolved = tuple(modules)

        # 5. build stage plan
        try:
            plan = build_whole_book_stage_plan(mode=mode, requested_modules=resolved)
        except NarrativeCoreError as exc:
            if exc.code == NarrativeCoreErrorCode.WHOLE_BOOK_MODULE_NOT_SUPPORTED:
                raise MockWholeBookRunError(
                    MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                    detail_code="MODULE_INVALID",
                ) from exc
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                detail_code="STAGE_PLAN_INVALID",
            ) from exc
        stage_keys = tuple(stage_definitions_to_run_stage_keys(plan.stages))

        # 6. reserve mock execution slot (active run conflict)
        self._reserve_slot(int(book.id))

        payload_hash = hash_create_payload(
            book_id=int(request.book_id),
            book_snapshot_id=int(request.book_snapshot_id),
            analysis_mode=mode.value,
            requested_modules=[m.value for m in resolved],
            configuration_fingerprint=request.configuration_fingerprint,
            preflight_fingerprint=request.preflight_fingerprint,
            mock_profile=request.mock_profile.value,
        )
        metadata = build_mock_run_metadata(
            book_id=int(book.id),
            book_snapshot_id=int(snapshot.id),
            analysis_mode=mode.value,
            requested_modules=[m.value for m in resolved],
            resolved_modules=[m.value for m in resolved],
            engine_id=MOCK_ENGINE_ID,
            engine_version=MOCK_ENGINE_VERSION,
            configuration_fingerprint=request.configuration_fingerprint,
            preflight_fingerprint=request.preflight_fingerprint,
            mock_profile=request.mock_profile.value,
            requested_by=request.requested_by,
            idempotency_key=request.idempotency_key,
            idempotency_payload_hash=payload_hash,
            state_version=0,
        )

        # 7–8. create AnalysisRun + Stages
        try:
            run = self._stages.create_scoped_run(
                scope_type=AnalysisScopeType.BOOK,
                analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
                book_id=int(book.id),
                book_snapshot_id=int(snapshot.id),
                configuration_fingerprint=request.configuration_fingerprint,
                provider="mock_lab",
                model=MOCK_ENGINE_ID,
                prompt_version="none",
                schema_version="mock-lab-v1",
                status=RunStatus.PENDING.value,
                task_type="whole_book_mock_lab",
                analysis_mode=mode.value,
                client_request_id=request.idempotency_key[:64],
                validated_output=serialize_metadata(metadata),
                execution_mode="local",
            )
            self._stages.initialize_run_stages(int(run.id), list(stage_keys))
        except Exception:
            self._session.rollback()
            raise

        # 9. register execution task
        self._registry.register(int(run.id))

        self._session.commit()
        self._session.refresh(run)

        created_at = run.created_at
        created_iso = (
            created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            if isinstance(created_at, datetime)
            else _utc_now_iso()
        )
        return CreateMockWholeBookRunResult(
            run_id=int(run.id),
            book_id=int(book.id),
            book_snapshot_id=int(snapshot.id),
            status=WholeBookRunViewStatus.PENDING,
            analysis_mode=mode,
            requested_modules=resolved,
            resolved_modules=resolved,
            stage_plan=stage_keys,
            mock=True,
            non_production=True,
            created=True,
            duplicate_of_run_id=None,
            created_at=created_iso,
        )

    # ----- Reads -----

    def get_run(self, run_id: int) -> dict[str, Any]:
        run, meta = self._require_mock_run(run_id)
        stages = list(self._stages.get_run_stages(int(run.id)))
        return self._run_view(run, meta, stages)

    def get_run_stages(self, run_id: int) -> list[dict[str, Any]]:
        run, _meta = self._require_mock_run(run_id)
        return [self._stage_view(s) for s in self._stages.get_run_stages(int(run.id))]

    # ----- Actions -----

    def pause_run(
        self,
        run_id: int,
        *,
        expected_state: WholeBookRunViewStatus | None = None,
        expected_version: int | None = None,
        operation_idempotency_key: str = "pause",
    ) -> dict[str, Any]:
        run, meta = self._require_mock_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current == WholeBookRunViewStatus.PAUSED:
            return self._action_result(run, meta, MockRunAction.PAUSE, idempotent=True)
        if not action_allowed_for_state(MockRunAction.PAUSE, current):
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED, run_id=int(run.id)
            )
        exp_state = expected_state or current
        try:
            result = self._state.transition(
                run,
                to_state=WholeBookRunViewStatus.PAUSED,
                expected_state=exp_state,
                expected_version=expected_version,
                metadata=meta,
                operation_idempotency_key=operation_idempotency_key,
            )
        except MockRunStateError as exc:
            raise MockWholeBookRunError(exc.error.code, run_id=int(run.id)) from exc
        meta["state_version"] = result.version
        run.validated_output = serialize_metadata(meta)
        self._stages.pause_run(int(run.id))
        # Ensure run status remains paused after pause_run (which also sets it).
        run.status = RunStatus.PAUSED.value
        self._registry.request_pause(int(run.id))
        self._session.commit()
        return self._action_result(
            run, meta, MockRunAction.PAUSE, idempotent=result.idempotent_replay
        )

    def resume_run(
        self,
        run_id: int,
        *,
        expected_state: WholeBookRunViewStatus | None = None,
        expected_version: int | None = None,
        operation_idempotency_key: str = "resume",
    ) -> dict[str, Any]:
        run, meta = self._require_mock_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current == WholeBookRunViewStatus.RUNNING:
            return self._action_result(run, meta, MockRunAction.RESUME, idempotent=True)
        if not action_allowed_for_state(MockRunAction.RESUME, current):
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED, run_id=int(run.id)
            )
        exp_state = expected_state or current
        try:
            result = self._state.transition(
                run,
                to_state=WholeBookRunViewStatus.RUNNING,
                expected_state=exp_state,
                expected_version=expected_version,
                metadata=meta,
                operation_idempotency_key=operation_idempotency_key,
            )
        except MockRunStateError as exc:
            raise MockWholeBookRunError(exc.error.code, run_id=int(run.id)) from exc
        meta["state_version"] = result.version
        run.validated_output = serialize_metadata(meta)
        self._stages.resume_run(int(run.id))
        run.status = RunStatus.RUNNING.value
        self._registry.clear_pause_request(int(run.id))
        self._registry.mark_running(int(run.id))
        self._session.commit()
        return self._action_result(
            run, meta, MockRunAction.RESUME, idempotent=result.idempotent_replay
        )

    def cancel_run(
        self,
        run_id: int,
        *,
        expected_state: WholeBookRunViewStatus | None = None,
        expected_version: int | None = None,
        confirm_cancel: bool = True,
        operation_idempotency_key: str = "cancel",
    ) -> dict[str, Any]:
        if not confirm_cancel:
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                run_id=int(run_id),
                detail_code="CONFIRM_CANCEL_REQUIRED",
            )
        run, meta = self._require_mock_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current == WholeBookRunViewStatus.CANCELLED:
            return self._action_result(run, meta, MockRunAction.CANCEL, idempotent=True)
        if not action_allowed_for_state(MockRunAction.CANCEL, current):
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED, run_id=int(run.id)
            )
        exp_state = expected_state or current
        try:
            result = self._state.transition(
                run,
                to_state=WholeBookRunViewStatus.CANCELLED,
                expected_state=exp_state,
                expected_version=expected_version,
                metadata=meta,
                operation_idempotency_key=operation_idempotency_key,
            )
        except MockRunStateError as exc:
            raise MockWholeBookRunError(exc.error.code, run_id=int(run.id)) from exc
        meta["state_version"] = result.version
        run.validated_output = serialize_metadata(meta)
        # Cancel open stages; retain completed artifacts/assets.
        for stage in self._stages.get_run_stages(int(run.id)):
            status = StageStatus(stage.status)
            if status in {
                StageStatus.PENDING,
                StageStatus.RUNNING,
                StageStatus.PAUSED,
                StageStatus.INTERRUPTED,
                StageStatus.FAILED,
            }:
                try:
                    self._stages.transition_stage(
                        int(run.id),
                        stage.stage_key,
                        StageStatus.CANCELLED,
                        error_code=MockRunErrorCode.MOCK_RUN_CANCELLED.value,
                        error_message="cancelled by mock lab",
                    )
                except NarrativeCoreError:
                    # Retain whatever is already terminal.
                    pass
        run.status = RunStatus.CANCELLED.value
        run.error_code = MockRunErrorCode.MOCK_RUN_CANCELLED.value
        self._registry.request_cancel(int(run.id))
        self._registry.mark_finished(int(run.id))
        self._session.commit()
        return self._action_result(
            run, meta, MockRunAction.CANCEL, idempotent=result.idempotent_replay
        )

    def retry_stage(
        self,
        run_id: int,
        stage_key: str,
        *,
        expected_state: WholeBookRunViewStatus | None = None,
        expected_version: int | None = None,
        operation_idempotency_key: str = "retry",
    ) -> dict[str, Any]:
        run, meta = self._require_mock_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current == WholeBookRunViewStatus.RUNNING:
            # Idempotent if already running after prior retry.
            stage = self._stages._stages.get_stage(int(run.id), stage_key)  # noqa: SLF001
            if stage is not None and StageStatus(stage.status) == StageStatus.RUNNING:
                return self._action_result(
                    run, meta, MockRunAction.RETRY, idempotent=True, stage_key=stage_key
                )
        if current != WholeBookRunViewStatus.FAILED and current != WholeBookRunViewStatus.RUNNING:
            if not action_allowed_for_state(MockRunAction.RETRY, current):
                raise MockWholeBookRunError(
                    MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED, run_id=int(run.id)
                )

        stage = self._stages._stages.get_stage(int(run.id), stage_key)  # noqa: SLF001
        if stage is None:
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_NOT_FOUND, run_id=int(run.id), stage_key=stage_key
            )
        if StageStatus(stage.status) == StageStatus.COMPLETED:
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
                stage_key=stage_key,
                detail_code="COMPLETED_STAGE_NO_RERUN",
            )
        if StageStatus(stage.status) != StageStatus.FAILED:
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
                stage_key=stage_key,
                detail_code="RETRY_REQUIRES_FAILED",
            )

        impact = build_stage_retry_impact(stage_key)
        # Reset failed stage (bumps attempt_count).
        self._stages.retry_failed_stage(int(run.id), stage_key)
        # Downstream: only non-completed non-pending stages need attention.
        # PENDING downstream stay PENDING; COMPLETED upstream untouched.
        for down_key in impact.reset_downstream_stage_keys:
            down = self._stages._stages.get_stage(int(run.id), down_key)  # noqa: SLF001
            if down is None:
                continue
            st = StageStatus(down.status)
            if st == StageStatus.COMPLETED:
                continue
            if st == StageStatus.PENDING:
                continue
            if st == StageStatus.FAILED:
                # Clear failed downstream back onto runnable path without executing.
                self._stages.retry_failed_stage(int(run.id), down_key)
                # Leave as running briefly then they will re-exec after upstream;
                # demote conceptually by not executing until ordered loop reaches them.
                # Transition RUNNING is the only legal reset from FAILED.
            # PAUSED / INTERRUPTED / RUNNING: leave for orchestrator ordering.

        exp_state = expected_state or current
        try:
            result = self._state.transition(
                run,
                to_state=WholeBookRunViewStatus.RUNNING,
                expected_state=exp_state if current != WholeBookRunViewStatus.RUNNING else WholeBookRunViewStatus.RUNNING,
                expected_version=expected_version,
                metadata=meta,
                operation_idempotency_key=operation_idempotency_key,
            )
        except MockRunStateError as exc:
            # If already running, treat as applied path.
            if current != WholeBookRunViewStatus.RUNNING:
                raise MockWholeBookRunError(exc.error.code, run_id=int(run.id)) from exc
            result = None
        if result is not None:
            meta["state_version"] = result.version
        run.validated_output = serialize_metadata(meta)
        run.status = RunStatus.RUNNING.value
        self._registry.mark_running(int(run.id))
        self._session.commit()
        return self._action_result(
            run,
            meta,
            MockRunAction.RETRY,
            idempotent=bool(result and result.idempotent_replay),
            stage_key=stage_key,
        )

    # ----- Internals -----

    def _validate_snapshot(
        self, book_id: int, book_snapshot_id: int
    ) -> tuple[Book, BookSnapshot]:
        book = self._session.get(Book, int(book_id))
        if book is None:
            raise MockWholeBookRunError(MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID)
        snapshot = self._session.get(BookSnapshot, int(book_snapshot_id))
        if snapshot is None:
            raise MockWholeBookRunError(MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID)
        if int(snapshot.book_id) != int(book_id):
            raise MockWholeBookRunError(MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID)
        if str(snapshot.snapshot_status) != SnapshotStatus.COMPLETED.value:
            raise MockWholeBookRunError(MockRunErrorCode.MOCK_RUN_SNAPSHOT_INVALID)
        return book, snapshot

    def _validate_request(
        self, request: CreateMockWholeBookRunRequest
    ) -> tuple[WholeBookAnalysisMode, tuple[WholeBookModuleKey, ...]]:
        try:
            mode = WholeBookAnalysisMode(request.analysis_mode)
        except ValueError as exc:
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                detail_code="MODE_INVALID",
            ) from exc
        modules: list[WholeBookModuleKey] = []
        for raw in request.requested_modules:
            try:
                modules.append(WholeBookModuleKey(raw))
            except ValueError as exc:
                raise MockWholeBookRunError(
                    MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                    detail_code="MODULE_INVALID",
                ) from exc
        if not str(request.preflight_fingerprint).strip():
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                detail_code="PREFLIGHT_FINGERPRINT_REQUIRED",
            )
        if not str(request.configuration_fingerprint).strip():
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_OPERATION_NOT_ALLOWED,
                detail_code="CONFIGURATION_FINGERPRINT_REQUIRED",
            )
        # Engine must be mock / non-production.
        health = self._engine.health_check()
        if not health.get("mock") or health.get("production_ready") is True:
            raise MockWholeBookRunError(MockRunErrorCode.MOCK_ENGINE_REQUIRED)
        if str(self._engine.engine_id) != MOCK_ENGINE_ID:
            raise MockWholeBookRunError(MockRunErrorCode.MOCK_ENGINE_REQUIRED)
        return mode, tuple(modules)

    def _reserve_slot(self, book_id: int) -> None:
        policy = DEFAULT_MOCK_RUN_CONCURRENCY_POLICY
        active = self._list_active_mock_runs_for_book(book_id)
        if len(active) >= policy.max_active_mock_runs_per_book:
            raise MockWholeBookRunError(MockRunErrorCode.MOCK_RUN_ALREADY_ACTIVE)

    def _list_active_mock_runs_for_book(self, book_id: int) -> list[AnalysisRun]:
        rows = list(
            self._session.scalars(
                select(AnalysisRun).where(AnalysisRun.book_id == int(book_id))
            )
        )
        out: list[AnalysisRun] = []
        for run in rows:
            if not run.validated_output:
                continue
            try:
                meta = parse_metadata_json(run.validated_output)
            except MockRunMetadataError:
                continue
            if not meta.get("mock"):
                continue
            view = map_db_status_to_view(str(run.status))
            if occupies_active_slot(view):
                out.append(run)
        return out

    def _find_by_idempotency_key(self, key: str) -> AnalysisRun | None:
        rows = list(
            self._session.scalars(
                select(AnalysisRun).where(AnalysisRun.client_request_id == key[:64])
            )
        )
        for run in rows:
            try:
                parse_metadata_json(run.validated_output)
            except MockRunMetadataError:
                continue
            return run
        return None

    def _idempotent_result(
        self, run: AnalysisRun, request: CreateMockWholeBookRunRequest
    ) -> CreateMockWholeBookRunResult:
        meta = parse_metadata_json(run.validated_output)
        payload_hash = hash_create_payload(
            book_id=int(request.book_id),
            book_snapshot_id=int(request.book_snapshot_id),
            analysis_mode=str(
                request.analysis_mode.value
                if isinstance(request.analysis_mode, WholeBookAnalysisMode)
                else request.analysis_mode
            ),
            requested_modules=[
                m.value if isinstance(m, WholeBookModuleKey) else str(m)
                for m in request.requested_modules
            ],
            configuration_fingerprint=request.configuration_fingerprint,
            preflight_fingerprint=request.preflight_fingerprint,
            mock_profile=(
                request.mock_profile.value
                if isinstance(request.mock_profile, MockProfile)
                else str(request.mock_profile)
            ),
        )
        if meta.get("idempotency_payload_hash") != payload_hash:
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_IDEMPOTENCY_CONFLICT, run_id=int(run.id)
            )
        mode = WholeBookAnalysisMode(str(meta["analysis_mode"]))
        requested = tuple(WholeBookModuleKey(m) for m in meta["requested_modules"])
        resolved = tuple(WholeBookModuleKey(m) for m in meta["resolved_modules"])
        stages = list(self._stages.get_run_stages(int(run.id)))
        stage_plan = tuple(s.stage_key for s in stages)
        created_at = run.created_at
        created_iso = (
            created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            if isinstance(created_at, datetime)
            else _utc_now_iso()
        )
        return CreateMockWholeBookRunResult(
            run_id=int(run.id),
            book_id=int(meta["book_id"]),
            book_snapshot_id=int(meta["book_snapshot_id"]),
            status=map_db_status_to_view(str(run.status)),
            analysis_mode=mode,
            requested_modules=requested,
            resolved_modules=resolved,
            stage_plan=stage_plan,
            mock=True,
            non_production=True,
            created=False,
            duplicate_of_run_id=int(run.id),
            created_at=created_iso,
        )

    def _require_mock_run(self, run_id: int) -> tuple[AnalysisRun, dict[str, Any]]:
        run = self._session.get(AnalysisRun, int(run_id))
        if run is None:
            raise MockWholeBookRunError(MockRunErrorCode.MOCK_RUN_NOT_FOUND, run_id=int(run_id))
        try:
            meta = parse_metadata_json(run.validated_output)
        except MockRunMetadataError as exc:
            raise MockWholeBookRunError(
                MockRunErrorCode.MOCK_RUN_NON_MOCK_TARGET, run_id=int(run_id)
            ) from exc
        return run, meta

    def _run_view(
        self,
        run: AnalysisRun,
        meta: dict[str, Any],
        stages: Sequence[AnalysisRunStage],
    ) -> dict[str, Any]:
        return {
            "run_id": int(run.id),
            "book_id": int(meta["book_id"]),
            "book_snapshot_id": int(meta["book_snapshot_id"]),
            "status": map_db_status_to_view(str(run.status)).value,
            "analysis_mode": str(meta["analysis_mode"]),
            "requested_modules": list(meta["requested_modules"]),
            "resolved_modules": list(meta["resolved_modules"]),
            "stage_plan": [s.stage_key for s in stages],
            "engine_id": str(meta["engine_id"]),
            "engine_version": str(meta["engine_version"]),
            "configuration_fingerprint": str(meta["configuration_fingerprint"]),
            "preflight_fingerprint": str(meta.get("preflight_fingerprint") or ""),
            "mock_profile": str(meta.get("mock_profile") or ""),
            "mock": True,
            "non_production": True,
            "source": str(meta["source"]),
            "metadata_schema": str(meta["schema"]),
            "metadata_version": str(meta["version"]),
            "state_version": int(meta.get("state_version") or 0),
            "stages": [self._stage_view(s) for s in stages],
        }

    def _stage_view(self, stage: AnalysisRunStage) -> dict[str, Any]:
        return {
            "stage_key": str(stage.stage_key),
            "stage_order": int(stage.stage_order),
            "status": str(stage.status),
            "attempt_count": int(stage.attempt_count or 0),
            "error_code": stage.error_code,
            "has_checkpoint": bool(stage.checkpoint_json),
        }

    def _action_result(
        self,
        run: AnalysisRun,
        meta: dict[str, Any],
        action: MockRunAction,
        *,
        idempotent: bool = False,
        stage_key: str | None = None,
    ) -> dict[str, Any]:
        return {
            "run_id": int(run.id),
            "action": action.value,
            "requested": True,
            "accepted": True,
            "current_state": map_db_status_to_view(str(run.status)).value,
            "idempotent_replay": bool(idempotent),
            "stage_key": stage_key,
            "mock": True,
            "non_production": True,
            "state_version": int(meta.get("state_version") or 0),
        }


__all__ = [
    "MockWholeBookRunError",
    "MockWholeBookRunService",
]
