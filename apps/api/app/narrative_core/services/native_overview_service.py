"""Native Overview walking-skeleton orchestrator (STEP 2.2-A).

Service boundary only — routers stay thin. Fixture execution is gated by
``is_pro_native_overview_enabled()``; WHOLE_BOOK_RUNS_ENDPOINT_DISABLED stays True
for the legacy whole-book analysis create path.
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
    WALKING_SKELETON_USER_NOTICE,
    is_pro_native_overview_enabled,
)
from app.narrative_core.contracts.whole_book_overview_errors import (
    WHOLE_BOOK_OVERVIEW_ERROR_META,
    WholeBookOverviewErrorCode,
    overview_error_payload,
)
from app.narrative_core.contracts.whole_book_overview_state_machine import (
    OVERVIEW_PRODUCTION_STAGE_ORDER,
    validate_overview_run_transition,
    validate_overview_stage_transition,
    validate_window_transition,
)
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CONTRACT_VERSION,
    CoverageDTO,
    CreateRunRequest,
    CreateRunResponse,
    EvidenceDeepLink,
    EvidenceIndexEntry,
    OverviewApiResponse,
    OverviewBodyDTO,
    OverviewBookSummary,
    OverviewRunSummary,
    OverviewSnapshotSummary,
    PreflightBlockingError,
    PreflightResponse,
    PriorStateV1,
    ProgressDTO,
    RunActionsDTO,
    RunStatusResponse,
    WholeBookOverviewProjectionCandidateV1,
    WholeBookOverviewSynthesisInputV1,
    WholeBookOverviewWindowInputV1,
    WholeBookOverviewWindowResultV1,
    OverviewRunRef,
    ChapterRef,
    WindowParagraph,
    WindowSlice,
)
from app.narrative_core.enums import (
    AnalysisType,
    OriginType,
    OverviewProductionStageKey,
    RunStatus,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WindowStatus,
)
from app.narrative_core.services.asset_evidence_service import NarrativeAssetEvidenceService
from app.narrative_core.services.asset_service import NarrativeAssetService
from app.narrative_core.services.entity_service import NarrativeEntityServiceImpl
from app.narrative_core.services.native_overview_fixture_adapter import (
    NativeOverviewFixtureAdapter,
    empty_prior_state,
    get_fixture_adapter,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.services import entitlement

OVERVIEW_PROJECTION_ARTIFACT_TYPE = "whole_book_overview_projection"
NATIVE_OVERVIEW_UNAVAILABLE_CODE = "PRO_NATIVE_OVERVIEW_UNAVAILABLE"


class NativeOverviewError(Exception):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
        stage_key: str | None = None,
        window_index: int | None = None,
    ) -> None:
        self.code = code
        self.details = details or {}
        self.run_id = run_id
        self.stage_key = stage_key
        self.window_index = window_index
        try:
            meta = WHOLE_BOOK_OVERVIEW_ERROR_META[WholeBookOverviewErrorCode(code)]
            self.http_status = http_status if http_status is not None else meta["http_status"]
            self.message = message or meta["user_message"]
            self.retryable = meta["retryable"]
        except ValueError:
            self.http_status = http_status if http_status is not None else 503
            self.message = message or "原生全书概览不可用。"
            self.retryable = False
        super().__init__(self.message)

    def as_envelope(self) -> dict[str, Any]:
        try:
            return overview_error_payload(
                self.code,
                message=self.message,
                details=self.details,
                run_id=self.run_id,
                stage_key=self.stage_key,
                window_index=self.window_index,
            )
        except ValueError:
            return {
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "retryable": self.retryable,
                    "details": self.details,
                    "run_id": self.run_id,
                    "stage_key": self.stage_key,
                    "window_index": self.window_index,
                }
            }


def require_native_overview_enabled() -> None:
    if not is_pro_native_overview_enabled():
        raise NativeOverviewError(
            NATIVE_OVERVIEW_UNAVAILABLE_CODE,
            "原生全书概览行走骨架未启用（PRO_NATIVE_OVERVIEW_ENABLED）。",
            http_status=503,
            details={"flag": "PRO_NATIVE_OVERVIEW_ENABLED", "enabled": False},
        )


def require_pro_license(session: Session) -> None:
    snap = entitlement.entitlement_snapshot(session)
    if not snap.get("pro_active"):
        raise NativeOverviewError(
            WholeBookOverviewErrorCode.PRO_LICENSE_REQUIRED.value,
            details={"edition": snap.get("edition")},
        )


class NativeOverviewService:
    """Orchestrates Snapshot → Window → Fixture Adapter → Materialize → Projection."""

    def __init__(
        self,
        session: Session,
        *,
        adapter: NativeOverviewFixtureAdapter | None = None,
    ) -> None:
        self._session = session
        self._adapter = adapter or get_fixture_adapter()
        self._snapshots = BookSnapshotServiceImpl(session)
        self._entities = NarrativeEntityServiceImpl(session)
        self._assets = NarrativeAssetService(session)
        self._evidence = NarrativeAssetEvidenceService(session)

    # ------------------------------------------------------------------
    # Preflight
    # ------------------------------------------------------------------

    def preflight(self, book_id: int) -> PreflightResponse:
        book = self._session.get(Book, int(book_id))
        license_allowed = bool(entitlement.entitlement_snapshot(self._session).get("pro_active"))
        flag_on = is_pro_native_overview_enabled()

        if book is None:
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
                warnings=[FIXTURE_DEVELOPMENT_WARNING, WALKING_SKELETON_USER_NOTICE],
                blocking_errors=[
                    PreflightBlockingError(
                        code=WholeBookOverviewErrorCode.BOOK_NOT_FOUND,
                        message="未找到指定书籍。",
                    )
                ],
                run_creation_enabled=False,
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
        warnings = [FIXTURE_DEVELOPMENT_WARNING, WALKING_SKELETON_USER_NOTICE]
        if not flag_on:
            blocking.append(
                PreflightBlockingError(
                    code=NATIVE_OVERVIEW_UNAVAILABLE_CODE,
                    message="原生全书概览行走骨架未启用。",
                )
            )
            warnings.append("Feature flag PRO_NATIVE_OVERVIEW_ENABLED is off.")
        if not license_allowed:
            blocking.append(
                PreflightBlockingError(
                    code=WholeBookOverviewErrorCode.PRO_LICENSE_REQUIRED,
                    message="需要有效的 StoryLens Pro 授权才能创建原生全书概览。",
                )
            )
        if paragraph_count <= 0 or character_count <= 0:
            blocking.append(
                PreflightBlockingError(
                    code=WholeBookOverviewErrorCode.BOOK_CONTENT_EMPTY,
                    message="书籍没有可用于分析的正文段落。",
                )
            )

        run_enabled = flag_on and license_allowed and paragraph_count > 0 and not blocking
        # When only flag/license/content errors exist, still disable create.
        run_enabled = bool(flag_on and license_allowed and paragraph_count > 0 and character_count > 0)
        if blocking:
            run_enabled = False

        return PreflightResponse(
            book_id=str(book.id),
            chapter_count=chapter_count,
            paragraph_count=paragraph_count,
            character_count=character_count,
            snapshot_required=True,
            provider_configured=False,
            license_allowed=license_allowed,
            mode=WholeBookAnalysisMode.NATIVE,
            estimated_windows=1 if paragraph_count > 0 else 0,
            estimated_tokens=0,
            estimated_cost=0.0,
            currency="CNY",
            warnings=warnings,
            blocking_errors=blocking,
            run_creation_enabled=run_enabled,
        )

    # ------------------------------------------------------------------
    # Create + execute
    # ------------------------------------------------------------------

    def create_run(self, book_id: int, request: CreateRunRequest) -> CreateRunResponse:
        require_native_overview_enabled()
        require_pro_license(self._session)

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
            provider=FIXTURE_ENGINE_ID,
            model=FIXTURE_ENGINE_VERSION,
            prompt_version=FIXTURE_PROMPT_VERSION,
            schema_version=CONTRACT_VERSION,
            input_hash=snapshot.content_hash or "",
            prompt_hash=FIXTURE_PROMPT_VERSION,
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

        # Execute synchronously for STEP 2.2 walking skeleton.
        try:
            self.execute_run(int(run.id))
        except NativeOverviewError:
            # Persist failed run/stages before the request session may roll back.
            self._session.commit()
            raise
        self._session.commit()
        self._session.refresh(run)
        return self._to_create_response(run)

    def execute_run(self, run_id: int) -> AnalysisRun:
        run = self._session.get(AnalysisRun, int(run_id))
        if run is None:
            raise NativeOverviewError(WholeBookOverviewErrorCode.RUN_NOT_FOUND.value)

        try:
            self._transition_run(run, RunStatus.PREPARING)
            self._run_stage(run, OverviewProductionStageKey.SNAPSHOT_PREFLIGHT, self._stage_snapshot)
            self._transition_run(run, RunStatus.ANALYZING)
            window = self._run_stage(
                run, OverviewProductionStageKey.BUILD_CONTEXT_WINDOWS, self._stage_build_window
            )
            window_result = self._run_stage(
                run,
                OverviewProductionStageKey.EXTRACT_OVERVIEW_FACTS,
                lambda r, s: self._stage_extract(r, s, window),
            )
            self._transition_run(run, RunStatus.MATERIALIZING)
            materialization = self._run_stage(
                run,
                OverviewProductionStageKey.MATERIALIZE_ASSETS,
                lambda r, s: self._stage_materialize(r, s, window_result),
            )
            self._transition_run(run, RunStatus.SYNTHESIZING)
            self._run_stage(
                run,
                OverviewProductionStageKey.GENERATE_OVERVIEW_PROJECTION,
                lambda r, s: self._stage_projection(r, s, materialization),
            )
            self._run_stage(run, OverviewProductionStageKey.FINALIZE, self._stage_finalize)
            self._transition_run(run, RunStatus.COMPLETED)
            run.completed_at = utc_now()
            run.progress_current = 1
            run.error_code = None
            run.error_message = None
            run.retryable = False
            self._session.flush()
            return run
        except NativeOverviewError as exc:
            self._fail_run(run, exc)
            raise
        except Exception as exc:  # noqa: BLE001
            wrapped = NativeOverviewError(
                WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value,
                f"Fixture adapter / execution failed: {exc}",
                details={"cause": type(exc).__name__},
                run_id=str(run.id),
            )
            self._fail_run(run, wrapped)
            raise wrapped from exc

    # ------------------------------------------------------------------
    # Read APIs
    # ------------------------------------------------------------------

    def get_run(self, run_id: int) -> RunStatusResponse:
        require_native_overview_enabled()
        run = self._require_overview_run(run_id)
        windows = list(
            self._session.scalars(
                select(WholeBookRunWindow)
                .where(WholeBookRunWindow.run_id == run.id)
                .order_by(WholeBookRunWindow.window_index)
            )
        )
        completed = sum(1 for w in windows if w.status == WindowStatus.COMPLETED.value)
        total = len(windows)
        percent = 100.0 if total and completed == total and run.status == RunStatus.COMPLETED.value else (
            (completed / total * 100.0) if total else 0.0
        )
        current_stage = self._current_stage_key(run)
        error_code = None
        if run.error_code:
            try:
                error_code = WholeBookOverviewErrorCode(run.error_code)
            except ValueError:
                error_code = None
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
                current_window_index=0 if windows else None,
                failed_window_index=next(
                    (w.window_index for w in windows if w.status == WindowStatus.FAILED.value),
                    None,
                ),
            ),
            estimated_tokens=0,
            actual_tokens=0,
            estimated_cost=0.0,
            actual_cost=0.0,
            provider=run.provider,
            model=run.model,
            error=run.error_message,
            error_code=error_code,
            retryable=bool(run.retryable),
            actions=RunActionsDTO(can_retry=bool(run.retryable), can_resume=False),
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

    def _stage_build_window(
        self, run: AnalysisRun, stage: AnalysisRunStage
    ) -> WholeBookRunWindow:
        assert run.book_snapshot_id is not None
        paragraphs = list(
            self._session.scalars(
                select(BookSnapshotParagraph)
                .where(BookSnapshotParagraph.snapshot_id == int(run.book_snapshot_id))
                .order_by(BookSnapshotParagraph.paragraph_order)
            )
        )
        if not paragraphs:
            raise NativeOverviewError(WholeBookOverviewErrorCode.BOOK_CONTENT_EMPTY.value)

        chapters = {
            c.id: c
            for c in self._session.scalars(
                select(BookSnapshotChapter).where(
                    BookSnapshotChapter.snapshot_id == int(run.book_snapshot_id)
                )
            )
        }
        first = paragraphs[0]
        last = paragraphs[-1]
        start_chapter = chapters.get(first.snapshot_chapter_id)
        end_chapter = chapters.get(last.snapshot_chapter_id)
        source_ids = [p.stable_paragraph_id or p.source_paragraph_id or str(p.id) for p in paragraphs]
        # Build temporary WindowParagraph list for hash (must match Private rule).
        from app.narrative_core.contracts.whole_book_overview_v1 import WindowParagraph as WP

        hash_paras: list[WP] = []
        for p in paragraphs:
            ch = chapters.get(p.snapshot_chapter_id)
            chapter_id = str(
                ch.source_chapter_id if ch and ch.source_chapter_id else p.snapshot_chapter_id
            )
            text = self._snapshots.get_snapshot_paragraph_text(p.id)
            hash_paras.append(
                WP(
                    paragraph_id=p.stable_paragraph_id or p.source_paragraph_id or str(p.id),
                    chapter_id=chapter_id,
                    paragraph_index=int(p.paragraph_order),
                    text=text,
                )
            )
        from app.narrative_core.services.native_overview_fixture_adapter import (
            compute_window_input_hash,
        )

        input_hash = compute_window_input_hash(hash_paras)

        window = WholeBookRunWindow(
            run_id=run.id,
            window_index=0,
            start_paragraph_id=source_ids[0],
            end_paragraph_id=source_ids[-1],
            start_chapter_id=start_chapter.source_chapter_id if start_chapter else None,
            end_chapter_id=end_chapter.source_chapter_id if end_chapter else None,
            input_hash=input_hash,
            status=WindowStatus.PENDING.value,
            attempt_count=0,
            state_version_before=0,
            checkpoint_json=json.dumps(
                {
                    "paragraph_ids": source_ids,
                    "snapshot_paragraph_ids": [p.id for p in paragraphs],
                    "cross_chapter": True,
                },
                ensure_ascii=False,
            ),
        )
        self._session.add(window)
        self._session.flush()
        stage.checkpoint_json = json.dumps(
            {"window_id": window.id, "window_index": 0, "paragraph_count": len(paragraphs)},
            ensure_ascii=False,
        )
        return window

    def _stage_extract(
        self,
        run: AnalysisRun,
        stage: AnalysisRunStage,
        window: WholeBookRunWindow,
    ) -> WholeBookOverviewWindowResultV1:
        validate_window_transition(window.status, WindowStatus.RUNNING)
        window.status = WindowStatus.RUNNING.value
        window.attempt_count = int(window.attempt_count or 0) + 1
        window.started_at = utc_now()
        self._session.flush()

        window_input = self._build_window_input(run, window)
        try:
            result = self._adapter.run_window(window_input)
            # Re-validate frozen contract shape
            result = WholeBookOverviewWindowResultV1.model_validate(result.model_dump())
        except Exception as exc:  # noqa: BLE001
            validate_window_transition(window.status, WindowStatus.FAILED)
            window.status = WindowStatus.FAILED.value
            window.error_code = WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value
            window.error_detail = str(exc)
            window.completed_at = utc_now()
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value,
                run_id=str(run.id),
                stage_key=stage.stage_key,
                window_index=window.window_index,
                details={"cause": type(exc).__name__},
            ) from exc

        validate_window_transition(window.status, WindowStatus.COMPLETED)
        window.status = WindowStatus.COMPLETED.value
        window.completed_at = utc_now()
        window.checkpoint_json = json.dumps(
            {
                **json.loads(window.checkpoint_json or "{}"),
                "candidate_entity_count": len(result.candidate_entities),
                "candidate_asset_count": len(result.candidate_assets),
                "candidate_evidence_count": len(result.candidate_evidence),
            },
            ensure_ascii=False,
        )
        stage.checkpoint_json = json.dumps(
            {"window_id": window.id, "input_hash": result.input_hash},
            ensure_ascii=False,
        )
        # Stash result for materialize via stage checkpoint (small fixture payload).
        stage.checkpoint_json = json.dumps(
            {
                "window_result": result.model_dump(mode="json"),
                "window_id": window.id,
            },
            ensure_ascii=False,
        )
        self._session.flush()
        return result

    def _stage_materialize(
        self,
        run: AnalysisRun,
        stage: AnalysisRunStage,
        window_result: WholeBookOverviewWindowResultV1,
    ) -> dict[str, Any]:
        assert run.book_id is not None and run.book_snapshot_id is not None
        snapshot_id = int(run.book_snapshot_id)
        book_id = int(run.book_id)

        para_by_stable = {
            (p.stable_paragraph_id or p.source_paragraph_id or ""): p
            for p in self._session.scalars(
                select(BookSnapshotParagraph).where(
                    BookSnapshotParagraph.snapshot_id == snapshot_id
                )
            )
        }
        # Also index by source_paragraph_id and numeric string id
        for p in list(para_by_stable.values()):
            if p.source_paragraph_id:
                para_by_stable[p.source_paragraph_id] = p
            para_by_stable[str(p.id)] = p

        evidence_by_id = {e.evidence_id: e for e in window_result.candidate_evidence}
        entity_map: dict[str, int] = {}
        asset_version_map: dict[str, int] = {}
        evidence_rows: list[dict[str, Any]] = []

        with self._session.begin_nested():
            for ent in window_result.candidate_entities:
                entity = self._entities.create_entity(
                    book_id,
                    entity_type=ent.entity_type,
                    canonical_name=ent.canonical_name,
                    created_by=FIXTURE_ENGINE_ID,
                )
                entity_map[ent.candidate_id] = int(entity.id)
                for alias in ent.aliases:
                    self._entities.add_alias_candidate(
                        entity.id,
                        alias_text=alias,
                        source_run_id=run.id,
                        source_snapshot_id=snapshot_id,
                    )

            for asset in window_result.candidate_assets:
                result = self._assets.create_candidate_asset(
                    book_id,
                    asset_type=asset.asset_type,
                    title=asset.title or asset.candidate_id,
                    summary=asset.summary,
                    run_id=run.id,
                    book_snapshot_id=snapshot_id,
                    identity_fingerprint=asset.deduplication_key or asset.candidate_id,
                    confidence=asset.confidence,
                    origin_type=OriginType.SYSTEM,
                    attributes_json=json.dumps(
                        {
                            "candidate_id": asset.candidate_id,
                            "engine_id": FIXTURE_ENGINE_ID,
                            "engine_version": FIXTURE_ENGINE_VERSION,
                            "fixture": True,
                        },
                        ensure_ascii=False,
                    ),
                    source_fingerprint=asset.deduplication_key or asset.candidate_id,
                )
                asset_version_map[asset.candidate_id] = int(result.version.id)

                for ev_id in asset.evidence_refs:
                    cand_ev = evidence_by_id.get(ev_id)
                    if cand_ev is None:
                        continue
                    snap_para = para_by_stable.get(cand_ev.paragraph_id)
                    if snap_para is None:
                        raise NativeOverviewError(
                            WholeBookOverviewErrorCode.EVIDENCE_INVALID.value,
                            f"evidence paragraph not in snapshot: {cand_ev.paragraph_id}",
                            run_id=str(run.id),
                        )
                    text = self._snapshots.get_snapshot_paragraph_text(snap_para.id)
                    quote = cand_ev.quote
                    start = text.find(quote)
                    if start < 0:
                        start = 0
                        end = min(len(text), max(1, len(quote)))
                        quote = text[start:end]
                    else:
                        end = start + len(quote)
                    row = self._evidence.attach_asset_evidence(
                        result.version.id,
                        book_snapshot_id=snapshot_id,
                        snapshot_chapter_id=int(snap_para.snapshot_chapter_id),
                        snapshot_paragraph_id=int(snap_para.id),
                        paragraph_content_hash=snap_para.content_hash,
                        start_offset=start,
                        end_offset=end,
                        evidence_role=cand_ev.evidence_role or "support",
                        evidence_label=cand_ev.evidence_id,
                        actor="model",
                    )
                    evidence_rows.append(
                        {
                            "evidence_id": cand_ev.evidence_id,
                            "db_id": row.id,
                            "paragraph_id": cand_ev.paragraph_id,
                            "chapter_id": cand_ev.chapter_id,
                            "quote": quote,
                            "confidence": cand_ev.confidence,
                            "snapshot_paragraph_id": snap_para.id,
                            "source_paragraph_id": snap_para.source_paragraph_id,
                            "stable_paragraph_id": snap_para.stable_paragraph_id,
                            "content_hash": snap_para.content_hash,
                            "chapter_index": None,
                            "paragraph_index": snap_para.paragraph_order,
                            "asset_candidate_id": asset.candidate_id,
                        }
                    )

            state = WholeBookRunStateVersion(
                run_id=run.id,
                version_number=1,
                after_window_index=0,
                state_json=json.dumps(
                    {
                        "entities": entity_map,
                        "assets": asset_version_map,
                        "state_delta": window_result.state_delta.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                ),
                state_hash=hashlib.sha256(
                    json.dumps(sorted(entity_map.items())).encode("utf-8")
                ).hexdigest(),
                source_stage_key=OverviewProductionStageKey.MATERIALIZE_ASSETS.value,
            )
            self._session.add(state)

            window = self._session.scalar(
                select(WholeBookRunWindow).where(
                    WholeBookRunWindow.run_id == run.id,
                    WholeBookRunWindow.window_index == 0,
                )
            )
            if window is not None:
                window.state_version_after = 1

        self._session.flush()
        stage.checkpoint_json = json.dumps(
            {
                "entity_count": len(entity_map),
                "asset_count": len(asset_version_map),
                "evidence_count": len(evidence_rows),
                "window_result": window_result.model_dump(mode="json"),
                "evidence_rows": evidence_rows,
                "entity_map": entity_map,
                "asset_version_map": asset_version_map,
            },
            ensure_ascii=False,
        )
        return {
            "window_result": window_result,
            "evidence_rows": evidence_rows,
            "entity_map": entity_map,
            "asset_version_map": asset_version_map,
        }

    def _stage_projection(
        self,
        run: AnalysisRun,
        stage: AnalysisRunStage,
        materialization: dict[str, Any],
    ) -> AnalysisArtifact:
        window_result: WholeBookOverviewWindowResultV1 = materialization["window_result"]
        evidence_rows: list[dict[str, Any]] = materialization["evidence_rows"]
        synthesis_input = WholeBookOverviewSynthesisInputV1(
            contract_version=CONTRACT_VERSION,
            run_id=str(run.id),
            book_id=str(run.book_id),
            snapshot_id=str(run.book_snapshot_id),
            engine_version=FIXTURE_ENGINE_VERSION,
            prompt_version=FIXTURE_PROMPT_VERSION,
            entities=[
                e.model_dump(mode="json") for e in window_result.candidate_entities
            ],
            assets=[
                a.model_dump(mode="json") for a in window_result.candidate_assets
            ],
            evidence=[
                ev.model_dump(mode="json") for ev in window_result.candidate_evidence
            ],
            final_state=PriorStateV1.model_validate(
                {
                    **window_result.state_delta.model_dump(mode="json"),
                    "state_version": 1,
                }
            ),
            snapshot_meta={"snapshot_id": run.book_snapshot_id},
            selected_evidence=list(window_result.candidate_evidence),
        )
        try:
            projection = self._adapter.run_synthesis(synthesis_input)
            projection = WholeBookOverviewProjectionCandidateV1.model_validate(
                projection.model_dump()
            )
        except Exception as exc:  # noqa: BLE001
            raise NativeOverviewError(
                WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value,
                run_id=str(run.id),
                stage_key=stage.stage_key,
                details={"cause": type(exc).__name__},
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

        # Coverage: single cross-chapter window covering all snapshot paragraphs.
        para_total = int(
            self._session.scalar(
                select(func.count())
                .select_from(BookSnapshotParagraph)
                .where(BookSnapshotParagraph.snapshot_id == int(run.book_snapshot_id))
            )
            or 0
        )
        coverage = CoverageDTO(
            original_paragraphs_total=para_total,
            original_paragraphs_covered=para_total,
            original_coverage_percent=100.0 if para_total else 0.0,
            windows_total=1,
            windows_completed=1,
            evidence_count=len(evidence_rows),
        )

        evidence_index = self._build_evidence_index(run, evidence_rows)
        generated_at = utc_now()
        payload = {
            "overview": overview_body.model_dump(mode="json"),
            "coverage": coverage.model_dump(mode="json"),
            "evidence_index": [e.model_dump(mode="json") for e in evidence_index],
            "warnings": list(projection.warnings) or [FIXTURE_DEVELOPMENT_WARNING],
            "engine_id": FIXTURE_ENGINE_ID,
            "engine_version": FIXTURE_ENGINE_VERSION,
            "prompt_version": FIXTURE_PROMPT_VERSION,
            "generated_at": generated_at.isoformat(),
            "contract_version": CONTRACT_VERSION,
        }
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type=OVERVIEW_PROJECTION_ARTIFACT_TYPE,
            subject_type="book",
            subject_id=str(run.book_id),
            schema_version=CONTRACT_VERSION,
            prompt_version=FIXTURE_PROMPT_VERSION,
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
        stage.checkpoint_json = json.dumps(
            {
                "engine_id": FIXTURE_ENGINE_ID,
                "engine_version": FIXTURE_ENGINE_VERSION,
                "prompt_version": FIXTURE_PROMPT_VERSION,
                "fixture": True,
                "walking_skeleton": True,
                "production_ready": False,
            },
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_window_input(
        self, run: AnalysisRun, window: WholeBookRunWindow
    ) -> WholeBookOverviewWindowInputV1:
        assert run.book_snapshot_id is not None
        snap_paragraphs = list(
            self._session.scalars(
                select(BookSnapshotParagraph)
                .where(BookSnapshotParagraph.snapshot_id == int(run.book_snapshot_id))
                .order_by(BookSnapshotParagraph.paragraph_order)
            )
        )
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
            chapter_id = str(ch.source_chapter_id if ch and ch.source_chapter_id else p.snapshot_chapter_id)
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
        return WholeBookOverviewWindowInputV1(
            contract_version=CONTRACT_VERSION,
            run=OverviewRunRef(
                run_id=str(run.id),
                book_id=str(run.book_id),
                snapshot_id=str(run.book_snapshot_id),
                mode=WholeBookAnalysisMode.NATIVE,
                engine_version=FIXTURE_ENGINE_VERSION,
                prompt_version=FIXTURE_PROMPT_VERSION,
            ),
            window=WindowSlice(
                window_id=f"w-{window.window_index}",
                window_index=int(window.window_index),
                total_windows=1,
                start_paragraph_id=window.start_paragraph_id,
                end_paragraph_id=window.end_paragraph_id,
                chapter_refs=chapter_refs,
                paragraphs=paras,
                input_hash=window.input_hash,
                status=WindowStatus(window.status) if window.status else WindowStatus.RUNNING,
            ),
            prior_state=empty_prior_state(),
        )

    def _build_evidence_index(
        self, run: AnalysisRun, evidence_rows: list[dict[str, Any]]
    ) -> list[EvidenceIndexEntry]:
        # Deduplicate by evidence_id (same evidence may attach to multiple assets).
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
                    paragraph_id=str(row.get("stable_paragraph_id") or row.get("paragraph_id") or ""),
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
        validate_overview_stage_transition(stage.status, StageStatus.RUNNING)
        stage.status = StageStatus.RUNNING.value
        stage.attempt_count = int(stage.attempt_count or 0) + 1
        stage.started_at = utc_now()
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
        validate_overview_run_transition(run.status, target)
        run.status = target.value
        self._session.flush()

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
        run.error_message = exc.message
        run.retryable = True
        run.completed_at = utc_now()
        # Mark current running stage failed if any
        stage = self._session.scalar(
            select(AnalysisRunStage).where(
                AnalysisRunStage.run_id == run.id,
                AnalysisRunStage.status == StageStatus.RUNNING.value,
            )
        )
        if stage is not None:
            stage.status = StageStatus.FAILED.value
            stage.error_code = exc.code
            stage.error_message = exc.message
            stage.completed_at = utc_now()
        self._session.flush()

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

    def _to_create_response(self, run: AnalysisRun) -> CreateRunResponse:
        windows = list(
            self._session.scalars(
                select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run.id)
            )
        )
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
                percent=100.0 if run.status == RunStatus.COMPLETED.value else 0.0,
                current_window_index=0 if windows else None,
            ),
            created_at=run.created_at,
        )

    @staticmethod
    def _config_fingerprint() -> str:
        raw = f"{FIXTURE_ENGINE_ID}|{FIXTURE_ENGINE_VERSION}|{FIXTURE_PROMPT_VERSION}"
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
