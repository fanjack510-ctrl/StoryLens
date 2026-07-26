"""Native Overview production orchestrator (STEP 2.3-A2/A3/A4).

Resumable multi-window Snapshot → Window → Adapter → Materialize → Projection.
Fixture execution is gated by ``is_pro_native_overview_enabled()``;
``WHOLE_BOOK_RUNS_ENDPOINT_DISABLED`` stays True for the legacy create path.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    AnalysisRunStage,
    Book,
    BookSnapshot,
    BookSnapshotChapter,
    BookSnapshotParagraph,
    Chapter,
    Paragraph,
    WholeBookRunStateVersion,
    WholeBookRunWindow,
    utc_now,
)
from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_DEVELOPMENT_WARNING,
    FIXTURE_ENGINE_ID,
    FIXTURE_ENGINE_VERSION,
    FIXTURE_PROMPT_VERSION,
    PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
    WALKING_SKELETON_USER_NOTICE,
    is_pro_native_overview_enabled,
)
from app.narrative_core.contracts.whole_book_overview_errors import (
    WHOLE_BOOK_OVERVIEW_ERROR_META,
    WholeBookOverviewErrorCode,
)
from app.narrative_core.contracts.whole_book_overview_state_machine import (
    OVERVIEW_PRODUCTION_STAGE_ORDER,
    validate_overview_run_transition,
    validate_overview_stage_transition,
    validate_window_transition,
)
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CONTRACT_VERSION,
    ChapterRef,
    CoverageDTO,
    CreateRunRequest,
    CreateRunResponse,
    EvidenceDeepLink,
    EvidenceIndexEntry,
    OverviewApiResponse,
    OverviewBodyDTO,
    OverviewBookSummary,
    OverviewRunRef,
    OverviewRunSummary,
    OverviewSnapshotSummary,
    PreflightBlockingError,
    PreflightResponse,
    PriorStateV1,
    ProgressDTO,
    ResumeRunRequest,
    RetryResumeRunResponse,
    RetryRunRequest,
    RunActionsDTO,
    RunStatusResponse,
    StateDeltaV1,
    WholeBookOverviewProjectionCandidateV1,
    WholeBookOverviewSynthesisInputV1,
    WholeBookOverviewWindowInputV1,
    WholeBookOverviewWindowResultV1,
    WindowParagraph,
    WindowSlice,
)
from app.narrative_core.enums import (
    AnalysisType,
    OverviewProductionStageKey,
    RunStatus,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WindowStatus,
)
from app.narrative_core.services.native_overview_context_windows import (
    OverviewWindowBudget,
    SnapshotParagraphRef,
    assert_full_coverage,
    build_overview_windows,
    estimate_window_count,
)
from app.narrative_core.services.native_overview_errors import (
    NATIVE_OVERVIEW_UNAVAILABLE_CODE,
    NativeOverviewError,
)
from app.narrative_core.services.native_overview_exception_map import map_engine_exception
from app.narrative_core.services.native_overview_fixture_adapter import (
    compute_window_input_hash,
    empty_prior_state,
)
from app.narrative_core.services.native_overview_materializer import (
    NativeOverviewMaterializer,
    merge_prior_with_delta,
)
from app.narrative_core.services.native_overview_provider_accounting import (
    OverviewProviderAccounting,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_overview_engine_loader import (
    EngineLoadError,
    load_overview_engine,
)
from app.narrative_core.services.whole_book_overview_engine_protocol import (
    ProviderTransport,
    WholeBookOverviewEngineAdapter,
)
OVERVIEW_PROJECTION_ARTIFACT_TYPE = "whole_book_overview_projection"
CONTROL_ARTIFACT_TYPE = "whole_book_overview_control"
PRIVATE_NATIVE_ENGINE_VERSION = "native-overview-1"
PRIVATE_NATIVE_PROMPT_VERSION = "native-overview-window-v1"

_PREPARING_STAGE_KEYS = frozenset(
    {
        OverviewProductionStageKey.SNAPSHOT_PREFLIGHT,
        OverviewProductionStageKey.BUILD_CONTEXT_WINDOWS,
    }
)

# Re-export for routers / tests.
__all__ = [
    "NATIVE_OVERVIEW_UNAVAILABLE_CODE",
    "NativeOverviewError",
    "NativeOverviewService",
    "OVERVIEW_PROJECTION_ARTIFACT_TYPE",
    "require_native_overview_enabled",
    "require_pro_license",
]


def require_native_overview_enabled() -> None:
    if not is_pro_native_overview_enabled():
        raise NativeOverviewError(
            NATIVE_OVERVIEW_UNAVAILABLE_CODE,
            "原生全书概览行走骨架未启用（PRO_NATIVE_OVERVIEW_ENABLED）。",
            http_status=503,
            details={"flag": "PRO_NATIVE_OVERVIEW_ENABLED", "enabled": False},
        )


def require_pro_license(session: Session) -> None:
    """Deprecated for native overview (CHG-20260726-004).

    Native ``whole_book_native`` + ``book_overview`` is FREE in StoryLens 1.1.x.
    Kept as a no-op export so older call sites/tests can still import the symbol.
    Future Pro modes (e.g. ``whole_book_enhanced``) must use CapabilityService /
    entitlement gates instead — do not delete ``PRO_LICENSE_REQUIRED``.
    """

    _ = session
    return None


class NativeOverviewService:
    """Orchestrates Snapshot → Windows → Adapter → Materialize → Projection."""

    def __init__(
        self,
        session: Session,
        *,
        adapter: WholeBookOverviewEngineAdapter | None = None,
        engine_id: str = FIXTURE_ENGINE_ID,
        transport: ProviderTransport | None = None,
        window_budget: OverviewWindowBudget | None = None,
    ) -> None:
        self._session = session
        self._engine_id = engine_id
        self._transport = transport
        self._window_budget = window_budget
        self._engine_load_error: EngineLoadError | None = None
        if adapter is not None:
            self._adapter: WholeBookOverviewEngineAdapter | None = adapter
        else:
            try:
                self._adapter = load_overview_engine(engine_id)
            except EngineLoadError as exc:
                self._adapter = None
                self._engine_load_error = exc
        self._snapshots = BookSnapshotServiceImpl(session)
        self._accounting = OverviewProviderAccounting(session)
        self._materializer = NativeOverviewMaterializer(session)
        # Explicit opt-in: Background path sets True via execute_run(commit_progress=...).
        self._commit_progress = False

    def _checkpoint_commit(self) -> None:
        """Commit a stable progress snapshot when Background progress mode is on."""

        if not self._commit_progress:
            return
        self._session.commit()

    def _engine_provider_name(self) -> str:
        return self._engine_id

    def _engine_version_label(self) -> str:
        adapter = self._adapter
        version = getattr(adapter, "engine_version", None) if adapter is not None else None
        if version:
            return str(version)
        if self._engine_id == PRIVATE_NATIVE_OVERVIEW_ENGINE_ID:
            return PRIVATE_NATIVE_ENGINE_VERSION
        return FIXTURE_ENGINE_VERSION

    def _prompt_version_label(self) -> str:
        adapter = self._adapter
        version = getattr(adapter, "prompt_version", None) if adapter is not None else None
        if version:
            return str(version)
        if self._engine_id == PRIVATE_NATIVE_OVERVIEW_ENGINE_ID:
            return PRIVATE_NATIVE_PROMPT_VERSION
        return FIXTURE_PROMPT_VERSION

    def _require_adapter(self) -> WholeBookOverviewEngineAdapter:
        if self._engine_load_error is not None:
            err = self._engine_load_error
            raise NativeOverviewError(
                err.code,
                err.message,
                details=err.details or {"engine_id": self._engine_id},
            )
        if self._adapter is None:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value,
                details={"engine_id": self._engine_id},
            )
        return self._adapter

    # ------------------------------------------------------------------
    # Preflight
    # ------------------------------------------------------------------

    def preflight(self, book_id: int) -> PreflightResponse:
        book = self._session.get(Book, int(book_id))
        # CHG-20260726-004: native overview entitlement is FREE in 1.1.x.
        # ``license_allowed`` means product entitlement allows this feature
        # (not "Pro edition active").
        license_allowed = True
        flag_on = is_pro_native_overview_enabled()

        if book is None:
            missing_warnings = (
                [FIXTURE_DEVELOPMENT_WARNING, WALKING_SKELETON_USER_NOTICE]
                if self._engine_id == FIXTURE_ENGINE_ID
                else []
            )
            return PreflightResponse(
                book_id=str(book_id),
                chapter_count=0,
                paragraph_count=0,
                character_count=0,
                snapshot_required=True,
                provider_configured=False,
                license_allowed=license_allowed,
                mode=WholeBookAnalysisMode.NATIVE,
                estimated_windows=0,
                estimated_tokens=0,
                estimated_cost=0.0,
                warnings=missing_warnings,
                blocking_errors=[
                    PreflightBlockingError(
                        code=WholeBookOverviewErrorCode.BOOK_NOT_FOUND,
                        message="未找到指定书籍。",
                    )
                ],
                run_creation_enabled=False,
                engine_id=self._engine_id,
                provider_id=self._engine_id,
                model_id=self._engine_version_label(),
            )

        chapter_count = int(
            self._session.scalar(
                select(func.count()).select_from(Chapter).where(Chapter.book_id == int(book_id))
            )
            or 0
        )
        paragraph_count = int(
            self._session.scalar(
                select(func.count()).select_from(Paragraph).where(Paragraph.book_id == int(book_id))
            )
            or 0
        )
        character_count = int(
            self._session.scalar(
                select(func.coalesce(func.sum(func.length(Paragraph.raw_text)), 0))
                .select_from(Paragraph)
                .where(Paragraph.book_id == int(book_id))
            )
            or 0
        )

        blocking: list[PreflightBlockingError | str] = []
        warnings: list[str] = []
        if self._engine_id == FIXTURE_ENGINE_ID:
            warnings = [FIXTURE_DEVELOPMENT_WARNING, WALKING_SKELETON_USER_NOTICE]
        if not flag_on:
            blocking.append(
                PreflightBlockingError(
                    code=NATIVE_OVERVIEW_UNAVAILABLE_CODE,
                    message="原生全书概览行走骨架未启用。",
                )
            )
            warnings.append("Feature flag PRO_NATIVE_OVERVIEW_ENABLED is off.")
        if paragraph_count <= 0 or character_count <= 0:
            blocking.append(
                PreflightBlockingError(
                    code=WholeBookOverviewErrorCode.BOOK_CONTENT_EMPTY,
                    message="书籍没有可用于分析的正文段落。",
                )
            )

        estimated_windows = estimate_window_count(
            paragraph_count,
            character_count=character_count,
            budget=self._window_budget,
        )

        from app.services.native_overview_ai_binding import (
            estimate_native_overview_usage,
            resolve_native_overview_ai_binding,
        )

        ai = resolve_native_overview_ai_binding(self._session)
        if self._engine_id == FIXTURE_ENGINE_ID:
            provider_id = FIXTURE_ENGINE_ID
            model_id = self._engine_version_label()
            provider_configured = True
        else:
            provider_id = ai.provider_id
            model_id = ai.model_id
            try:
                from app.narrative_core.services.native_overview_http_factory import (
                    is_cloud_provider_configured_for_native_overview,
                )

                provider_configured = is_cloud_provider_configured_for_native_overview()
            except Exception:  # noqa: BLE001
                provider_configured = False

        usage = estimate_native_overview_usage(
            character_count=character_count,
            estimated_windows=estimated_windows,
            model_id=ai.model_id,
        )
        estimated_tokens = int(usage["estimated_total_tokens"] or 0)
        estimated_cost = (
            float(usage["estimated_cost"])
            if usage.get("estimated_cost") is not None
            else 0.0
        )
        currency = str(usage.get("currency") or "CNY")

        # Paid Private path: never present a silent zero estimate as actionable.
        if (
            self._engine_id != FIXTURE_ENGINE_ID
            and character_count > 0
            and estimated_windows > 0
            and (
                estimated_tokens <= 0
                or not usage.get("pricing_available")
                or usage.get("estimated_cost") is None
                or float(usage["estimated_cost"]) <= 0
            )
        ):
            blocking.append(
                PreflightBlockingError(
                    code="COST_ESTIMATE_UNAVAILABLE",
                    message=(
                        "暂时无法可靠估算本次分析的 Token 和费用，"
                        "请检查模型价格或 Provider 配置后重试。"
                    ),
                )
            )
            estimated_cost = 0.0

        run_enabled = bool(
            flag_on
            and license_allowed
            and paragraph_count > 0
            and character_count > 0
            and not blocking
        )

        return PreflightResponse(
            book_id=str(book.id),
            chapter_count=chapter_count,
            paragraph_count=paragraph_count,
            character_count=character_count,
            snapshot_required=True,
            provider_configured=provider_configured,
            license_allowed=license_allowed,
            mode=WholeBookAnalysisMode.NATIVE,
            estimated_windows=estimated_windows,
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
            currency=currency,
            warnings=warnings,
            blocking_errors=blocking,
            run_creation_enabled=run_enabled,
            engine_id=self._engine_id,
            provider_id=provider_id,
            model_id=model_id,
        )

    # ------------------------------------------------------------------
    # Create + execute
    # ------------------------------------------------------------------

    def create_run(
        self,
        book_id: int,
        request: CreateRunRequest,
        *,
        defer_execution: bool = False,
    ) -> CreateRunResponse:
        require_native_overview_enabled()

        book = self._session.get(Book, int(book_id))
        if book is None:
            raise NativeOverviewError(WholeBookOverviewErrorCode.BOOK_NOT_FOUND.value)

        para_count = int(
            self._session.scalar(
                select(func.count()).select_from(Paragraph).where(Paragraph.book_id == int(book_id))
            )
            or 0
        )
        if para_count <= 0:
            raise NativeOverviewError(WholeBookOverviewErrorCode.BOOK_CONTENT_EMPTY.value)

        if request.mode != WholeBookAnalysisMode.NATIVE:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.PROVIDER_OUTPUT_INVALID.value,
                "walking skeleton only supports whole_book_native",
                http_status=422,
                details={"mode": request.mode.value},
            )
        if request.module_key != WholeBookModuleKey.BOOK_OVERVIEW:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.PROVIDER_OUTPUT_INVALID.value,
                "walking skeleton only supports book_overview",
                http_status=422,
                details={"module_key": request.module_key.value},
            )
        if not request.consent.confirmed:
            raise NativeOverviewError(WholeBookOverviewErrorCode.USER_CONSENT_REQUIRED.value)

        from app.services.native_overview_ai_binding import (
            resolve_native_overview_ai_binding,
        )

        ai = resolve_native_overview_ai_binding(self._session)
        create_provider = request.provider_id
        create_model = request.model_id
        if self._engine_id != FIXTURE_ENGINE_ID:
            create_provider = ai.provider_id
            create_model = ai.model_id
            # Refuse silent zero-cost consent for paid Private path.
            if (
                int(request.consent.estimated_tokens or 0) <= 0
                or float(request.consent.estimated_cost or 0) <= 0
            ):
                raise NativeOverviewError(
                    "COST_ESTIMATE_UNAVAILABLE",
                    "暂时无法可靠估算本次分析的 Token 和费用，请检查模型价格或 Provider 配置后重试。",
                    http_status=422,
                )

        existing = self._find_by_client_request_id(book_id, request.client_request_id)
        if existing is not None:
            return self._to_create_response(existing)

        snapshot = self._snapshots.create_or_reuse_snapshot(int(book_id))
        self._session.flush()

        now = utc_now()
        run = AnalysisRun(
            task_type="whole_book_overview",
            subject_type="book",
            subject_id=str(book_id),
            provider=create_provider if self._engine_id != FIXTURE_ENGINE_ID else self._engine_provider_name(),
            model=create_model if self._engine_id != FIXTURE_ENGINE_ID else self._engine_version_label(),
            prompt_version=self._prompt_version_label(),
            schema_version=CONTRACT_VERSION,
            input_hash=snapshot.content_hash or "",
            prompt_hash=self._prompt_version_label(),
            status=RunStatus.PENDING.value,
            progress_current=0,
            progress_total=1,
            analysis_type=AnalysisType.WHOLE_BOOK_NATIVE.value,
            scope_type="whole_book",
            book_id=int(book_id),
            book_snapshot_id=int(snapshot.id),
            client_request_id=request.client_request_id,
            configuration_fingerprint=self._config_fingerprint(),
            cloud_consent=bool(request.consent.confirmed),
            cloud_consent_at=now if request.consent.confirmed else None,
            started_at=now,
            execution_mode="cloud" if self._engine_id != FIXTURE_ENGINE_ID else "local",
            analysis_mode="automatic",
            sends_content_to_cloud=self._engine_id != FIXTURE_ENGINE_ID,
        )
        self._session.add(run)
        self._session.flush()

        for order, stage_key in enumerate(OVERVIEW_PRODUCTION_STAGE_ORDER):
            self._session.add(
                AnalysisRunStage(
                    run_id=run.id,
                    stage_key=stage_key.value,
                    stage_order=order,
                    status=StageStatus.PENDING.value,
                    checkpoint_json="{}",
                    attempt_count=0,
                )
            )
        self._session.flush()

        # HTTP create returns immediately; production path schedules execute_run
        # via BackgroundTasks. Direct service callers (directed tests) keep
        # inline execution unless defer_execution=True.
        self._session.commit()
        self._session.refresh(run)
        if not defer_execution:
            try:
                self.execute_run(int(run.id))
            except NativeOverviewError:
                self._session.commit()
                raise
            self._session.commit()
            self._session.refresh(run)
        return self._to_create_response(run)

    def execute_run(self, run_id: int, *, commit_progress: bool = False) -> AnalysisRun:
        """Run overview production stages.

        ``commit_progress=False`` (default): preserve single-transaction behavior for
        inline callers (create without defer, retry/resume).

        ``commit_progress=True`` (Background path): commit after windows are built,
        before each Provider call, after each window success/failure, and after
        finalize — so other Sessions can poll live progress without a long write txn
        during Provider wait.
        """

        previous_flag = self._commit_progress
        self._commit_progress = bool(commit_progress)
        run = self._session.get(AnalysisRun, int(run_id))
        if run is None:
            self._commit_progress = previous_flag
            raise NativeOverviewError(WholeBookOverviewErrorCode.RUN_NOT_FOUND.value)

        try:
            if run.status == RunStatus.PENDING.value:
                self._transition_run(run, RunStatus.PREPARING)

            self._run_stage(run, OverviewProductionStageKey.SNAPSHOT_PREFLIGHT, self._stage_snapshot)
            self._run_stage(
                run,
                OverviewProductionStageKey.BUILD_CONTEXT_WINDOWS,
                self._stage_build_windows,
            )

            if run.status == RunStatus.PREPARING.value:
                self._transition_run(run, RunStatus.ANALYZING)

            # Windows exist + analyzing: pollers must see 0/N (not 0/0).
            self._session.flush()
            self._checkpoint_commit()

            self._run_stage(
                run,
                OverviewProductionStageKey.EXTRACT_OVERVIEW_FACTS,
                self._stage_extract_windows,
            )
            # All windows committed — expose N/N before materialize/projection work.
            self._session.flush()
            self._checkpoint_commit()

            if run.status == RunStatus.ANALYZING.value:
                self._transition_run(run, RunStatus.MATERIALIZING)

            materialization = self._run_stage(
                run,
                OverviewProductionStageKey.MATERIALIZE_ASSETS,
                self._stage_materialize_windows,
            )
            if materialization is None:
                materialization = self._aggregate_materialization(run)

            if run.status == RunStatus.MATERIALIZING.value:
                self._transition_run(run, RunStatus.SYNTHESIZING)

            self._run_stage(
                run,
                OverviewProductionStageKey.GENERATE_OVERVIEW_PROJECTION,
                lambda r, s: self._stage_projection(r, s, materialization),
            )
            self._run_stage(run, OverviewProductionStageKey.FINALIZE, self._stage_finalize)
            self._transition_run(run, RunStatus.COMPLETED)
            windows = self._list_windows(int(run.id))
            completed = sum(1 for w in windows if w.status == WindowStatus.COMPLETED.value)
            run.completed_at = utc_now()
            run.progress_current = completed
            run.progress_total = max(len(windows), 1)
            run.error_code = None
            run.error_message = None
            run.retryable = False
            self._session.flush()
            self._checkpoint_commit()
            return run
        except NativeOverviewError as exc:
            self._fail_run_with_progress(run, exc)
            raise
        except Exception as exc:  # noqa: BLE001
            wrapped = map_engine_exception(exc, run_id=str(run.id))
            self._fail_run_with_progress(run, wrapped)
            raise wrapped from exc
        finally:
            self._commit_progress = previous_flag

    def retry_run(self, run_id: int, request: RetryRunRequest) -> RetryResumeRunResponse:
        require_native_overview_enabled()
        run = self._require_overview_run(run_id)

        prior = self._find_control_action(int(run.id), "retry", request.client_request_id)
        if prior is not None:
            return self._to_retry_resume_response(
                run, message="idempotent retry replay"
            )

        if run.status == RunStatus.COMPLETED.value:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.RUN_ALREADY_COMPLETED.value,
                run_id=str(run.id),
            )
        if run.status != RunStatus.FAILED.value:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.RUN_NOT_RETRYABLE.value,
                run_id=str(run.id),
                details={"status": run.status},
            )

        landing = self._retry_landing_status(run)
        run.error_code = None
        run.error_message = None
        run.retryable = False
        run.completed_at = None
        self._clear_failed_stage_errors(run)
        self._transition_run(run, landing)

        try:
            self.execute_run(int(run.id))
        except NativeOverviewError:
            self._session.commit()
            raise
        self._remember_control_action(run, "retry", request.client_request_id)
        self._session.commit()
        self._session.refresh(run)
        return self._to_retry_resume_response(
            run,
            message=request.reason or "Retry accepted; completed windows will be skipped.",
        )

    def resume_run(self, run_id: int, request: ResumeRunRequest) -> RetryResumeRunResponse:
        require_native_overview_enabled()
        run = self._require_overview_run(run_id)

        prior = self._find_control_action(int(run.id), "resume", request.client_request_id)
        if prior is not None:
            return self._to_retry_resume_response(
                run, message="idempotent resume replay"
            )

        if run.status == RunStatus.COMPLETED.value:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.RUN_ALREADY_COMPLETED.value,
                run_id=str(run.id),
            )
        if run.status != RunStatus.PAUSED.value:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.RUN_NOT_RESUMABLE.value,
                run_id=str(run.id),
                details={"status": run.status},
            )
        self._transition_run(run, RunStatus.ANALYZING)
        try:
            self.execute_run(int(run.id))
        except NativeOverviewError:
            self._session.commit()
            raise
        self._remember_control_action(run, "resume", request.client_request_id)
        self._session.commit()
        self._session.refresh(run)
        return self._to_retry_resume_response(
            run,
            message="Resume accepted; continuing from paused checkpoint.",
        )

    # ------------------------------------------------------------------
    # Read APIs
    # ------------------------------------------------------------------

    def get_run(self, run_id: int) -> RunStatusResponse:
        require_native_overview_enabled()
        run = self._require_overview_run(run_id)
        windows = self._list_windows(int(run.id))
        completed = sum(1 for w in windows if w.status == WindowStatus.COMPLETED.value)
        total = len(windows)
        percent = (
            100.0
            if total and completed == total and run.status == RunStatus.COMPLETED.value
            else ((completed / total * 100.0) if total else 0.0)
        )
        usage = self._accounting.run_usage_totals(int(run.id))
        current_stage = self._current_stage_key(run)
        error_code = None
        if run.error_code:
            try:
                error_code = WholeBookOverviewErrorCode(run.error_code)
            except ValueError:
                error_code = None
        can_resume = run.status == RunStatus.PAUSED.value
        can_retry = bool(run.retryable) and run.status == RunStatus.FAILED.value
        return RunStatusResponse(
            run_id=str(run.id),
            book_id=str(run.book_id),
            snapshot_id=str(run.book_snapshot_id),
            mode=WholeBookAnalysisMode.NATIVE,
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            status=RunStatus(run.status),
            current_stage=current_stage,
            progress=ProgressDTO(
                completed_windows=completed,
                total_windows=total,
                percent=percent,
                current_window_index=self._current_window_index(windows),
                failed_window_index=next(
                    (w.window_index for w in windows if w.status == WindowStatus.FAILED.value),
                    None,
                ),
            ),
            estimated_tokens=0,
            actual_tokens=int(usage.get("actual_tokens") or 0),
            estimated_cost=0.0,
            actual_cost=float(usage.get("actual_cost") or 0.0),
            provider=run.provider,
            model=run.model,
            error=run.error_message,
            error_code=error_code,
            retryable=bool(run.retryable),
            actions=RunActionsDTO(can_retry=can_retry, can_resume=can_resume),
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )

    def get_overview(self, run_id: int) -> OverviewApiResponse:
        require_native_overview_enabled()
        run = self._require_overview_run(run_id)
        if run.status != RunStatus.COMPLETED.value:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.PROJECTION_FAILED.value,
                "Overview projection is not ready.",
                http_status=409,
                run_id=str(run.id),
                details={"status": run.status},
            )
        artifact = self._session.scalar(
            select(AnalysisArtifact)
            .where(
                AnalysisArtifact.run_id == run.id,
                AnalysisArtifact.artifact_type == OVERVIEW_PROJECTION_ARTIFACT_TYPE,
            )
            .order_by(AnalysisArtifact.id.desc())
        )
        if artifact is None:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.PROJECTION_FAILED.value,
                run_id=str(run.id),
            )
        payload = json.loads(artifact.payload_json)
        overview = OverviewBodyDTO.model_validate(payload.get("overview") or {})
        evidence_index = [
            EvidenceIndexEntry.model_validate(row) for row in (payload.get("evidence_index") or [])
        ]
        coverage = CoverageDTO.model_validate(payload.get("coverage") or {})
        book = self._session.get(Book, int(run.book_id)) if run.book_id else None
        snapshot = (
            self._session.get(BookSnapshot, int(run.book_snapshot_id))
            if run.book_snapshot_id
            else None
        )
        return OverviewApiResponse(
            run=OverviewRunSummary(
                run_id=str(run.id),
                status=RunStatus(run.status),
                mode=WholeBookAnalysisMode.NATIVE,
                module_key=WholeBookModuleKey.BOOK_OVERVIEW,
                current_stage=OverviewProductionStageKey.FINALIZE,
            ),
            book=OverviewBookSummary(
                book_id=str(run.book_id),
                title=(book.title if book else ""),
            ),
            snapshot=OverviewSnapshotSummary(
                snapshot_id=str(run.book_snapshot_id),
                status=str(getattr(snapshot, "snapshot_status", None) or "completed"),
            ),
            coverage=coverage,
            overview=overview,
            warnings=list(payload.get("warnings") or [FIXTURE_DEVELOPMENT_WARNING]),
            evidence_index=evidence_index,
            generated_at=_parse_dt(payload.get("generated_at")) or utc_now(),
            engine_version=str(payload.get("engine_version") or FIXTURE_ENGINE_VERSION),
            prompt_version=str(payload.get("prompt_version") or FIXTURE_PROMPT_VERSION),
            contract_version=CONTRACT_VERSION,
        )

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------

    def _stage_snapshot(self, run: AnalysisRun, stage: AnalysisRunStage) -> BookSnapshot:
        assert run.book_id is not None
        snapshot = self._snapshots.create_or_reuse_snapshot(int(run.book_id))
        run.book_snapshot_id = int(snapshot.id)
        stage.checkpoint_json = json.dumps(
            {"snapshot_id": snapshot.id, "content_hash": snapshot.content_hash},
            ensure_ascii=False,
        )
        return snapshot

    def _stage_build_windows(
        self, run: AnalysisRun, stage: AnalysisRunStage
    ) -> list[WholeBookRunWindow]:
        assert run.book_snapshot_id is not None
        snap_paragraphs = list(
            self._session.scalars(
                select(BookSnapshotParagraph)
                .where(BookSnapshotParagraph.snapshot_id == int(run.book_snapshot_id))
                .order_by(BookSnapshotParagraph.paragraph_order)
            )
        )
        if not snap_paragraphs:
            raise NativeOverviewError(WholeBookOverviewErrorCode.BOOK_CONTENT_EMPTY.value)

        chapters = {
            c.id: c
            for c in self._session.scalars(
                select(BookSnapshotChapter).where(
                    BookSnapshotChapter.snapshot_id == int(run.book_snapshot_id)
                )
            )
        }
        refs = self._to_snapshot_refs(snap_paragraphs, chapters)
        try:
            planned = build_overview_windows(refs, budget=self._window_budget)
            assert_full_coverage(planned, refs)
        except ValueError as exc:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.WINDOW_BUILD_FAILED.value,
                str(exc),
                run_id=str(run.id),
                stage_key=stage.stage_key,
            ) from exc

        existing = self._list_windows(int(run.id))
        by_hash = {w.input_hash: w for w in existing if w.input_hash}
        by_index = {int(w.window_index): w for w in existing}
        windows: list[WholeBookRunWindow] = []

        for plan in planned:
            order_map = {pid: i for i, pid in enumerate(plan.snapshot_paragraph_ids)}
            slice_paras = [p for p in snap_paragraphs if p.id in set(plan.snapshot_paragraph_ids)]
            slice_paras.sort(key=lambda p: order_map.get(p.id, 0))
            hash_paras = self._window_paragraphs_for_slice(slice_paras, chapters)
            input_hash = compute_window_input_hash(hash_paras)

            reused = by_hash.get(input_hash) or by_index.get(int(plan.window_index))
            if reused is not None:
                windows.append(reused)
                continue

            window = WholeBookRunWindow(
                run_id=run.id,
                window_index=int(plan.window_index),
                start_paragraph_id=plan.start_paragraph_id,
                end_paragraph_id=plan.end_paragraph_id,
                start_chapter_id=plan.start_chapter_id,
                end_chapter_id=plan.end_chapter_id,
                input_hash=input_hash,
                status=WindowStatus.PENDING.value,
                attempt_count=0,
                state_version_before=0,
                checkpoint_json=json.dumps(
                    {
                        "paragraph_ids": list(plan.paragraph_ids),
                        "snapshot_paragraph_ids": list(plan.snapshot_paragraph_ids),
                        "cross_chapter": plan.cross_chapter,
                        "character_count": plan.character_count,
                        "token_estimate": plan.token_estimate,
                    },
                    ensure_ascii=False,
                ),
            )
            self._session.add(window)
            windows.append(window)

        self._session.flush()
        run.progress_total = max(len(windows), 1)
        run.progress_current = sum(
            1 for w in windows if w.status == WindowStatus.COMPLETED.value
        )
        stage.checkpoint_json = json.dumps(
            {
                "window_count": len(windows),
                "window_indexes": [w.window_index for w in windows],
                "paragraph_count": len(snap_paragraphs),
            },
            ensure_ascii=False,
        )
        return windows

    def _stage_extract_windows(
        self, run: AnalysisRun, stage: AnalysisRunStage
    ) -> list[WholeBookOverviewWindowResultV1]:
        windows = self._list_windows(int(run.id))
        if not windows:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.WINDOW_BUILD_FAILED.value,
                "no windows to extract",
                run_id=str(run.id),
                stage_key=stage.stage_key,
            )
        # Make extract stage RUNNING visible before the first Provider wait.
        self._session.flush()
        self._checkpoint_commit()
        total_windows = len(windows)
        results: list[WholeBookOverviewWindowResultV1] = []

        for window in windows:
            if window.status == WindowStatus.COMPLETED.value:
                loaded = self._load_window_result(window)
                if loaded is not None:
                    results.append(loaded)
                continue

            if window.status == WindowStatus.RUNNING.value:
                validate_window_transition(window.status, WindowStatus.FAILED)
                window.status = WindowStatus.FAILED.value
                self._session.flush()

            if window.status not in {WindowStatus.PENDING.value, WindowStatus.FAILED.value}:
                continue

            validate_window_transition(window.status, WindowStatus.RUNNING)
            window.status = WindowStatus.RUNNING.value
            window.attempt_count = int(window.attempt_count or 0) + 1
            window.started_at = utc_now()
            window.error_code = None
            window.error_detail = None
            self._session.flush()
            # Release SQLite write lock before Provider/Fake wait.
            self._checkpoint_commit()

            prior_state = self._latest_prior_state(
                int(run.id), before_window_index=int(window.window_index)
            )
            window_input = self._build_window_input(
                run,
                window,
                prior_state=prior_state,
                total_windows=total_windows,
            )
            prompt = f"overview-window:{window.window_index}:{window.input_hash}"

            try:
                result = self._require_adapter().analyze_window(
                    window_input, transport=self._transport
                )
                result = WholeBookOverviewWindowResultV1.model_validate(result.model_dump())
            except NativeOverviewError as exc:
                if self._commit_progress:
                    try:
                        self._session.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                    window = self._session.get(WholeBookRunWindow, int(window.id)) or window
                    run = self._session.get(AnalysisRun, int(run.id)) or run
                validate_window_transition(window.status, WindowStatus.FAILED)
                window.status = WindowStatus.FAILED.value
                window.error_code = exc.code
                window.error_detail = exc.message
                window.completed_at = utc_now()
                self._record_attempt_safe(
                    run, window, prompt=prompt, status="failed", error_message=exc.message
                )
                self._session.flush()
                self._checkpoint_commit()
                raise
            except Exception as exc:  # noqa: BLE001
                wrapped = map_engine_exception(
                    exc,
                    run_id=str(run.id),
                    stage_key=stage.stage_key,
                    window_index=window.window_index,
                )
                if self._commit_progress:
                    try:
                        self._session.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                    window = self._session.get(WholeBookRunWindow, int(window.id)) or window
                    run = self._session.get(AnalysisRun, int(run.id)) or run
                validate_window_transition(window.status, WindowStatus.FAILED)
                window.status = WindowStatus.FAILED.value
                window.error_code = wrapped.code
                window.error_detail = wrapped.message
                window.completed_at = utc_now()
                self._record_attempt_safe(
                    run, window, prompt=prompt, status="failed", error_message=wrapped.message
                )
                self._session.flush()
                self._checkpoint_commit()
                raise wrapped from exc

            validate_window_transition(window.status, WindowStatus.COMPLETED)
            window.status = WindowStatus.COMPLETED.value
            window.completed_at = utc_now()
            checkpoint = json.loads(window.checkpoint_json or "{}")
            checkpoint["window_result"] = result.model_dump(mode="json")
            checkpoint["state_delta"] = result.state_delta.model_dump(mode="json")
            checkpoint["candidate_entity_count"] = len(result.candidate_entities)
            checkpoint["candidate_asset_count"] = len(result.candidate_assets)
            checkpoint["candidate_evidence_count"] = len(result.candidate_evidence)
            window.checkpoint_json = json.dumps(checkpoint, ensure_ascii=False)
            self._record_attempt_safe(run, window, prompt=prompt, status="succeeded")
            self._session.flush()
            results.append(result)
            # Refresh window list statuses for progress (same objects mutated above).
            run.progress_current = sum(
                1 for w in windows if w.status == WindowStatus.COMPLETED.value
            )
            run.progress_total = max(total_windows, 1)
            self._session.flush()
            self._checkpoint_commit()

        stage.checkpoint_json = json.dumps(
            {
                "windows_completed": sum(
                    1 for w in windows if w.status == WindowStatus.COMPLETED.value
                ),
                "windows_total": total_windows,
            },
            ensure_ascii=False,
        )
        self._session.flush()
        return results

    def _stage_materialize_windows(
        self, run: AnalysisRun, stage: AnalysisRunStage
    ) -> dict[str, Any]:
        windows = self._list_windows(int(run.id))
        entity_map: dict[str, int] = {}
        asset_version_map: dict[str, int] = {}
        evidence_rows: list[dict[str, Any]] = []
        window_results: list[WholeBookOverviewWindowResultV1] = []
        stats_acc: dict[str, int] = {
            "created_entities": 0,
            "reused_entities": 0,
            "created_assets": 0,
            "reused_assets": 0,
            "created_evidence": 0,
            "reused_evidence": 0,
        }

        for window in windows:
            if window.status != WindowStatus.COMPLETED.value:
                continue
            result = self._load_window_result(window)
            if result is None:
                raise NativeOverviewError(
                    WholeBookOverviewErrorCode.MATERIALIZATION_FAILED.value,
                    f"missing window_result checkpoint for window {window.window_index}",
                    run_id=str(run.id),
                    window_index=window.window_index,
                )
            window_results.append(result)

            if window.state_version_after is not None:
                state = self._session.scalar(
                    select(WholeBookRunStateVersion).where(
                        WholeBookRunStateVersion.run_id == run.id,
                        WholeBookRunStateVersion.version_number == int(window.state_version_after),
                    )
                )
                if state is not None:
                    payload = json.loads(state.state_json or "{}")
                    entity_map.update(
                        {str(k): int(v) for k, v in (payload.get("entities") or {}).items()}
                    )
                    asset_version_map.update(
                        {str(k): int(v) for k, v in (payload.get("assets") or {}).items()}
                    )
                continue

            prior = self._materializer.load_prior_state(int(run.id))
            window.state_version_before = int(prior.state_version)
            try:
                mat = self._materializer.materialize_window(
                    run, window, result, prior_state=prior
                )
            except NativeOverviewError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise NativeOverviewError(
                    WholeBookOverviewErrorCode.MATERIALIZATION_FAILED.value,
                    run_id=str(run.id),
                    stage_key=stage.stage_key,
                    window_index=window.window_index,
                    details={"cause": type(exc).__name__},
                ) from exc

            entity_map.update(mat["entity_map"])
            asset_version_map.update(mat["asset_version_map"])
            evidence_rows.extend(mat["evidence_rows"])
            for key, value in (mat.get("stats") or {}).items():
                if key in stats_acc:
                    stats_acc[key] += int(value)

        aggregate = {
            "window_results": window_results,
            "evidence_rows": evidence_rows,
            "entity_map": entity_map,
            "asset_version_map": asset_version_map,
            "stats": stats_acc,
        }
        stage.checkpoint_json = json.dumps(
            {
                "entity_count": len(entity_map),
                "asset_count": len(asset_version_map),
                "evidence_count": len(evidence_rows),
                "windows_materialized": len(window_results),
                "entity_map": entity_map,
                "asset_version_map": asset_version_map,
                "evidence_rows": evidence_rows,
                "window_results": [r.model_dump(mode="json") for r in window_results],
                "stats": stats_acc,
            },
            ensure_ascii=False,
        )
        self._session.flush()
        return aggregate

    def _stage_projection(
        self,
        run: AnalysisRun,
        stage: AnalysisRunStage,
        materialization: dict[str, Any],
    ) -> AnalysisArtifact:
        window_results: list[WholeBookOverviewWindowResultV1] = list(
            materialization.get("window_results") or []
        )
        if not window_results:
            for window in self._list_windows(int(run.id)):
                loaded = self._load_window_result(window)
                if loaded is not None:
                    window_results.append(loaded)
        evidence_rows: list[dict[str, Any]] = list(materialization.get("evidence_rows") or [])

        entities: list[dict[str, Any]] = []
        assets: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        selected_evidence = []
        seen_evidence: set[str] = set()
        for wr in window_results:
            entities.extend(e.model_dump(mode="json") for e in wr.candidate_entities)
            assets.extend(a.model_dump(mode="json") for a in wr.candidate_assets)
            for ev in wr.candidate_evidence:
                evidence.append(ev.model_dump(mode="json"))
                if ev.evidence_id not in seen_evidence:
                    seen_evidence.add(ev.evidence_id)
                    selected_evidence.append(ev)

        final_state = self._materializer.load_prior_state(int(run.id))
        if final_state.state_version == 0 and window_results:
            prior = empty_prior_state()
            for wr in window_results:
                prior = merge_prior_with_delta(prior, wr.state_delta)
            final_state = prior

        synthesis_input = WholeBookOverviewSynthesisInputV1(
            contract_version=CONTRACT_VERSION,
            run_id=str(run.id),
            book_id=str(run.book_id),
            snapshot_id=str(run.book_snapshot_id),
            engine_version=self._engine_version_label(),
            prompt_version=self._prompt_version_label(),
            entities=entities,
            assets=assets,
            evidence=evidence,
            final_state=final_state,
            snapshot_meta={"snapshot_id": run.book_snapshot_id},
            selected_evidence=selected_evidence,
        )
        try:
            projection = self._require_adapter().synthesize_overview(
                synthesis_input, transport=self._transport
            )
            projection = WholeBookOverviewProjectionCandidateV1.model_validate(
                projection.model_dump()
            )
        except NativeOverviewError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise map_engine_exception(
                exc, run_id=str(run.id), stage_key=stage.stage_key
            ) from exc

        overview_body = OverviewBodyDTO(
            novel_type=projection.novel_type,
            narrative_features=projection.narrative_features,
            core_setting=projection.core_setting,
            protagonist=projection.protagonist,
            protagonist_core_goal=projection.protagonist_core_goal,
            primary_conflict=projection.primary_conflict,
            central_question=projection.central_question,
            key_turning_points=projection.key_turning_points,
            climax=projection.climax,
            resolved_problem=projection.resolved_problem,
            ending_state=projection.ending_state,
            logline=projection.logline,
            synopsis=projection.synopsis,
        )

        windows = self._list_windows(int(run.id))
        windows_total = len(windows)
        windows_completed = sum(1 for w in windows if w.status == WindowStatus.COMPLETED.value)
        para_total = int(
            self._session.scalar(
                select(func.count())
                .select_from(BookSnapshotParagraph)
                .where(BookSnapshotParagraph.snapshot_id == int(run.book_snapshot_id))
            )
            or 0
        )
        covered_ids: set[str] = set()
        for window in windows:
            if window.status != WindowStatus.COMPLETED.value:
                continue
            checkpoint = json.loads(window.checkpoint_json or "{}")
            covered_ids.update(str(pid) for pid in (checkpoint.get("paragraph_ids") or []))
        covered_count = len(covered_ids) if covered_ids else (
            para_total if windows_completed == windows_total and windows_total else 0
        )
        all_done = windows_total > 0 and windows_completed == windows_total
        coverage = CoverageDTO(
            original_paragraphs_total=para_total,
            original_paragraphs_covered=para_total if all_done else covered_count,
            original_coverage_percent=100.0
            if all_done and para_total
            else (round(covered_count / para_total * 100.0, 6) if para_total else 0.0),
            windows_total=windows_total,
            windows_completed=windows_completed,
            evidence_count=len(evidence_rows) or len(seen_evidence),
        )

        evidence_index = self._build_evidence_index(run, evidence_rows)
        if not evidence_index and selected_evidence:
            evidence_index = self._build_evidence_index_from_candidates(run, selected_evidence)

        generated_at = utc_now()
        payload = {
            "overview": overview_body.model_dump(mode="json"),
            "coverage": coverage.model_dump(mode="json"),
            "evidence_index": [e.model_dump(mode="json") for e in evidence_index],
            "warnings": list(projection.warnings)
            or (
                [FIXTURE_DEVELOPMENT_WARNING]
                if self._engine_id == FIXTURE_ENGINE_ID
                else []
            ),
            "engine_id": self._engine_provider_name(),
            "engine_version": self._engine_version_label(),
            "prompt_version": self._prompt_version_label(),
            "generated_at": generated_at.isoformat(),
            "contract_version": CONTRACT_VERSION,
        }
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type=OVERVIEW_PROJECTION_ARTIFACT_TYPE,
            subject_type="book",
            subject_id=str(run.book_id),
            schema_version=CONTRACT_VERSION,
            prompt_version=self._prompt_version_label(),
            payload_json=json.dumps(payload, ensure_ascii=False),
            confidence=0.85,
            validation_status="valid",
        )
        self._session.add(artifact)
        self._session.flush()
        stage.output_artifact_id = artifact.id
        stage.checkpoint_json = json.dumps({"artifact_id": artifact.id}, ensure_ascii=False)
        return artifact

    def _stage_finalize(self, run: AnalysisRun, stage: AnalysisRunStage) -> None:
        windows = self._list_windows(int(run.id))
        stage.checkpoint_json = json.dumps(
            {
                "engine_id": self._engine_provider_name(),
                "engine_version": self._engine_version_label(),
                "prompt_version": self._prompt_version_label(),
                "fixture": self._engine_id == FIXTURE_ENGINE_ID,
                "walking_skeleton": self._engine_id == FIXTURE_ENGINE_ID,
                "production_ready": self._engine_id == PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
                "windows_total": len(windows),
            },
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_control_action(
        self, run_id: int, action: str, client_request_id: str
    ) -> dict[str, Any] | None:
        """Idempotent retry/resume lookup keyed by client_request_id (no schema change)."""

        stage = self._session.scalar(
            select(AnalysisRunStage).where(
                AnalysisRunStage.run_id == int(run_id),
                AnalysisRunStage.stage_key
                == OverviewProductionStageKey.SNAPSHOT_PREFLIGHT.value,
            )
        )
        if stage is None:
            return None
        try:
            data = json.loads(stage.checkpoint_json or "{}")
        except json.JSONDecodeError:
            return None
        actions = data.get("control_actions") or {}
        entry = actions.get(f"{action}:{client_request_id}")
        return entry if isinstance(entry, dict) else None

    def _remember_control_action(
        self, run: AnalysisRun, action: str, client_request_id: str
    ) -> None:
        stage = self._session.scalar(
            select(AnalysisRunStage).where(
                AnalysisRunStage.run_id == run.id,
                AnalysisRunStage.stage_key
                == OverviewProductionStageKey.SNAPSHOT_PREFLIGHT.value,
            )
        )
        if stage is None:
            return
        try:
            data = json.loads(stage.checkpoint_json or "{}")
        except json.JSONDecodeError:
            data = {}
        actions = dict(data.get("control_actions") or {})
        actions[f"{action}:{client_request_id}"] = {
            "status": run.status,
            "recorded_at": utc_now().isoformat(),
        }
        data["control_actions"] = actions
        stage.checkpoint_json = json.dumps(data, ensure_ascii=False)
        self._session.flush()

    def _list_windows(self, run_id: int) -> list[WholeBookRunWindow]:
        return list(
            self._session.scalars(
                select(WholeBookRunWindow)
                .where(WholeBookRunWindow.run_id == int(run_id))
                .order_by(WholeBookRunWindow.window_index)
            )
        )

    def _load_window_result(
        self, window: WholeBookRunWindow
    ) -> WholeBookOverviewWindowResultV1 | None:
        checkpoint = json.loads(window.checkpoint_json or "{}")
        raw = checkpoint.get("window_result")
        if not isinstance(raw, dict):
            return None
        return WholeBookOverviewWindowResultV1.model_validate(raw)

    def _latest_prior_state(
        self, run_id: int, *, before_window_index: int | None = None
    ) -> PriorStateV1:
        """Prefer materialized state; else chain state_delta from completed window checkpoints."""

        if before_window_index is None or before_window_index > 0:
            row = self._session.scalar(
                select(WholeBookRunStateVersion)
                .where(WholeBookRunStateVersion.run_id == int(run_id))
                .order_by(WholeBookRunStateVersion.version_number.desc())
            )
            if row is not None:
                after_idx = int(row.after_window_index or -1)
                if before_window_index is None or after_idx < int(before_window_index):
                    payload = json.loads(row.state_json or "{}")
                    prior_raw = payload.get("prior_state")
                    if isinstance(prior_raw, dict):
                        return PriorStateV1.model_validate(prior_raw)
                    return PriorStateV1(state_version=int(row.version_number or 0))

        prior = empty_prior_state()
        for window in self._list_windows(run_id):
            if before_window_index is not None and int(window.window_index) >= int(
                before_window_index
            ):
                break
            if window.status != WindowStatus.COMPLETED.value:
                continue
            checkpoint = json.loads(window.checkpoint_json or "{}")
            delta_raw = checkpoint.get("state_delta")
            if isinstance(delta_raw, dict):
                delta = StateDeltaV1.model_validate(delta_raw)
            else:
                result = self._load_window_result(window)
                if result is None:
                    continue
                delta = result.state_delta
            prior = merge_prior_with_delta(prior, delta)

        # Pre-materialize extract chaining: prior for window k uses state_version = k.
        if before_window_index is not None:
            return PriorStateV1.model_validate(
                {
                    **prior.model_dump(mode="json"),
                    "state_version": int(before_window_index),
                }
            )
        return prior

    def _aggregate_materialization(self, run: AnalysisRun) -> dict[str, Any]:
        stage = self._session.scalar(
            select(AnalysisRunStage).where(
                AnalysisRunStage.run_id == run.id,
                AnalysisRunStage.stage_key
                == OverviewProductionStageKey.MATERIALIZE_ASSETS.value,
            )
        )
        if stage is not None and stage.checkpoint_json:
            data = json.loads(stage.checkpoint_json or "{}")
            if data.get("window_results") is not None or data.get("entity_map") is not None:
                window_results = [
                    WholeBookOverviewWindowResultV1.model_validate(row)
                    for row in (data.get("window_results") or [])
                ]
                if not window_results:
                    for window in self._list_windows(int(run.id)):
                        loaded = self._load_window_result(window)
                        if loaded is not None:
                            window_results.append(loaded)
                return {
                    "window_results": window_results,
                    "evidence_rows": list(data.get("evidence_rows") or []),
                    "entity_map": dict(data.get("entity_map") or {}),
                    "asset_version_map": dict(data.get("asset_version_map") or {}),
                    "stats": dict(data.get("stats") or {}),
                }

        window_results: list[WholeBookOverviewWindowResultV1] = []
        entity_map: dict[str, int] = {}
        asset_version_map: dict[str, int] = {}
        for window in self._list_windows(int(run.id)):
            loaded = self._load_window_result(window)
            if loaded is not None:
                window_results.append(loaded)
            if window.state_version_after is None:
                continue
            state = self._session.scalar(
                select(WholeBookRunStateVersion).where(
                    WholeBookRunStateVersion.run_id == run.id,
                    WholeBookRunStateVersion.version_number == int(window.state_version_after),
                )
            )
            if state is None:
                continue
            payload = json.loads(state.state_json or "{}")
            entity_map.update({str(k): int(v) for k, v in (payload.get("entities") or {}).items()})
            asset_version_map.update(
                {str(k): int(v) for k, v in (payload.get("assets") or {}).items()}
            )
        return {
            "window_results": window_results,
            "evidence_rows": [],
            "entity_map": entity_map,
            "asset_version_map": asset_version_map,
            "stats": {},
        }

    def _build_window_input(
        self,
        run: AnalysisRun,
        window: WholeBookRunWindow,
        *,
        prior_state: PriorStateV1,
        total_windows: int,
    ) -> WholeBookOverviewWindowInputV1:
        assert run.book_snapshot_id is not None
        checkpoint = json.loads(window.checkpoint_json or "{}")
        snap_ids = [int(x) for x in (checkpoint.get("snapshot_paragraph_ids") or [])]
        if not snap_ids:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.WINDOW_BUILD_FAILED.value,
                "window checkpoint missing snapshot_paragraph_ids",
                run_id=str(run.id),
                window_index=window.window_index,
            )

        snap_paragraphs = list(
            self._session.scalars(
                select(BookSnapshotParagraph).where(BookSnapshotParagraph.id.in_(snap_ids))
            )
        )
        order_map = {pid: i for i, pid in enumerate(snap_ids)}
        snap_paragraphs.sort(key=lambda p: order_map.get(int(p.id), 0))

        chapters = {
            c.id: c
            for c in self._session.scalars(
                select(BookSnapshotChapter).where(
                    BookSnapshotChapter.snapshot_id == int(run.book_snapshot_id)
                )
            )
        }
        chapter_refs: list[ChapterRef] = []
        seen_chapters: set[int] = set()
        paras: list[WindowParagraph] = []
        for p in snap_paragraphs:
            ch = chapters.get(p.snapshot_chapter_id)
            chapter_id = str(
                ch.source_chapter_id if ch and ch.source_chapter_id else p.snapshot_chapter_id
            )
            if p.snapshot_chapter_id not in seen_chapters:
                seen_chapters.add(p.snapshot_chapter_id)
                chapter_refs.append(
                    ChapterRef(
                        chapter_id=chapter_id,
                        chapter_index=int(ch.chapter_order if ch else 0),
                        title=str(ch.title if ch else ""),
                    )
                )
            text = self._snapshots.get_snapshot_paragraph_text(p.id)
            paras.append(
                WindowParagraph(
                    paragraph_id=p.stable_paragraph_id or p.source_paragraph_id or str(p.id),
                    chapter_id=chapter_id,
                    paragraph_index=int(p.paragraph_order),
                    text=text,
                )
            )
        if not paras:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.BOOK_CONTENT_EMPTY.value,
                run_id=str(run.id),
                window_index=window.window_index,
            )

        return WholeBookOverviewWindowInputV1(
            contract_version=CONTRACT_VERSION,
            run=OverviewRunRef(
                run_id=str(run.id),
                book_id=str(run.book_id),
                snapshot_id=str(run.book_snapshot_id),
                mode=WholeBookAnalysisMode.NATIVE,
                engine_version=self._engine_version_label(),
                prompt_version=self._prompt_version_label(),
            ),
            window=WindowSlice(
                window_id=f"w-{window.window_index}",
                window_index=int(window.window_index),
                total_windows=max(1, int(total_windows)),
                start_paragraph_id=window.start_paragraph_id,
                end_paragraph_id=window.end_paragraph_id,
                chapter_refs=chapter_refs,
                paragraphs=paras,
                input_hash=window.input_hash,
                status=WindowStatus(window.status) if window.status else WindowStatus.RUNNING,
            ),
            prior_state=prior_state,
        )

    def _to_snapshot_refs(
        self,
        paragraphs: list[BookSnapshotParagraph],
        chapters: dict[Any, BookSnapshotChapter],
    ) -> list[SnapshotParagraphRef]:
        refs: list[SnapshotParagraphRef] = []
        for p in paragraphs:
            ch = chapters.get(p.snapshot_chapter_id)
            chapter_id = str(
                ch.source_chapter_id if ch and ch.source_chapter_id else p.snapshot_chapter_id
            )
            text = self._snapshots.get_snapshot_paragraph_text(p.id)
            refs.append(
                SnapshotParagraphRef(
                    snapshot_paragraph_id=int(p.id),
                    paragraph_id=p.stable_paragraph_id or p.source_paragraph_id or str(p.id),
                    chapter_id=chapter_id,
                    source_chapter_id=(
                        int(ch.source_chapter_id)
                        if ch and ch.source_chapter_id is not None
                        else None
                    ),
                    paragraph_order=int(p.paragraph_order),
                    text=text,
                    content_hash=str(p.content_hash or ""),
                )
            )
        return refs

    def _window_paragraphs_for_slice(
        self,
        paragraphs: list[BookSnapshotParagraph],
        chapters: dict[Any, BookSnapshotChapter],
    ) -> list[WindowParagraph]:
        paras: list[WindowParagraph] = []
        for p in paragraphs:
            ch = chapters.get(p.snapshot_chapter_id)
            chapter_id = str(
                ch.source_chapter_id if ch and ch.source_chapter_id else p.snapshot_chapter_id
            )
            text = self._snapshots.get_snapshot_paragraph_text(p.id)
            paras.append(
                WindowParagraph(
                    paragraph_id=p.stable_paragraph_id or p.source_paragraph_id or str(p.id),
                    chapter_id=chapter_id,
                    paragraph_index=int(p.paragraph_order),
                    text=text,
                )
            )
        return paras

    def _record_attempt_safe(
        self,
        run: AnalysisRun,
        window: WholeBookRunWindow,
        *,
        prompt: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        if self._transport is None and status == "succeeded":
            return
        try:
            # Private engine always calls transport.request before parse/repair.
            # Mark invoked on BOTH success and failure so Live call_log is harvested
            # instead of synthesizing empty text / zero cost.
            already_invoked = (
                self._transport is not None
                and self._engine_id == PRIVATE_NATIVE_OVERVIEW_ENGINE_ID
            )
            invocation = self._accounting.record_window_attempt(
                run,
                window,
                transport=self._transport,
                prompt=prompt,
                status=status,
                error_message=error_message,
                transport_already_invoked=already_invoked,
            )
            if status != "succeeded" and invocation is not None:
                run.failed_invocation_id = int(invocation.id)
                self._session.flush()
        except Exception:  # noqa: BLE001
            pass

    def _build_evidence_index(
        self, run: AnalysisRun, evidence_rows: list[dict[str, Any]]
    ) -> list[EvidenceIndexEntry]:
        seen: set[str] = set()
        index: list[EvidenceIndexEntry] = []
        for row in evidence_rows:
            eid = str(row["evidence_id"])
            if eid in seen:
                continue
            seen.add(eid)
            chapter = None
            if row.get("source_paragraph_id"):
                para = self._session.get(Paragraph, row["source_paragraph_id"])
                if para is not None:
                    chapter = self._session.get(Chapter, para.chapter_id)
            index.append(
                EvidenceIndexEntry(
                    evidence_id=eid,
                    chapter_id=str(row.get("chapter_id") or ""),
                    paragraph_id=str(
                        row.get("stable_paragraph_id") or row.get("paragraph_id") or ""
                    ),
                    quote=str(row.get("quote") or ""),
                    evidence_role="support",
                    confidence=float(row.get("confidence") or 0),
                    snapshot_id=str(run.book_snapshot_id),
                    source_run_id=str(run.id),
                    deep_link=EvidenceDeepLink(
                        book_id=str(run.book_id),
                        chapter_id=str(row.get("chapter_id") or (chapter.id if chapter else "")),
                        chapter_index=int(chapter.chapter_index) if chapter else None,
                        paragraph_id=str(
                            row.get("source_paragraph_id")
                            or row.get("stable_paragraph_id")
                            or row.get("paragraph_id")
                            or ""
                        ),
                        paragraph_index=row.get("paragraph_index"),
                        content_hash=row.get("content_hash"),
                        integrity_status="ok",
                    ),
                )
            )
        return index

    def _build_evidence_index_from_candidates(
        self, run: AnalysisRun, candidates: list[Any]
    ) -> list[EvidenceIndexEntry]:
        index: list[EvidenceIndexEntry] = []
        seen: set[str] = set()
        for cand in candidates:
            eid = str(cand.evidence_id)
            if eid in seen:
                continue
            seen.add(eid)
            index.append(
                EvidenceIndexEntry(
                    evidence_id=eid,
                    chapter_id=str(cand.chapter_id),
                    paragraph_id=str(cand.paragraph_id),
                    quote=str(cand.quote),
                    evidence_role=str(cand.evidence_role or "support"),
                    confidence=float(cand.confidence or 0),
                    snapshot_id=str(run.book_snapshot_id),
                    source_run_id=str(run.id),
                    deep_link=EvidenceDeepLink(
                        book_id=str(run.book_id),
                        chapter_id=str(cand.chapter_id),
                        paragraph_id=str(cand.paragraph_id),
                        integrity_status="ok",
                    ),
                )
            )
        return index

    def _run_stage(self, run: AnalysisRun, key: OverviewProductionStageKey, fn):  # noqa: ANN001
        stage = self._session.scalar(
            select(AnalysisRunStage).where(
                AnalysisRunStage.run_id == run.id,
                AnalysisRunStage.stage_key == key.value,
            )
        )
        if stage is None:
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.DATABASE_WRITE_FAILED.value,
                f"missing stage {key.value}",
                run_id=str(run.id),
            )
        if stage.status == StageStatus.COMPLETED.value:
            return None

        if stage.status == StageStatus.RUNNING.value:
            validate_overview_stage_transition(stage.status, StageStatus.FAILED)
            stage.status = StageStatus.FAILED.value
            stage.completed_at = utc_now()
            self._session.flush()

        validate_overview_stage_transition(stage.status, StageStatus.RUNNING)
        stage.status = StageStatus.RUNNING.value
        stage.attempt_count = int(stage.attempt_count or 0) + 1
        stage.started_at = utc_now()
        stage.error_code = None
        stage.error_message = None
        self._session.flush()
        try:
            result = fn(run, stage)
            validate_overview_stage_transition(stage.status, StageStatus.COMPLETED)
            stage.status = StageStatus.COMPLETED.value
            stage.completed_at = utc_now()
            self._session.flush()
            return result
        except Exception:
            validate_overview_stage_transition(stage.status, StageStatus.FAILED)
            stage.status = StageStatus.FAILED.value
            stage.completed_at = utc_now()
            self._session.flush()
            raise

    def _transition_run(self, run: AnalysisRun, target: RunStatus) -> None:
        if run.status == target.value:
            return
        validate_overview_run_transition(run.status, target)
        run.status = target.value
        self._session.flush()

    def _fail_run_with_progress(self, run: AnalysisRun, exc: NativeOverviewError) -> None:
        """Persist failure; when commit_progress is on, use a short committed txn."""

        if not self._commit_progress:
            self._fail_run(run, exc)
            return
        # Drop any partial uncommitted work, then write a durable failure snapshot.
        try:
            self._session.rollback()
        except Exception:  # noqa: BLE001
            pass
        run = self._session.get(AnalysisRun, int(run.id)) or run
        self._fail_run(run, exc)
        self._session.commit()

    def _fail_run(self, run: AnalysisRun, exc: NativeOverviewError) -> None:
        try:
            if run.status not in {
                RunStatus.FAILED.value,
                RunStatus.COMPLETED.value,
                RunStatus.CANCELLED.value,
            }:
                validate_overview_run_transition(run.status, RunStatus.FAILED)
                run.status = RunStatus.FAILED.value
        except ValueError:
            run.status = RunStatus.FAILED.value
        run.error_code = exc.code
        # Keep technical detail for developers; surface Chinese UX copy to Task Center.
        technical = exc.message
        try:
            meta = WHOLE_BOOK_OVERVIEW_ERROR_META[WholeBookOverviewErrorCode(exc.code)]
            run.error_message = meta["user_message"]
            run.user_action_hint = meta["user_message"]
        except ValueError:
            run.error_message = technical
        run.root_error_code = exc.code
        run.root_error_message = technical
        if exc.stage_key:
            run.failed_stage = exc.stage_key
        run.retryable = True
        run.completed_at = utc_now()
        stage = self._session.scalar(
            select(AnalysisRunStage).where(
                AnalysisRunStage.run_id == run.id,
                AnalysisRunStage.status == StageStatus.RUNNING.value,
            )
        )
        if stage is not None:
            stage.status = StageStatus.FAILED.value
            stage.error_code = exc.code
            stage.error_message = technical
            stage.completed_at = utc_now()
            if not run.failed_stage:
                run.failed_stage = stage.stage_key
        self._session.flush()

    def _remember_control_action(
        self, run: AnalysisRun, action: str, client_request_id: str
    ) -> None:
        payload = {
            "action": action,
            "client_request_id": client_request_id,
            "status": run.status,
            "run_id": run.id,
        }
        self._session.add(
            AnalysisArtifact(
                run_id=run.id,
                artifact_type=CONTROL_ARTIFACT_TYPE,
                subject_type="book",
                subject_id=str(run.book_id),
                schema_version=CONTRACT_VERSION,
                prompt_version=self._prompt_version_label(),
                payload_json=json.dumps(payload, ensure_ascii=False),
                confidence=1.0,
                validation_status="valid",
            )
        )
        self._session.flush()

    def _find_control_action(
        self, run_id: int, action: str, client_request_id: str
    ) -> AnalysisArtifact | None:
        rows = list(
            self._session.scalars(
                select(AnalysisArtifact).where(
                    AnalysisArtifact.run_id == int(run_id),
                    AnalysisArtifact.artifact_type == CONTROL_ARTIFACT_TYPE,
                )
            )
        )
        for row in rows:
            try:
                payload = json.loads(row.payload_json or "{}")
            except json.JSONDecodeError:
                continue
            if (
                payload.get("action") == action
                and payload.get("client_request_id") == client_request_id
            ):
                return row
        return None

    def _retry_landing_status(self, run: AnalysisRun) -> RunStatus:
        for key in OVERVIEW_PRODUCTION_STAGE_ORDER:
            stage = self._session.scalar(
                select(AnalysisRunStage).where(
                    AnalysisRunStage.run_id == run.id,
                    AnalysisRunStage.stage_key == key.value,
                )
            )
            if stage is None:
                continue
            if stage.status != StageStatus.COMPLETED.value:
                if key in _PREPARING_STAGE_KEYS:
                    return RunStatus.PREPARING
                return RunStatus.ANALYZING
        return RunStatus.ANALYZING

    def _clear_failed_stage_errors(self, run: AnalysisRun) -> None:
        stages = list(
            self._session.scalars(
                select(AnalysisRunStage).where(AnalysisRunStage.run_id == run.id)
            )
        )
        for stage in stages:
            if stage.status == StageStatus.FAILED.value:
                stage.error_code = None
                stage.error_message = None

    def _find_by_client_request_id(self, book_id: int, client_request_id: str) -> AnalysisRun | None:
        return self._session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.book_id == int(book_id),
                AnalysisRun.client_request_id == client_request_id,
                AnalysisRun.analysis_type == AnalysisType.WHOLE_BOOK_NATIVE.value,
                AnalysisRun.task_type == "whole_book_overview",
            )
        )

    def _require_overview_run(self, run_id: int) -> AnalysisRun:
        run = self._session.get(AnalysisRun, int(run_id))
        if run is None or run.task_type != "whole_book_overview":
            raise NativeOverviewError(WholeBookOverviewErrorCode.RUN_NOT_FOUND.value)
        return run

    def _current_stage_key(self, run: AnalysisRun) -> OverviewProductionStageKey | None:
        stages = list(
            self._session.scalars(
                select(AnalysisRunStage)
                .where(AnalysisRunStage.run_id == run.id)
                .order_by(AnalysisRunStage.stage_order)
            )
        )
        for stage in stages:
            if stage.status == StageStatus.RUNNING.value:
                return OverviewProductionStageKey(stage.stage_key)
        for stage in reversed(stages):
            if stage.status == StageStatus.COMPLETED.value:
                return OverviewProductionStageKey(stage.stage_key)
        for stage in stages:
            if stage.status == StageStatus.FAILED.value:
                return OverviewProductionStageKey(stage.stage_key)
        return OverviewProductionStageKey.SNAPSHOT_PREFLIGHT if stages else None

    @staticmethod
    def _current_window_index(windows: list[WholeBookRunWindow]) -> int | None:
        if not windows:
            return None
        for window in windows:
            if window.status == WindowStatus.RUNNING.value:
                return int(window.window_index)
        for window in windows:
            if window.status in {WindowStatus.PENDING.value, WindowStatus.FAILED.value}:
                return int(window.window_index)
        return int(windows[-1].window_index)

    def _to_create_response(self, run: AnalysisRun) -> CreateRunResponse:
        windows = self._list_windows(int(run.id))
        completed = sum(1 for w in windows if w.status == WindowStatus.COMPLETED.value)
        total = max(len(windows), 1)
        return CreateRunResponse(
            run_id=str(run.id),
            book_id=str(run.book_id),
            snapshot_id=str(run.book_snapshot_id),
            mode=WholeBookAnalysisMode.NATIVE,
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            status=RunStatus(run.status),
            current_stage=self._current_stage_key(run),
            progress=ProgressDTO(
                completed_windows=completed,
                total_windows=total,
                percent=100.0
                if run.status == RunStatus.COMPLETED.value
                else ((completed / total * 100.0) if total else 0.0),
                current_window_index=self._current_window_index(windows),
            ),
            created_at=run.created_at,
        )

    def _to_retry_resume_response(
        self, run: AnalysisRun, *, message: str
    ) -> RetryResumeRunResponse:
        windows = self._list_windows(int(run.id))
        completed = sum(1 for w in windows if w.status == WindowStatus.COMPLETED.value)
        total = len(windows)
        percent = (
            100.0
            if total and completed == total and run.status == RunStatus.COMPLETED.value
            else ((completed / total * 100.0) if total else 0.0)
        )
        can_resume = run.status == RunStatus.PAUSED.value
        can_retry = bool(run.retryable) and run.status == RunStatus.FAILED.value
        return RetryResumeRunResponse(
            run_id=str(run.id),
            book_id=str(run.book_id),
            snapshot_id=str(run.book_snapshot_id),
            status=RunStatus(run.status),
            current_stage=self._current_stage_key(run),
            progress=ProgressDTO(
                completed_windows=completed,
                total_windows=total,
                percent=percent,
                current_window_index=self._current_window_index(windows),
                failed_window_index=next(
                    (w.window_index for w in windows if w.status == WindowStatus.FAILED.value),
                    None,
                ),
            ),
            retryable=bool(run.retryable),
            actions=RunActionsDTO(can_retry=can_retry, can_resume=can_resume),
            message=message,
        )

    def _config_fingerprint(self) -> str:
        raw = (
            f"{self._engine_provider_name()}|"
            f"{self._engine_version_label()}|"
            f"{self._prompt_version_label()}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
