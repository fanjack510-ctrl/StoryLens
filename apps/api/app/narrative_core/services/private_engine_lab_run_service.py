"""Private Whole-Book Lab Run Service (Phase 2B-R1 Agent V).

Creates AnalysisRun + 10 Stages, sequential four-module orchestration hooks.
Uses Agent U Ports for preflight/estimate/consent — no U logic duplication.
No real Provider HTTP. No Credential reads. No production create.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

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
    WholeBookStageKey,
)
from app.narrative_core.private_engine_contract.module_spec import (
    FIRST_FOUR_MODULE_KEYS,
    FIRST_FOUR_MODULE_SPECS,
    MODULE_PRODUCER_STAGES,
)
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.private_engine_lab import (
    CREATE_PRIVATE_LAB_RUN_SEQUENCE,
    PRIVATE_ENGINE_LAB_SOURCE,
    PRIVATE_LAB_ENGINE_ID,
    PRIVATE_LAB_ENGINE_VERSION,
    PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER,
    PRIVATE_LAB_FIRST_MODEL_ID,
    PRIVATE_LAB_FIRST_PROVIDER_KEY,
    PRIVATE_LAB_FIRST_QUALITY_PROFILE,
    PRIVATE_LAB_TASK_TYPE,
    PrivateEngineLabDenyReason,
)
from app.narrative_core.run_shell_contract.stage_lifecycle import (
    ORDERED_MOCK_STAGE_KEYS,
    build_stage_retry_impact,
)
from app.narrative_core.services.in_process_private_lab_task_registry import (
    InProcessPrivateLabTaskRegistry,
    get_default_private_lab_task_registry,
)
from app.narrative_core.services.private_engine_lab_authorization_service import (
    PrivateEngineLabAuthorizationDenied,
    PrivateEngineLabAuthorizationService,
)
from app.narrative_core.services.private_lab_idempotency import (
    PrivateLabConcurrencyGuard,
    PrivateLabCreateIdempotency,
    PrivateLabIdempotencyNamespace,
    occupies_active_slot,
)
from app.narrative_core.services.private_lab_ports import (
    FakePrivateLabConsentValidationPort,
    FakePrivateLabEstimatePort,
    FakePrivateLabPreflightPort,
    PrivateLabConsentValidationPort,
    PrivateLabEstimatePort,
    PrivateLabPreflightPort,
)
from app.narrative_core.services.private_lab_run_metadata import (
    build_private_lab_run_metadata,
    hash_create_payload,
    is_private_lab_run_metadata,
    parse_metadata_json,
    serialize_metadata,
)
from app.narrative_core.services.private_lab_run_state_service import (
    PrivateLabRunStateError,
    PrivateLabRunStateService,
    map_db_status_to_view,
)
from app.narrative_core.services.run_stage_service import RunStageService


class PrivateWholeBookLabRunError(Exception):
    def __init__(
        self,
        reason: PrivateEngineLabDenyReason,
        *,
        run_id: int | None = None,
        stage_key: str | None = None,
        message: str | None = None,
        detail_code: str | None = None,
    ) -> None:
        self.reason = reason
        self.run_id = run_id
        self.stage_key = stage_key
        self.detail_code = detail_code
        if message is not None:
            self.message = message
        elif detail_code:
            self.message = f"{reason.value}:{detail_code}"
        else:
            self.message = reason.value
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class CreatePrivateLabRunRequest:
    book_id: int
    book_snapshot_id: int
    analysis_mode: WholeBookAnalysisMode | str = WholeBookAnalysisMode.NATIVE
    requested_modules: tuple[str, ...] = PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER
    configuration_fingerprint: str = "private-lab-cfg"
    idempotency_key: str = "private-lab"
    preflight_fingerprint: str = "preflight-fp-ok"
    estimate_fingerprint: str = "estimate-fp-ok"
    consent_fingerprint: str = "consent-fp-ok"
    data_transfer_manifest_hash: str = "manifest-hash-ok"
    context_bundle_hash: str = "context-hash-ok"
    prompt_pack_id: str = "private.lab.pack"
    prompt_pack_version: str = "1.0.0"
    provider_key: str = PRIVATE_LAB_FIRST_PROVIDER_KEY
    model_id: str = PRIVATE_LAB_FIRST_MODEL_ID
    quality_profile: str = PRIVATE_LAB_FIRST_QUALITY_PROFILE
    output_locale: str = "zh-CN"
    source_language: str = "zh"
    dry_run: bool = True
    data_transfer_consented: bool = True
    user_confirmed: bool = True
    credential_present: bool = False
    budget_ok: bool = True
    capability_ok: bool = True
    requested_by: str = "lab"


@dataclass(frozen=True, slots=True)
class CreatePrivateLabRunResult:
    run_id: int
    book_id: int
    book_snapshot_id: int
    status: WholeBookRunViewStatus
    analysis_mode: WholeBookAnalysisMode
    requested_modules: tuple[str, ...]
    resolved_modules: tuple[str, ...]
    stage_plan: tuple[str, ...]
    private_lab: bool
    non_production: bool
    modules_implemented: bool
    created: bool
    duplicate_of_run_id: int | None
    created_at: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def active_stage_keys_for_modules(modules: Sequence[str]) -> set[str]:
    """Stages required by Module Execution Spec + scaffolds; others skipped."""

    active: set[str] = {
        WholeBookStageKey.BUILD_FULLTEXT_INDEX.value,
        WholeBookStageKey.RESOLVE_ENTITIES.value,
        WholeBookStageKey.VERIFY_EVIDENCE.value,
        WholeBookStageKey.PERSIST_NARRATIVE_ASSETS.value,
    }
    for raw in modules:
        try:
            key = WholeBookModuleKey(str(raw))
        except ValueError:
            continue
        for stage in MODULE_PRODUCER_STAGES.get(key, ()):
            active.add(stage.value)
        for spec in FIRST_FOUR_MODULE_SPECS:
            if spec.module_key == key:
                for stage in spec.required_stage_keys:
                    active.add(stage.value)
                for stage in spec.product_result_stage_dependencies:
                    active.add(stage.value)
    return active


def modules_for_stage(stage_key: str, resolved_modules: Sequence[str]) -> tuple[str, ...]:
    ordered = []
    for mod in PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER:
        if mod not in resolved_modules:
            continue
        try:
            key = WholeBookModuleKey(mod)
        except ValueError:
            continue
        producers = {s.value for s in MODULE_PRODUCER_STAGES.get(key, ())}
        if stage_key in producers:
            ordered.append(mod)
    return tuple(ordered)


class PrivateWholeBookLabRunService:
    """Lab-only whole-book private run lifecycle service."""

    CREATE_SEQUENCE = CREATE_PRIVATE_LAB_RUN_SEQUENCE

    def __init__(
        self,
        session: Session,
        *,
        auth: PrivateEngineLabAuthorizationService | None = None,
        stage_service: RunStageService | None = None,
        state_service: PrivateLabRunStateService | None = None,
        task_registry: InProcessPrivateLabTaskRegistry | None = None,
        idempotency: PrivateLabCreateIdempotency | None = None,
        concurrency: PrivateLabConcurrencyGuard | None = None,
        preflight_port: PrivateLabPreflightPort | None = None,
        estimate_port: PrivateLabEstimatePort | None = None,
        consent_port: PrivateLabConsentValidationPort | None = None,
    ) -> None:
        self._session = session
        self._auth = auth or PrivateEngineLabAuthorizationService(
            environment="test", lab_enabled=True
        )
        self._stages = stage_service or RunStageService(session)
        self._state = state_service or PrivateLabRunStateService(session)
        self._registry = task_registry or get_default_private_lab_task_registry()
        self._idempotency = idempotency or PrivateLabCreateIdempotency()
        self._concurrency = concurrency or PrivateLabConcurrencyGuard()
        self._preflight = preflight_port or FakePrivateLabPreflightPort()
        self._estimate = estimate_port or FakePrivateLabEstimatePort()
        self._consent = consent_port or FakePrivateLabConsentValidationPort()

    def authorize(
        self,
        *,
        loopback: bool,
        request_marker_present: bool,
        dry_run: bool = True,
        credential_present: bool = False,
        data_transfer_consented: bool = False,
        budget_ok: bool = True,
        capability_ok: bool = True,
        user_confirmed: bool = False,
    ) -> None:
        try:
            self._auth.require(
                loopback=loopback,
                request_marker_present=request_marker_present,
                credential_present=credential_present,
                data_transfer_consented=data_transfer_consented,
                budget_ok=budget_ok,
                capability_ok=capability_ok,
                user_confirmed=user_confirmed,
                dry_run=dry_run,
            )
        except PrivateEngineLabAuthorizationDenied as exc:
            raise PrivateWholeBookLabRunError(exc.reason, message=exc.message) from exc

    def create_run(
        self,
        request: CreatePrivateLabRunRequest,
        *,
        loopback: bool,
        request_marker_present: bool,
        auto_start: bool = False,
    ) -> CreatePrivateLabRunResult:
        # 1. authorize
        self.authorize(
            loopback=loopback,
            request_marker_present=request_marker_present,
            dry_run=request.dry_run,
            credential_present=request.credential_present,
            data_transfer_consented=request.data_transfer_consented,
            budget_ok=request.budget_ok,
            capability_ok=request.capability_ok,
            user_confirmed=request.user_confirmed,
        )

        mode = (
            request.analysis_mode
            if isinstance(request.analysis_mode, WholeBookAnalysisMode)
            else WholeBookAnalysisMode(str(request.analysis_mode))
        )
        resolved = self._resolve_modules(request.requested_modules)

        create_payload = {
            "book_id": int(request.book_id),
            "book_snapshot_id": int(request.book_snapshot_id),
            "analysis_mode": mode.value,
            "requested_modules": list(resolved),
            "configuration_fingerprint": request.configuration_fingerprint,
            "preflight_fingerprint": request.preflight_fingerprint,
            "estimate_fingerprint": request.estimate_fingerprint,
            "consent_fingerprint": request.consent_fingerprint,
        }
        resolved_idem = self._idempotency.resolve_create_request(
            idempotency_key=request.idempotency_key,
            actor=str(request.requested_by or "lab"),
            request_scope=f"book:{int(request.book_id)}",
            payload=create_payload,
        )
        if resolved_idem.conflict:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_IDEMPOTENCY_CONFLICT
            )
        if resolved_idem.hit and resolved_idem.record and resolved_idem.record.run_id is not None:
            existing = self._session.get(AnalysisRun, int(resolved_idem.record.run_id))
            if existing is not None and is_private_lab_run_metadata(existing.validated_output):
                return self._idempotent_result(existing, request, resolved)

        existing_db = self._find_by_idempotency_key(request.idempotency_key)
        if existing_db is not None:
            return self._idempotent_result(existing_db, request, resolved)

        # 2–6. Port + snapshot gates — fail before any Run write
        preflight = self._preflight.preflight(
            book_id=int(request.book_id),
            book_snapshot_id=int(request.book_snapshot_id),
            configuration_fingerprint=request.configuration_fingerprint,
            requested_modules=resolved,
        )
        if not preflight.ok:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_PREFLIGHT_REJECTED,
                detail_code=preflight.reason_code,
            )
        if preflight.fingerprint != request.preflight_fingerprint:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_PREFLIGHT_REJECTED,
                detail_code="PREFLIGHT_FINGERPRINT_MISMATCH",
            )

        estimate = self._estimate.estimate(
            book_id=int(request.book_id),
            book_snapshot_id=int(request.book_snapshot_id),
            configuration_fingerprint=request.configuration_fingerprint,
            provider_key=request.provider_key,
            model_id=request.model_id,
            quality_profile=request.quality_profile,
            requested_modules=resolved,
            preflight_fingerprint=request.preflight_fingerprint,
        )
        if not self._estimate.validate_fingerprint(
            expected_fingerprint=request.estimate_fingerprint, estimate=estimate
        ):
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_ESTIMATE_FINGERPRINT_MISMATCH
            )

        consent = self._consent.validate_consent(
            consent_fingerprint=request.consent_fingerprint,
            data_transfer_manifest_hash=request.data_transfer_manifest_hash
            or (estimate.data_transfer_manifest_hash or ""),
            data_transfer_consented=request.data_transfer_consented,
        )
        if not consent.ok:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONSENT_FINGERPRINT_MISMATCH,
                detail_code=consent.reason_code,
            )

        if not request.dry_run and not request.credential_present:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CREDENTIAL_REQUIRED
            )
        if not request.budget_ok:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_BUDGET_DENIED
            )

        book, snapshot = self._validate_snapshot(request.book_id, request.book_snapshot_id)

        # Durable active-run check then process concurrency reserve
        self._reserve_durable_slot(int(book.id))
        concurrency_reservation_id: str | None = None
        try:
            reservation = self._concurrency.reserve_book_slot(book_id=int(book.id))
            concurrency_reservation_id = reservation.reservation_id
        except RuntimeError as exc:
            if "CONCURRENCY" in str(exc):
                raise PrivateWholeBookLabRunError(
                    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONCURRENCY_LIMIT
                ) from exc
            raise

        payload_hash = hash_create_payload(create_payload)
        created_at = _utc_now_iso()
        metadata = build_private_lab_run_metadata(
            book_id=int(book.id),
            snapshot_id=int(snapshot.id),
            analysis_mode=mode.value,
            requested_modules=resolved,
            resolved_modules=resolved,
            provider_key=request.provider_key,
            model_id=request.model_id,
            quality_profile=request.quality_profile,
            engine_id=PRIVATE_LAB_ENGINE_ID,
            engine_version=PRIVATE_LAB_ENGINE_VERSION,
            prompt_pack_id=request.prompt_pack_id,
            prompt_pack_version=request.prompt_pack_version,
            context_bundle_hash=request.context_bundle_hash,
            estimate_fingerprint=request.estimate_fingerprint,
            consent_fingerprint=request.consent_fingerprint,
            configuration_fingerprint=request.configuration_fingerprint,
            data_transfer_manifest_hash=request.data_transfer_manifest_hash,
            output_locale=request.output_locale,
            source_language=request.source_language,
            create_idempotency_key=request.idempotency_key,
            created_at=created_at,
            dry_run=request.dry_run,
            extra={
                "idempotency_payload_hash": payload_hash,
                "preflight_fingerprint": request.preflight_fingerprint,
                "modules_implemented": True,
                "source": PRIVATE_ENGINE_LAB_SOURCE,
            },
        )

        stage_keys = tuple(k.value for k in ORDERED_MOCK_STAGE_KEYS)
        run: AnalysisRun | None = None
        try:
            run = self._stages.create_scoped_run(
                scope_type=AnalysisScopeType.BOOK,
                analysis_type=AnalysisType.WHOLE_BOOK_NATIVE,
                book_id=int(book.id),
                book_snapshot_id=int(snapshot.id),
                configuration_fingerprint=request.configuration_fingerprint,
                provider="private_lab",
                model=PRIVATE_LAB_ENGINE_ID,
                prompt_version=request.prompt_pack_version,
                schema_version="private-lab-v1",
                status=RunStatus.PENDING.value,
                task_type=PRIVATE_LAB_TASK_TYPE,
                analysis_mode=mode.value,
                client_request_id=request.idempotency_key[:64],
                validated_output=serialize_metadata(metadata),
                execution_mode="local",
            )
            self._stages.initialize_run_stages(int(run.id), list(stage_keys))
            self._mark_unused_stages_skipped(int(run.id), resolved)
            self._concurrency.bind_reservation_run(concurrency_reservation_id, int(run.id))
            self._registry.register(int(run.id))
        except Exception:
            if run is not None:
                try:
                    self._registry.mark_finished(int(run.id))
                except Exception:  # noqa: BLE001
                    pass
            if concurrency_reservation_id:
                self._concurrency.release_book_slot(
                    book_id=int(book.id), reservation_id=concurrency_reservation_id
                )
            self._session.rollback()
            raise

        self._idempotency.register_create_request(
            idempotency_key=request.idempotency_key,
            actor=str(request.requested_by or "lab"),
            request_scope=f"book:{int(book.id)}",
            payload=create_payload,
            run_id=int(run.id),
        )
        self._session.commit()
        self._session.refresh(run)

        if auto_start:
            # Executor start is cooperative — caller/router may invoke PrivateLabRunExecutor.
            pass

        created_at_db = run.created_at
        created_iso = (
            created_at_db.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            if isinstance(created_at_db, datetime)
            else created_at
        )
        return CreatePrivateLabRunResult(
            run_id=int(run.id),
            book_id=int(book.id),
            book_snapshot_id=int(snapshot.id),
            status=WholeBookRunViewStatus.PENDING,
            analysis_mode=mode,
            requested_modules=resolved,
            resolved_modules=resolved,
            stage_plan=stage_keys,
            private_lab=True,
            non_production=True,
            modules_implemented=True,
            created=True,
            duplicate_of_run_id=None,
            created_at=created_iso,
        )

    def get_run(self, run_id: int) -> dict[str, Any]:
        run, meta = self._require_private_run(run_id)
        stages = list(self._stages.get_run_stages(int(run.id)))
        return self._run_view(run, meta, stages)

    def get_run_stages(self, run_id: int) -> list[dict[str, Any]]:
        run, _meta = self._require_private_run(run_id)
        return [self._stage_view(s) for s in self._stages.get_run_stages(int(run.id))]

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
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONFIRM_REQUIRED,
                run_id=run_id,
                detail_code="CANCEL_CONFIRM_REQUIRED",
            )
        run, meta = self._require_private_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current == WholeBookRunViewStatus.CANCELLED:
            return self._action_result(run, meta, "cancel", idempotent=True)
        if current in (
            WholeBookRunViewStatus.COMPLETED,
            WholeBookRunViewStatus.FAILED,
        ):
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
            )
        try:
            result = self._state.transition(
                run,
                to_state=WholeBookRunViewStatus.CANCELLED,
                expected_state=expected_state or current,
                expected_version=expected_version,
                metadata=meta,
                operation_idempotency_key=operation_idempotency_key,
            )
        except PrivateLabRunStateError as exc:
            raise PrivateWholeBookLabRunError(exc.reason, run_id=int(run.id)) from exc
        meta["state_version"] = result.version
        run.validated_output = serialize_metadata(
            meta, existing_validated_output=run.validated_output
        )
        for stage in self._stages.get_run_stages(int(run.id)):
            st = StageStatus(stage.status)
            if st in (StageStatus.PENDING, StageStatus.RUNNING, StageStatus.PAUSED, StageStatus.INTERRUPTED):
                try:
                    self._stages.transition_stage(
                        int(run.id), stage.stage_key, StageStatus.CANCELLED
                    )
                except Exception:  # noqa: BLE001 — keep cancel best-effort on stages
                    pass
        handle = self._registry.request_cancel(int(run.id))
        self._registry.mark_finished(int(run.id))
        self._concurrency.note_run_status(int(run.id), WholeBookRunViewStatus.CANCELLED.value)
        self._idempotency.mark_operation_completed(
            namespace=PrivateLabIdempotencyNamespace.CANCEL,
            idempotency_key=operation_idempotency_key,
            actor="lab",
            request_scope=f"run:{int(run.id)}",
            result={"run_id": int(run.id), "status": "cancelled"},
            run_id=int(run.id),
        )
        self._session.commit()
        out = self._action_result(run, meta, "cancel")
        out["cancellation_ref"] = handle.cancellation_ref
        return out

    def resume_run(
        self,
        run_id: int,
        *,
        expected_state: WholeBookRunViewStatus | None = None,
        expected_version: int | None = None,
        estimate_fingerprint: str | None = None,
        consent_fingerprint: str | None = None,
        context_bundle_hash: str | None = None,
        operation_idempotency_key: str = "resume",
    ) -> dict[str, Any]:
        run, meta = self._require_private_run(run_id)
        current = map_db_status_to_view(str(run.status))
        if current not in (
            WholeBookRunViewStatus.PAUSED,
            WholeBookRunViewStatus.INTERRUPTED,
        ):
            if current == WholeBookRunViewStatus.RUNNING:
                return self._action_result(run, meta, "resume", idempotent=True)
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
            )
        # Fingerprint compatibility — silent Prompt/Model swap forbidden.
        if estimate_fingerprint is not None and estimate_fingerprint != meta.get(
            "estimate_fingerprint"
        ):
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_ESTIMATE_FINGERPRINT_MISMATCH,
                run_id=int(run.id),
            )
        if consent_fingerprint is not None and consent_fingerprint != meta.get(
            "consent_fingerprint"
        ):
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONSENT_FINGERPRINT_MISMATCH,
                run_id=int(run.id),
            )
        if context_bundle_hash is not None and context_bundle_hash != meta.get(
            "context_bundle_hash"
        ):
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CHECKPOINT_INVALID,
                run_id=int(run.id),
                detail_code="CONTEXT_BUNDLE_HASH_MISMATCH",
            )
        try:
            result = self._state.transition(
                run,
                to_state=WholeBookRunViewStatus.RUNNING,
                expected_state=expected_state or current,
                expected_version=expected_version,
                metadata=meta,
                operation_idempotency_key=operation_idempotency_key,
            )
        except PrivateLabRunStateError as exc:
            raise PrivateWholeBookLabRunError(exc.reason, run_id=int(run.id)) from exc
        meta["state_version"] = result.version
        run.validated_output = serialize_metadata(
            meta, existing_validated_output=run.validated_output
        )
        self._stages.resume_run(int(run.id))
        self._registry.clear_pause_request(int(run.id))
        self._registry.register(int(run.id))
        self._session.commit()
        return self._action_result(run, meta, "resume")

    def retry_stage(
        self,
        run_id: int,
        stage_key: str,
        *,
        expected_state: WholeBookRunViewStatus | None = None,
        expected_version: int | None = None,
        operation_idempotency_key: str = "retry",
    ) -> dict[str, Any]:
        run, meta = self._require_private_run(run_id)
        current = map_db_status_to_view(str(run.status))
        stage = next(
            (s for s in self._stages.get_run_stages(int(run.id)) if s.stage_key == stage_key),
            None,
        )
        if stage is None:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
                stage_key=stage_key,
                detail_code="STAGE_NOT_FOUND",
            )
        if StageStatus(stage.status) == StageStatus.COMPLETED:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
                stage_key=stage_key,
                detail_code="COMPLETED_STAGE_NO_RETRY",
            )
        if StageStatus(stage.status) != StageStatus.FAILED:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
                stage_key=stage_key,
                detail_code="RETRY_REQUIRES_FAILED",
            )
        impact = build_stage_retry_impact(stage_key)
        self._stages.retry_failed_stage(int(run.id), stage_key)
        for downstream in impact.reset_downstream_stage_keys:
            ds = next(
                (s for s in self._stages.get_run_stages(int(run.id)) if s.stage_key == downstream),
                None,
            )
            if ds is None:
                continue
            if StageStatus(ds.status) in (
                StageStatus.FAILED,
                StageStatus.RUNNING,
                StageStatus.PAUSED,
                StageStatus.INTERRUPTED,
                StageStatus.COMPLETED,
            ):
                # Reset affected downstream to pending when allowed; completed historical
                # artifacts retained — only reopen non-terminal when transition allows.
                if StageStatus(ds.status) != StageStatus.COMPLETED:
                    try:
                        if StageStatus(ds.status) != StageStatus.PENDING:
                            # failed→running already handled for target; for downstream
                            # reopen via repository if pending path available
                            pass
                    except Exception:  # noqa: BLE001
                        pass
        if current in (
            WholeBookRunViewStatus.FAILED,
            WholeBookRunViewStatus.PAUSED,
            WholeBookRunViewStatus.INTERRUPTED,
            WholeBookRunViewStatus.PENDING,
        ):
            try:
                result = self._state.transition(
                    run,
                    to_state=WholeBookRunViewStatus.RUNNING,
                    expected_state=expected_state or current,
                    expected_version=expected_version,
                    metadata=meta,
                    operation_idempotency_key=operation_idempotency_key,
                )
                meta["state_version"] = result.version
                run.validated_output = serialize_metadata(
                    meta, existing_validated_output=run.validated_output
                )
            except PrivateLabRunStateError:
                pass
        self._registry.register(int(run.id))
        self._session.commit()
        out = self._action_result(run, meta, "retry")
        out["stage_key"] = stage_key
        out["attempt"] = int(getattr(stage, "attempt_count", 0) or 0) + 1
        out["reset_downstream"] = list(impact.reset_downstream_stage_keys)
        return out

    # ----- internals -----

    def _resolve_modules(self, requested: Sequence[str]) -> tuple[str, ...]:
        if not requested:
            return PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER
        out: list[str] = []
        for raw in requested:
            key = str(raw)
            try:
                mod = WholeBookModuleKey(key)
            except ValueError as exc:
                raise PrivateWholeBookLabRunError(
                    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                    detail_code="MODULE_INVALID",
                ) from exc
            if mod not in FIRST_FOUR_MODULE_KEYS:
                raise PrivateWholeBookLabRunError(
                    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                    detail_code="MODULE_NOT_IN_FIRST_FOUR",
                )
            if key not in out:
                out.append(key)
        # Preserve frozen first-four order
        return tuple(m for m in PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER if m in out)

    def _validate_snapshot(self, book_id: int, snapshot_id: int) -> tuple[Book, BookSnapshot]:
        book = self._session.get(Book, int(book_id))
        if book is None:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_SNAPSHOT_INVALID,
                detail_code="BOOK_NOT_FOUND",
            )
        snapshot = self._session.get(BookSnapshot, int(snapshot_id))
        if snapshot is None or int(snapshot.book_id) != int(book_id):
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_SNAPSHOT_INVALID,
                detail_code="SNAPSHOT_BOOK_MISMATCH",
            )
        if str(snapshot.snapshot_status) != SnapshotStatus.COMPLETED.value:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_SNAPSHOT_INVALID,
                detail_code="SNAPSHOT_NOT_COMPLETED",
            )
        return book, snapshot

    def _reserve_durable_slot(self, book_id: int) -> None:
        rows = self._session.scalars(
            select(AnalysisRun).where(
                AnalysisRun.book_id == int(book_id),
                AnalysisRun.task_type == PRIVATE_LAB_TASK_TYPE,
            )
        ).all()
        for run in rows:
            if not is_private_lab_run_metadata(run.validated_output):
                continue
            if occupies_active_slot(map_db_status_to_view(str(run.status)).value):
                raise PrivateWholeBookLabRunError(
                    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONCURRENCY_LIMIT
                )

    def _mark_unused_stages_skipped(self, run_id: int, resolved_modules: Sequence[str]) -> None:
        active = active_stage_keys_for_modules(resolved_modules)
        for stage in self._stages.get_run_stages(run_id):
            if stage.stage_key in active:
                continue
            self._stages.transition_stage(
                run_id,
                stage.stage_key,
                StageStatus.SKIPPED,
                error_code="MODULE_NOT_REQUESTED",
                error_message=(
                    f"stage {stage.stage_key} skipped — not required by requested modules "
                    f"{list(resolved_modules)}"
                ),
            )

    def _find_by_idempotency_key(self, key: str) -> AnalysisRun | None:
        return self._session.scalars(
            select(AnalysisRun).where(AnalysisRun.client_request_id == key[:64])
        ).first()

    def _require_private_run(self, run_id: int) -> tuple[AnalysisRun, dict[str, Any]]:
        run = self._session.get(AnalysisRun, int(run_id))
        if run is None:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_RUN_NOT_FOUND,
                run_id=run_id,
            )
        if not is_private_lab_run_metadata(run.validated_output):
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_NOT_PRIVATE_RUN,
                run_id=run_id,
            )
        return run, parse_metadata_json(run.validated_output)

    def _idempotent_result(
        self,
        run: AnalysisRun,
        request: CreatePrivateLabRunRequest,
        resolved: tuple[str, ...],
    ) -> CreatePrivateLabRunResult:
        mode = (
            request.analysis_mode
            if isinstance(request.analysis_mode, WholeBookAnalysisMode)
            else WholeBookAnalysisMode(str(request.analysis_mode))
        )
        return CreatePrivateLabRunResult(
            run_id=int(run.id),
            book_id=int(run.book_id or request.book_id),
            book_snapshot_id=int(run.book_snapshot_id or request.book_snapshot_id),
            status=map_db_status_to_view(str(run.status)),
            analysis_mode=mode,
            requested_modules=resolved,
            resolved_modules=resolved,
            stage_plan=tuple(k.value for k in ORDERED_MOCK_STAGE_KEYS),
            private_lab=True,
            non_production=True,
            modules_implemented=True,
            created=False,
            duplicate_of_run_id=int(run.id),
            created_at=_utc_now_iso(),
        )

    def _run_view(
        self, run: AnalysisRun, meta: dict[str, Any], stages: Sequence[AnalysisRunStage]
    ) -> dict[str, Any]:
        return {
            "run_id": int(run.id),
            "book_id": int(run.book_id or 0),
            "book_snapshot_id": int(run.book_snapshot_id or 0),
            "status": map_db_status_to_view(str(run.status)).value,
            "state_version": int(meta.get("state_version", 0) or 0),
            "private_lab": True,
            "non_production": True,
            "mock_lab": False,
            "modules_implemented": True,
            "analysis_mode": meta.get("analysis_mode"),
            "requested_modules": list(meta.get("requested_modules") or []),
            "resolved_modules": list(meta.get("resolved_modules") or []),
            "provider_key": meta.get("provider_key"),
            "model_id": meta.get("model_id"),
            "quality_profile": meta.get("quality_profile"),
            "engine_id": meta.get("engine_id"),
            "engine_version": meta.get("engine_version"),
            "estimate_fingerprint": meta.get("estimate_fingerprint"),
            "consent_fingerprint": meta.get("consent_fingerprint"),
            "configuration_fingerprint": meta.get("configuration_fingerprint"),
            "stage_count": len(stages),
            "stages_completed": sum(
                1 for s in stages if StageStatus(s.status) == StageStatus.COMPLETED
            ),
            "stages_skipped": sum(
                1 for s in stages if StageStatus(s.status) == StageStatus.SKIPPED
            ),
            "created_at": meta.get("created_at"),
        }

    def _stage_view(self, stage: AnalysisRunStage) -> dict[str, Any]:
        return {
            "stage_key": stage.stage_key,
            "status": stage.status,
            "attempt_count": int(getattr(stage, "attempt_count", 0) or 0),
            "error_code": getattr(stage, "error_code", None),
            "error_message": getattr(stage, "error_message", None),
            "run_stage_id": int(stage.id),
        }

    def _action_result(
        self,
        run: AnalysisRun,
        meta: dict[str, Any],
        action: str,
        *,
        idempotent: bool = False,
    ) -> dict[str, Any]:
        return {
            "run_id": int(run.id),
            "status": map_db_status_to_view(str(run.status)).value,
            "state_version": int(meta.get("state_version", 0) or 0),
            "action": action,
            "idempotent": idempotent,
            "private_lab": True,
            "non_production": True,
        }


__all__ = [
    "CreatePrivateLabRunRequest",
    "CreatePrivateLabRunResult",
    "PrivateWholeBookLabRunError",
    "PrivateWholeBookLabRunService",
    "active_stage_keys_for_modules",
    "modules_for_stage",
]
