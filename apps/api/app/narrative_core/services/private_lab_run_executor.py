"""Private Lab Run Executor (Phase 2B-R1 Agent V).

Sequential four-module execution via PrivateWholeBookAnalysisRuntime + Fake Provider Port.
No real Provider HTTP. No Credential reads. No novel-specific inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun
from app.narrative_core.enums import (
    RunStatus,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WholeBookStageKey,
)
from app.narrative_core.run_shell_contract.private_engine_lab import (
    PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER,
    PrivateEngineLabDenyReason,
)
from app.narrative_core.run_shell_contract.stage_lifecycle import ORDERED_MOCK_STAGE_KEYS
from app.narrative_core.services.candidate_persistence_adapter import (
    Phase1BCandidatePersistenceSink,
    RecordingCandidatePersistenceSink,
)
from app.narrative_core.services.in_process_private_lab_task_registry import (
    InProcessPrivateLabTaskRegistry,
    get_default_private_lab_task_registry,
)
from app.narrative_core.services.private_engine_lab_run_service import (
    PrivateWholeBookLabRunError,
    modules_for_stage,
)
from app.narrative_core.services.live_engine_kind import (
    LiveEngineKind,
    assert_live_private_real,
    classify_live_engine_kind,
)
from app.narrative_core.services.private_engine_signature import is_fake_or_test_engine_id
from app.narrative_core.services.private_lab_idempotency import PrivateLabConcurrencyGuard
from app.narrative_core.services.private_lab_ports import (
    FakePrivateLabProviderExecutionPort,
    PrivateLabProviderExecutionPort,
)
from app.narrative_core.services.private_lab_run_metadata import (
    is_private_lab_run_metadata,
    parse_metadata_json,
    serialize_metadata,
)
from app.narrative_core.services.private_lab_run_state_service import (
    PrivateLabRunStateService,
    map_db_status_to_view,
)
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.services.run_stage_service import RunStageService


def _provider_attempt_record(
    *,
    module_key: str,
    stage_key: str,
    attempt_index: int,
    attempt_kind: str,
    provider_usage: Mapping[str, Any],
    cost_val: Any,
    effective_dry_run: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Safe provider attempt row for append-only checkpoint namespace (no bodies)."""

    record = {
        "attempt_index": int(attempt_index),
        "attempt_kind": str(attempt_kind),
        "module_key": module_key,
        "stage_key": stage_key,
        "checkpoint_kind": "provider_attempt",
        "provider_attempted": True,
        "provider_request_id": provider_usage.get("provider_request_id"),
        "provider_request_ids": list(provider_usage.get("provider_request_ids") or []),
        "provider_host": provider_usage.get("provider_host") or provider_usage.get("host"),
        "transport_kind": provider_usage.get("transport_kind"),
        "http_status": provider_usage.get("http_status"),
        "response_received": provider_usage.get("response_received", True),
        "finish_reason": provider_usage.get("finish_reason"),
        "latency_ms": provider_usage.get("latency_ms"),
        "usage_source": provider_usage.get("usage_source"),
        "input_tokens": provider_usage.get("input_tokens"),
        "output_tokens": provider_usage.get("output_tokens"),
        "cached_tokens": provider_usage.get("cached_tokens"),
        "retry_count": provider_usage.get("retry_count"),
        "actual_cost": cost_val,
        "pricing_version": provider_usage.get("pricing_version"),
        "attempt_status": provider_usage.get("attempt_status")
        or provider_usage.get("provider_status")
        or "success",
        "error_code": provider_usage.get("failure_code")
        or provider_usage.get("detail_code")
        or provider_usage.get("provider_error_code"),
        "started_at": provider_usage.get("started_at"),
        "completed_at": provider_usage.get("completed_at"),
        "effective_dry_run": effective_dry_run,
        "live_request_confirmed": provider_usage.get("live_request_confirmed"),
    }
    if extra:
        record.update(dict(extra))
    return record


@dataclass(frozen=True, slots=True)
class PrivateLabExecutorActionResult:
    run_id: int
    status: str
    applied: bool
    detail: Mapping[str, Any] = field(default_factory=dict)


class PrivateLabRunExecutor:
    """Sequential Private Lab executor — scaffold stages + first-four modules."""

    def __init__(
        self,
        session: Session,
        *,
        stage_service: RunStageService | None = None,
        state_service: PrivateLabRunStateService | None = None,
        task_registry: InProcessPrivateLabTaskRegistry | None = None,
        concurrency: PrivateLabConcurrencyGuard | None = None,
        provider_port: PrivateLabProviderExecutionPort | None = None,
        runtime_factory: Callable[..., Any] | None = None,
        use_recording_persistence: bool = False,
    ) -> None:
        self._session = session
        self._stages = stage_service or RunStageService(session)
        self._state = state_service or PrivateLabRunStateService(session)
        self._registry = task_registry or get_default_private_lab_task_registry()
        self._concurrency = concurrency or PrivateLabConcurrencyGuard()
        self._provider = provider_port or FakePrivateLabProviderExecutionPort()
        self._runtime_factory = runtime_factory
        self._use_recording_persistence = use_recording_persistence
        self._completed_module_fps: dict[tuple[int, str], str] = {}
        self._module_results: dict[int, list[dict[str, Any]]] = {}

    def start(self, run_id: int) -> PrivateLabExecutorActionResult:
        run, meta = self._require(run_id)
        if not self._concurrency.acquire_executor(int(run_id)):
            return PrivateLabExecutorActionResult(
                run_id=int(run_id),
                status=map_db_status_to_view(str(run.status)).value,
                applied=False,
                detail={"reason": "executor_lease_held"},
            )
        try:
            current = map_db_status_to_view(str(run.status))
            if current == WholeBookRunViewStatus.PENDING:
                result = self._state.transition(
                    run,
                    to_state=WholeBookRunViewStatus.RUNNING,
                    expected_state=WholeBookRunViewStatus.PENDING,
                    expected_version=int(meta.get("state_version", 0) or 0),
                    metadata=meta,
                    operation_idempotency_key="executor_start",
                )
                meta["state_version"] = result.version
                run.validated_output = serialize_metadata(
                    meta, existing_validated_output=run.validated_output
                )
            self._registry.mark_running(int(run_id))
            self._session.commit()
            return self.execute_until_blocked(int(run_id))
        finally:
            self._concurrency.release_executor(int(run_id))

    def execute_until_blocked(self, run_id: int) -> PrivateLabExecutorActionResult:
        run, meta = self._require(run_id)
        handle = self._registry.get(int(run_id))
        cancellation_ref = handle.cancellation_ref if handle else f"private-lab-cancel:{run_id}"
        resolved = [str(m) for m in (meta.get("resolved_modules") or PRIVATE_LAB_FIRST_FOUR_MODULE_ORDER)]
        results: list[dict[str, Any]] = list(self._module_results.get(int(run_id), []))

        for stage_key_enum in ORDERED_MOCK_STAGE_KEYS:
            if self._registry.is_cancel_requested(int(run_id)):
                self._provider.cancel(cancellation_ref or "")
                return self._cancel_terminal(run, meta, results, cancellation_ref)

            stage_key = stage_key_enum.value
            stage = next(
                (s for s in self._stages.get_run_stages(int(run_id)) if s.stage_key == stage_key),
                None,
            )
            if stage is None:
                continue
            status = StageStatus(stage.status)
            if status in (StageStatus.COMPLETED, StageStatus.SKIPPED, StageStatus.CANCELLED):
                continue
            if status == StageStatus.FAILED:
                return PrivateLabExecutorActionResult(
                    run_id=int(run_id),
                    status=WholeBookRunViewStatus.FAILED.value,
                    applied=True,
                    detail={"blocked_on": stage_key, "module_results": results},
                )

            # Start stage
            if status == StageStatus.PENDING:
                self._stages.transition_stage(int(run_id), stage_key, StageStatus.RUNNING)

            mods = modules_for_stage(stage_key, resolved)
            if not mods:
                # Scaffold / non-module stage — complete without Provider
                if stage_key in {
                    WholeBookStageKey.BUILD_FULLTEXT_INDEX.value,
                    WholeBookStageKey.RESOLVE_ENTITIES.value,
                    WholeBookStageKey.VERIFY_EVIDENCE.value,
                    WholeBookStageKey.PERSIST_NARRATIVE_ASSETS.value,
                }:
                    self._stages.write_checkpoint(
                        int(run_id),
                        stage_key,
                        {
                            "schema": "narrative_run_stage_checkpoint",
                            "version": "1",
                            "stage_key": stage_key,
                            "private_lab": True,
                            "scaffold": True,
                        },
                    )
                    self._stages.transition_stage(int(run_id), stage_key, StageStatus.COMPLETED)
                    continue
                # Unexpected active non-module stage — skip safely
                self._stages.transition_stage(
                    int(run_id),
                    stage_key,
                    StageStatus.SKIPPED,
                    error_code="NO_MODULE_FOR_STAGE",
                    error_message="no first-four module mapped to stage",
                )
                continue

            for module_key in mods:
                if self._registry.is_cancel_requested(int(run_id)):
                    self._provider.cancel(cancellation_ref or "")
                    return self._cancel_terminal(run, meta, results, cancellation_ref)

                fp_key = (int(run_id), module_key)
                if fp_key in self._completed_module_fps:
                    # completed module — do not re-persist
                    continue

                try:
                    module_result = self._execute_module(
                        run=run,
                        meta=meta,
                        stage=stage,
                        module_key=module_key,
                        cancellation_ref=cancellation_ref,
                    )
                except Exception as exc:  # noqa: BLE001
                    self._stages.transition_stage(
                        int(run_id),
                        stage_key,
                        StageStatus.FAILED,
                        error_code="MODULE_EXECUTION_FAILED",
                        error_message=str(exc)[:400],
                    )
                    try:
                        self._state.transition(
                            run,
                            to_state=WholeBookRunViewStatus.FAILED,
                            expected_state=map_db_status_to_view(str(run.status)),
                            expected_version=int(meta.get("state_version", 0) or 0),
                            metadata=meta,
                            operation_idempotency_key=f"fail:{module_key}",
                        )
                    except Exception:  # noqa: BLE001
                        run.status = RunStatus.FAILED.value
                    self._registry.mark_finished(int(run_id))
                    self._concurrency.note_run_status(
                        int(run_id), WholeBookRunViewStatus.FAILED.value
                    )
                    self._session.commit()
                    return PrivateLabExecutorActionResult(
                        run_id=int(run_id),
                        status=WholeBookRunViewStatus.FAILED.value,
                        applied=True,
                        detail={
                            "failed_module": module_key,
                            "error": str(exc),
                            "module_results": results,
                            "partial": True,
                        },
                    )

                results.append(module_result)
                self._module_results[int(run_id)] = results
                if module_result.get("output_fingerprint"):
                    self._completed_module_fps[fp_key] = str(module_result["output_fingerprint"])
                # Live business module must not complete Stage/Run on soft failures.
                if not bool(meta.get("dry_run", True)):
                    if module_result.get("status") != "success":
                        self._stages.transition_stage(
                            int(run_id),
                            stage_key,
                            StageStatus.FAILED,
                            error_code="LIVE_MODULE_NOT_SUCCESS",
                            error_message=str(module_result.get("status"))[:200],
                        )
                        try:
                            self._state.transition(
                                run,
                                to_state=WholeBookRunViewStatus.FAILED,
                                expected_state=map_db_status_to_view(str(run.status)),
                                expected_version=int(meta.get("state_version", 0) or 0),
                                metadata=meta,
                                operation_idempotency_key=f"fail:{module_key}",
                            )
                        except Exception:  # noqa: BLE001
                            run.status = RunStatus.FAILED.value
                        self._registry.mark_finished(int(run_id))
                        self._concurrency.note_run_status(
                            int(run_id), WholeBookRunViewStatus.FAILED.value
                        )
                        self._session.commit()
                        return PrivateLabExecutorActionResult(
                            run_id=int(run_id),
                            status=WholeBookRunViewStatus.FAILED.value,
                            applied=True,
                            detail={
                                "failed_module": module_key,
                                "module_results": results,
                                "partial": True,
                            },
                        )

            # Refresh stage after modules
            stage = next(
                (s for s in self._stages.get_run_stages(int(run_id)) if s.stage_key == stage_key),
                None,
            )
            if stage and StageStatus(stage.status) == StageStatus.RUNNING:
                self._stages.transition_stage(int(run_id), stage_key, StageStatus.COMPLETED)

        # All done — Live requires every requested module success + usage/ORM.
        if not bool(meta.get("dry_run", True)):
            live_ok = True
            for mr in results:
                if mr.get("status") != "success":
                    live_ok = False
                if not (mr.get("usage") or {}).get("provider_request_id"):
                    live_ok = False
                if not (mr.get("persistence_summary") or {}).get("orm_written"):
                    live_ok = False
                if int((mr.get("evidence_summary") or {}).get("count") or 0) < 1:
                    live_ok = False
            if not live_ok:
                try:
                    self._state.transition(
                        run,
                        to_state=WholeBookRunViewStatus.FAILED,
                        expected_state=map_db_status_to_view(str(run.status)),
                        expected_version=int(meta.get("state_version", 0) or 0),
                        metadata=meta,
                        operation_idempotency_key="executor_live_incomplete",
                    )
                except Exception:  # noqa: BLE001
                    run.status = RunStatus.FAILED.value
                self._registry.mark_finished(int(run_id))
                self._concurrency.note_run_status(
                    int(run_id), WholeBookRunViewStatus.FAILED.value
                )
                self._session.commit()
                return PrivateLabExecutorActionResult(
                    run_id=int(run_id),
                    status=WholeBookRunViewStatus.FAILED.value,
                    applied=True,
                    detail={"module_results": results, "live_incomplete": True},
                )

        try:
            result = self._state.transition(
                run,
                to_state=WholeBookRunViewStatus.COMPLETED,
                expected_state=map_db_status_to_view(str(run.status)),
                expected_version=int(meta.get("state_version", 0) or 0),
                metadata=meta,
                operation_idempotency_key="executor_complete",
            )
            meta["state_version"] = result.version
            run.validated_output = serialize_metadata(
                meta, existing_validated_output=run.validated_output
            )
        except Exception:  # noqa: BLE001
            run.status = RunStatus.COMPLETED.value
        self._registry.mark_finished(int(run_id))
        self._concurrency.note_run_status(int(run_id), WholeBookRunViewStatus.COMPLETED.value)
        self._session.commit()
        return PrivateLabExecutorActionResult(
            run_id=int(run_id),
            status=WholeBookRunViewStatus.COMPLETED.value,
            applied=True,
            detail={"module_results": results},
        )

    def cancel(self, run_id: int) -> PrivateLabExecutorActionResult:
        self._registry.request_cancel(int(run_id))
        handle = self._registry.get(int(run_id))
        ref = handle.cancellation_ref if handle else f"private-lab-cancel:{run_id}"
        self._provider.cancel(ref or "")
        run, meta = self._require(run_id)
        return self._cancel_terminal(run, meta, self._module_results.get(int(run_id), []), ref)

    def resume(self, run_id: int) -> PrivateLabExecutorActionResult:
        self._registry.clear_pause_request(int(run_id))
        self._registry.register(int(run_id))
        return self.start(int(run_id))

    def retry_stage(self, run_id: int, stage_key: str) -> PrivateLabExecutorActionResult:
        # Clear completed fingerprints for this stage's modules so they re-run.
        run, meta = self._require(run_id)
        resolved = [str(m) for m in (meta.get("resolved_modules") or [])]
        for mod in modules_for_stage(stage_key, resolved):
            self._completed_module_fps.pop((int(run_id), mod), None)
        return self.start(int(run_id))

    def get_module_results(self, run_id: int) -> list[dict[str, Any]]:
        return list(self._module_results.get(int(run_id), []))

    def _execute_module(
        self,
        *,
        run: AnalysisRun,
        meta: Mapping[str, Any],
        stage: Any,
        module_key: str,
        cancellation_ref: str | None,
    ) -> dict[str, Any]:
        live_requested = not bool(meta.get("dry_run", True))
        effective_dry_run = bool(meta.get("dry_run", True))

        # Live must have ORM persistence capability before any Provider call.
        if live_requested:
            if self._use_recording_persistence or self._runtime_factory is None:
                raise PrivateWholeBookLabRunError(
                    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                    run_id=int(run.id),
                    detail_code="LIVE_PERSISTENCE_CAPABILITY_MISSING",
                )

        runtime: Any | None = None
        context_bundle_hash: str | None = None
        citation_paragraph_units: list[dict[str, Any]] = []
        allowed_citation_ids: tuple[str, ...] = ()
        citation_catalog: Any | None = None
        if live_requested and self._runtime_factory is not None:
            runtime = self._runtime_factory(
                session=self._session,
                book_id=int(run.book_id or 0),
                use_phase1b_persistence=not self._use_recording_persistence,
                dry_run=effective_dry_run,
            )
            try:
                assert_live_private_real(
                    engine_id=self._runtime_engine_id(runtime),
                    private_modules_bound=bool(getattr(runtime, "private_modules_bound", False)),
                    synthetic=bool(getattr(runtime, "synthetic", True)),
                )
            except RuntimeError as exc:
                raise PrivateWholeBookLabRunError(
                    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                    run_id=int(run.id),
                    detail_code=str(exc),
                ) from exc
            # CHG-058: build Context Bundle before Provider so CitationCatalog IDs match enrich.
            if hasattr(runtime, "build_native_context_bundle") and str(module_key) == "book_overview":
                _wb, contract = runtime.build_native_context_bundle(
                    book_id=int(run.book_id or 0),
                    book_snapshot_id=int(run.book_snapshot_id or 0),
                    module_keys=(module_key,),
                )
                context_bundle_hash = str(getattr(contract, "bundle_hash", "") or "")
                meta["context_bundle_hash"] = context_bundle_hash
                from app.narrative_core.private_engine_contract.context import (
                    make_context_bundle_ref,
                )
                from app.narrative_core.services.citation_catalog_v2 import (
                    build_catalog_from_paragraph_units,
                )

                meta["context_bundle_ref"] = make_context_bundle_ref(context_bundle_hash)
                # Mirror enrich paragraph units (locator + length filler).
                if hasattr(runtime, "_paragraph_units_for_citation_catalog"):
                    citation_paragraph_units = list(
                        runtime._paragraph_units_for_citation_catalog(  # noqa: SLF001
                            contract=contract,
                            book_snapshot_id=int(run.book_snapshot_id or 0),
                            selected_paragraph_ids=None,
                        )
                    )
                if citation_paragraph_units and context_bundle_hash:
                    citation_catalog = build_catalog_from_paragraph_units(
                        context_bundle_hash=context_bundle_hash,
                        snapshot_id=int(run.book_snapshot_id or 0),
                        paragraph_units=citation_paragraph_units,
                        context_bundle_ref=str(meta.get("context_bundle_ref") or ""),
                    )
                    allowed_citation_ids = tuple(citation_catalog.citation_ids)

        usage = self._provider.execute_module(
            module_key=module_key,
            request={
                "run_id": int(run.id),
                "book_id": int(run.book_id or 0),
                "book_snapshot_id": int(run.book_snapshot_id or 0),
                "configuration_fingerprint": meta.get("configuration_fingerprint"),
                "dry_run": effective_dry_run,
                "consent_valid": True,
                "estimate_valid": True,
                "context_bundle_hash": context_bundle_hash,
                "citation_paragraph_units": citation_paragraph_units,
                "allowed_citation_ids": list(allowed_citation_ids),
                "citation_catalog": citation_catalog,
            },
            cancellation_ref=cancellation_ref,
        )
        if usage.status == "cancelled":
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
                detail_code="MODULE_CANCELLED",
            )
        if usage.status in {"security_denied", "provider_failed", "budget_denied"}:
            provider_usage = dict(usage.usage or {})
            # CHG-057: retain Stage provider_attempt authority even when Live fails after calls.
            if provider_usage.get("provider_attempted") or provider_usage.get(
                "provider_request_ids"
            ):
                token_in = int(provider_usage.get("input_tokens") or 0)
                token_out = int(provider_usage.get("output_tokens") or 0)
                cost_val = provider_usage.get("actual_cost")
                if cost_val is None:
                    cost_val = provider_usage.get("cost")
                accumulate: dict[str, Any] = {
                    "token_input": token_in,
                    "token_output": token_out,
                }
                if cost_val is not None:
                    accumulate["cost"] = float(cost_val)
                self._stages.write_checkpoint(
                    int(run.id),
                    stage.stage_key,
                    {
                        "schema": "narrative_run_stage_checkpoint",
                        "version": "1",
                        "stage_key": stage.stage_key,
                        "module_key": module_key,
                        "private_lab": True,
                        "non_production": True,
                        "attempt": int(getattr(stage, "attempt_count", 0) or 0),
                        "checkpoint_kind": "provider_attempt",
                        "provider_attempted": True,
                        "provider_request_id": provider_usage.get("provider_request_id"),
                        "transport_kind": provider_usage.get("transport_kind"),
                        "http_status": provider_usage.get("http_status"),
                        "usage_source": provider_usage.get("usage_source"),
                        "provider_status": usage.status,
                    },
                    append_provider_attempt=_provider_attempt_record(
                        module_key=module_key,
                        stage_key=stage.stage_key,
                        attempt_index=int(getattr(stage, "attempt_count", 0) or 0),
                        attempt_kind="initial",
                        provider_usage=provider_usage,
                        cost_val=cost_val,
                        effective_dry_run=effective_dry_run,
                        extra={
                            "attempt_status": usage.status,
                            "error_code": provider_usage.get("failure_code")
                            or provider_usage.get("detail_code"),
                            "provider_status": usage.status,
                            "attempts": list(provider_usage.get("attempts") or []),
                        },
                    ),
                    **accumulate,
                )
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
                detail_code=f"MODULE_{str(usage.status).upper()}",
            )

        provider_usage = dict(usage.usage or {})
        token_in = int(provider_usage.get("input_tokens") or 0)
        token_out = int(provider_usage.get("output_tokens") or 0)
        cost_val = provider_usage.get("actual_cost")
        if cost_val is None:
            cost_val = provider_usage.get("cost")
        accumulate: dict[str, Any] = {
            "token_input": token_in,
            "token_output": token_out,
        }
        if cost_val is not None:
            accumulate["cost"] = float(cost_val)

        self._stages.write_checkpoint(
            int(run.id),
            stage.stage_key,
            {
                "schema": "narrative_run_stage_checkpoint",
                "version": "1",
                "stage_key": stage.stage_key,
                "module_key": module_key,
                "private_lab": True,
                "non_production": True,
                "attempt": int(getattr(stage, "attempt_count", 0) or 0),
                "checkpoint_kind": "provider_attempt",
                "provider_attempted": True,
                "provider_request_id": provider_usage.get("provider_request_id"),
                "transport_kind": provider_usage.get("transport_kind"),
                "http_status": provider_usage.get("http_status"),
                "usage_source": provider_usage.get("usage_source"),
                "output_contract": provider_usage.get("output_contract"),
            },
            append_provider_attempt=_provider_attempt_record(
                module_key=module_key,
                stage_key=stage.stage_key,
                attempt_index=int(getattr(stage, "attempt_count", 0) or 0),
                attempt_kind="initial",
                provider_usage=provider_usage,
                cost_val=cost_val,
                effective_dry_run=effective_dry_run,
                extra={
                    "attempts": list(provider_usage.get("attempts") or []),
                    "provider_error_code": provider_usage.get("provider_error_code"),
                    "provider_error_class": provider_usage.get("provider_error_class"),
                    "validation_started": False,
                    "output_contract": provider_usage.get("output_contract"),
                },
            ),
            **accumulate,
        )

        persistence_summary: dict[str, Any] = {"orm_written": False}
        validation_summary: dict[str, Any] = {"accepted": False, "schema_valid": False}
        evidence_summary: dict[str, Any] = {"validated": False, "count": 0}
        output_fp = usage.output_fingerprint
        pipeline_status = "failed"

        if self._runtime_factory is not None:
            if runtime is None:
                runtime = self._runtime_factory(
                    session=self._session,
                    book_id=int(run.book_id or 0),
                    use_phase1b_persistence=not self._use_recording_persistence,
                    dry_run=effective_dry_run,
                )
            synthetic = dict(usage.structured_output or {})
            evidence_candidates = list(synthetic.get("evidence_candidates") or [])
            try:
                if hasattr(runtime, "bind_session"):
                    runtime.bind_session(self._session)
                if not hasattr(runtime, "build_native_context_bundle"):
                    raise RuntimeError("runtime_missing_context_builder")
                _wb, contract = runtime.build_native_context_bundle(
                    book_id=int(run.book_id or 0),
                    book_snapshot_id=int(run.book_snapshot_id or 0),
                    module_keys=(module_key,),
                )
                from app.narrative_core.private_engine_contract.context import (
                    make_context_bundle_ref,
                )

                # Single source of truth — never invent bundle:{run_id}.
                ref = make_context_bundle_ref(contract.bundle_hash)
                if ref not in getattr(runtime, "contract_bundles", {}):
                    raise PrivateWholeBookLabRunError(
                        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                        run_id=int(run.id),
                        detail_code="CONTEXT_BUNDLE_REF_NOT_REGISTERED",
                    )
                # Persist formal ref into run metadata for resume/audit (no new columns).
                meta["context_bundle_ref"] = ref
                meta["context_bundle_hash"] = str(contract.bundle_hash)
                meta["context_pipeline_version"] = str(
                    getattr(contract, "pipeline_version", "") or ""
                )
                provider_kind = "fake" if not live_requested else str(
                    meta.get("provider_key") or "aliyun_qwen_plus"
                )
                engine_id_hint = self._runtime_engine_id(runtime)
                engine_version_hint = str(
                    getattr(getattr(runtime, "fake_engine", None), "engine_version", "")
                    or "0.1.0-dev"
                )
                # Prefer private runner engine id when bound.
                private_runners = getattr(runtime, "private_runners", None) or {}
                bound_runner = private_runners.get(module_key) or next(
                    iter(private_runners.values()), None
                )
                if bound_runner is not None:
                    engine_id_hint = str(
                        getattr(bound_runner, "engine_id", None) or engine_id_hint
                    )
                    engine_version_hint = str(
                        getattr(bound_runner, "engine_version", None) or engine_version_hint
                    )
                if live_requested:
                    from app.narrative_core.services.provider_backed_module_result import (
                        build_provider_backed_module_result,
                    )

                    try:
                        provider_result = build_provider_backed_module_result(
                            module_key=module_key,
                            structured_output=synthetic,
                            provider_usage=provider_usage,
                            engine_id=engine_id_hint,
                            engine_version=engine_version_hint,
                            provider_key=provider_kind,
                            model_id=str(meta.get("model_id") or provider_usage.get("model_id") or ""),
                        )
                    except ValueError as exc:
                        raise PrivateWholeBookLabRunError(
                            PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                            run_id=int(run.id),
                            detail_code=str(exc.args[0] if exc.args else "PROVIDER_RESULT_BINDING_FAILED"),
                        ) from exc
                    provider_policy = provider_result.to_provider_policy()
                    if output_fp is None or not str(output_fp).strip():
                        output_fp = provider_result.output_fingerprint
                    # CHG-058: bind V2 schema label + catalog into private mapper channel.
                    structured_pol = dict(
                        provider_policy.get("provider_structured_output") or {}
                    )
                    if str(structured_pol.get("contract_version") or "").lower() == "v2" or any(
                        isinstance(structured_pol.get(f), dict)
                        and "citation_ids" in (structured_pol.get(f) or {})
                        for f in (
                            "logline",
                            "premise",
                            "central_question",
                            "primary_conflict",
                            "structure_summary",
                            "ending_state",
                        )
                    ):
                        structured_pol.setdefault("schema", "BookOverviewResultV2")
                        structured_pol.setdefault("contract_version", "v2")
                        provider_policy["provider_structured_output"] = structured_pol
                        provider_policy["evidence_contract_version"] = "v2"
                        if context_bundle_hash:
                            provider_policy["context_bundle_hash"] = context_bundle_hash
                        if citation_paragraph_units:
                            provider_policy["citation_paragraph_units"] = list(
                                citation_paragraph_units
                            )
                        if allowed_citation_ids:
                            provider_policy["allowed_citation_ids"] = list(
                                allowed_citation_ids
                            )
                        if citation_catalog is not None:
                            provider_policy["citation_catalog"] = citation_catalog
                else:
                    # Dry / non-live: fixture channel retained for lab harnesses.
                    provider_policy = {
                        "provider_kind": provider_kind,
                        "model_route": "lab-route",
                        "synthetic_output": synthetic or {"synthetic": True, "partial": True},
                        "evidence_candidates": evidence_candidates,
                    }
                pipeline = runtime.execute_module_pipeline(
                    module_key=WholeBookModuleKey(module_key),
                    book_id=int(run.book_id or 0),
                    book_snapshot_id=int(run.book_snapshot_id or 0),
                    run_id=int(run.id),
                    run_stage_id=int(stage.id),
                    context_bundle_ref=str(ref),
                    configuration_fingerprint_value=str(
                        meta.get("configuration_fingerprint") or "private-lab-cfg"
                    ),
                    provider_policy=provider_policy,
                    analysis_mode=WholeBookAnalysisMode(
                        str(meta.get("analysis_mode") or "native")
                    ),
                    persist=True,
                )
                pipeline_status = str(getattr(pipeline, "status", "") or "")
                validation_summary = dict(getattr(pipeline, "validation", {}) or {})
                coverage = dict(getattr(pipeline, "evidence_coverage", {}) or {})
                cand = dict(getattr(pipeline, "candidate_summary", {}) or {})
                persist = dict(cand.get("persist") or {})
                engine_result = getattr(pipeline, "engine_result", None)
                engine_id = str(getattr(engine_result, "engine_id", "") or self._runtime_engine_id(runtime))
                pipeline_synthetic = bool(getattr(pipeline, "synthetic", False)) or bool(
                    (getattr(engine_result, "module_outputs", {}) or {}).get("synthetic", False)
                )
                engine_kind = classify_live_engine_kind(
                    engine_id=engine_id,
                    private_modules_bound=bool(getattr(runtime, "private_modules_bound", False)),
                    synthetic=pipeline_synthetic,
                )
                persistence_summary = {
                    "orm_written": bool(persist.get("orm_written")),
                    "persistence_complete": bool(persist.get("persistence_complete")),
                    "candidate_written": bool(persist.get("candidate_written")),
                    "evidence_written": bool(persist.get("evidence_written")),
                    "artifact_written": bool(persist.get("artifact_written")),
                    "fallback": persist.get("fallback") or persist.get("fallback_used"),
                    "fallback_used": bool(persist.get("fallback_used") or persist.get("fallback")),
                    "asset_count": persist.get("asset_count")
                    if persist.get("asset_count") is not None
                    else cand.get("asset_count"),
                    "evidence_count": persist.get("evidence_count"),
                    "rejected": bool(cand.get("rejected")),
                    "context_bundle_ref": ref,
                    "engine_id": engine_id,
                    "engine_kind": engine_kind.value,
                    "synthetic": pipeline_synthetic,
                }
                pipeline_diagnostics = dict(getattr(pipeline, "pipeline_diagnostics", {}) or {})
                if pipeline_diagnostics:
                    persistence_summary["pipeline_diagnostics"] = pipeline_diagnostics
                    # Safe stage checkpoint so failures remain diagnosable without Migration.
                    # Merge into pipeline_diagnostics namespace — do not wipe provider_attempts.
                    self._stages.write_checkpoint(
                        int(run.id),
                        stage.stage_key,
                        {
                            "schema": "narrative_run_stage_checkpoint",
                            "version": "1",
                            "stage_key": stage.stage_key,
                            "module_key": module_key,
                            "checkpoint_kind": "pipeline_diagnostics",
                            "private_lab": True,
                            "non_production": True,
                            "pipeline_diagnostics": pipeline_diagnostics,
                            "persistence_summary": {
                                "orm_written": persistence_summary.get("orm_written"),
                                "persistence_complete": persistence_summary.get(
                                    "persistence_complete"
                                ),
                                "engine_kind": persistence_summary.get("engine_kind"),
                            },
                            "provider_request_id": provider_usage.get("provider_request_id"),
                            "transport_kind": provider_usage.get("transport_kind"),
                        },
                    )
                ev_count = len(getattr(engine_result, "evidence_candidates", ()) or ())
                if ev_count == 0:
                    ev_count = int(coverage.get("evidenced_claims") or 0)
                evidence_summary = {
                    "validated": bool(validation_summary.get("evidence_valid", False)),
                    "count": int(ev_count),
                    "coverage_incomplete": bool(coverage.get("incomplete", False)),
                }
                if getattr(pipeline, "output_fingerprint", None):
                    output_fp = str(pipeline.output_fingerprint)
                elif getattr(engine_result, "output_fingerprint", None):
                    output_fp = str(engine_result.output_fingerprint)
                if live_requested and (
                    pipeline_synthetic
                    or is_fake_or_test_engine_id(engine_id)
                    or engine_kind != LiveEngineKind.PRIVATE_REAL
                ):
                    raise PrivateWholeBookLabRunError(
                        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                        run_id=int(run.id),
                        detail_code="LIVE_SYNTHETIC_ARTIFACT_FORBIDDEN",
                    )
                # Live path: never accept port_only / recording fallback / artifact-only.
                if live_requested and (
                    persist.get("fallback") == "port_only"
                    or persist.get("fallback_used")
                    or self._use_recording_persistence
                    or not persist.get("persistence_complete")
                    or not persist.get("orm_written")
                    or not persist.get("candidate_written")
                ):
                    raise PrivateWholeBookLabRunError(
                        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                        run_id=int(run.id),
                        detail_code="LIVE_ORM_PERSISTENCE_REQUIRED",
                    )
            except PrivateWholeBookLabRunError:
                raise
            except Exception as exc:  # noqa: BLE001
                if live_requested:
                    detail = getattr(exc, "args", ("",))[0]
                    code = str(detail) if detail else f"LIVE_PIPELINE_FAILED:{type(exc).__name__}"
                    raise PrivateWholeBookLabRunError(
                        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                        run_id=int(run.id),
                        detail_code=code,
                    ) from exc
                # Dry-only: Port-only synthetic result (still no HTTP).
                persistence_summary = {
                    "orm_written": False,
                    "fallback": "port_only",
                    "detail": type(exc).__name__,
                }
                validation_summary = {"accepted": True, "schema_valid": True, "dry_fallback": True}
                evidence_summary = {"validated": True, "count": 0}

        if live_requested:
            self._assert_live_module_success(
                usage_status=usage.status,
                usage=provider_usage,
                validation_summary=validation_summary,
                evidence_summary=evidence_summary,
                persistence_summary=persistence_summary,
                pipeline_status=pipeline_status,
                run_id=int(run.id),
            )

        self._stages.write_checkpoint(
            int(run.id),
            stage.stage_key,
            {
                "schema": "narrative_run_stage_checkpoint",
                "version": "1",
                "stage_key": stage.stage_key,
                "module_key": module_key,
                "output_fingerprint": output_fp,
                "private_lab": True,
                "non_production": True,
                "attempt": int(getattr(stage, "attempt_count", 0) or 0),
                "provider_request_id": provider_usage.get("provider_request_id"),
                "transport_kind": provider_usage.get("transport_kind"),
                "http_status": provider_usage.get("http_status"),
                "usage_source": provider_usage.get("usage_source"),
            },
            **accumulate,
        )

        return {
            "module_key": module_key,
            "stage_key": stage.stage_key,
            "run_stage_id": int(stage.id),
            "status": "success" if (not live_requested or usage.status == "success") else usage.status,
            "output_fingerprint": output_fp,
            "usage": dict(provider_usage),
            "validation_summary": validation_summary,
            "evidence_summary": evidence_summary,
            "persistence_summary": dict(persistence_summary),
            "raw_response_absent": True,
            "prompt_absent": True,
            "credential_absent": True,
            "http": bool(provider_usage.get("http")),
            "private_lab": True,
            "non_production": True,
            "candidate_only": True,
            "auto_canonical": False,
            "auto_lock": False,
        }

    @staticmethod
    def _runtime_engine_id(runtime: Any) -> str:
        private = getattr(runtime, "private_runners", None) or {}
        for runner in private.values():
            engine_id = str(getattr(runner, "engine_id", "") or "")
            if engine_id:
                return engine_id
        if bool(getattr(runtime, "private_modules_bound", False)):
            for runner in (getattr(runtime, "module_runners", {}) or {}).values():
                delegate = getattr(runner, "private_runner", None) or getattr(
                    runner, "_private_runner", None
                )
                if delegate is not None:
                    engine_id = str(getattr(delegate, "engine_id", "") or "")
                    if engine_id:
                        return engine_id
        fake = getattr(runtime, "fake_engine", None)
        if fake is not None:
            return str(getattr(fake, "engine_id", "") or "")
        return ""

    def _assert_live_module_success(
        self,
        *,
        usage_status: str,
        usage: Mapping[str, Any],
        validation_summary: Mapping[str, Any],
        evidence_summary: Mapping[str, Any],
        persistence_summary: Mapping[str, Any],
        pipeline_status: str,
        run_id: int,
    ) -> None:
        def _fail(code: str) -> None:
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                run_id=run_id,
                detail_code=code,
            )

        if usage_status != "success":
            _fail(f"LIVE_PROVIDER_STATUS_{usage_status.upper()}")
        if usage.get("transport_kind") == "CAPTURING_TEST":
            _fail("LIVE_CAPTURING_TRANSPORT")
        if not usage.get("provider_request_id"):
            _fail("LIVE_PROVIDER_REQUEST_ID_MISSING")
        if not usage.get("live_request_confirmed"):
            _fail("LIVE_REQUEST_NOT_CONFIRMED")
        if usage.get("synthetic_success"):
            _fail("LIVE_SYNTHETIC_SUCCESS_FORBIDDEN")
        if not validation_summary.get("accepted"):
            _fail("LIVE_VALIDATION_NOT_ACCEPTED")
        if int(evidence_summary.get("count") or 0) < 1:
            _fail("LIVE_EVIDENCE_REQUIRED")
        if evidence_summary.get("coverage_incomplete"):
            _fail("LIVE_EVIDENCE_COVERAGE_INCOMPLETE")
        if not persistence_summary.get("orm_written"):
            _fail("LIVE_ORM_WRITTEN_REQUIRED")
        if persistence_summary.get("persistence_complete") is False:
            _fail("LIVE_PERSISTENCE_INCOMPLETE")
        if persistence_summary.get("candidate_written") is False:
            _fail("LIVE_CANDIDATE_REQUIRED")
        if persistence_summary.get("evidence_written") is False:
            _fail("LIVE_EVIDENCE_ORM_REQUIRED")
        if persistence_summary.get("fallback") or persistence_summary.get("fallback_used"):
            _fail("LIVE_PERSISTENCE_FALLBACK_FORBIDDEN")
        if pipeline_status in {"failed", "cancelled"}:
            _fail(f"LIVE_PIPELINE_{pipeline_status.upper()}")
        engine_kind = persistence_summary.get("engine_kind")
        if engine_kind is not None and engine_kind != LiveEngineKind.PRIVATE_REAL.value:
            _fail("LIVE_ENGINE_KIND_NOT_PRIVATE_REAL")
        if persistence_summary.get("synthetic") is True:
            _fail("LIVE_SYNTHETIC_ARTIFACT_FORBIDDEN")

    def _cancel_terminal(
        self,
        run: AnalysisRun,
        meta: dict[str, Any],
        results: list[dict[str, Any]],
        cancellation_ref: str | None,
    ) -> PrivateLabExecutorActionResult:
        try:
            result = self._state.transition(
                run,
                to_state=WholeBookRunViewStatus.CANCELLED,
                expected_state=map_db_status_to_view(str(run.status)),
                expected_version=int(meta.get("state_version", 0) or 0),
                metadata=meta,
                operation_idempotency_key="executor_cancel",
            )
            meta["state_version"] = result.version
            run.validated_output = serialize_metadata(
                meta, existing_validated_output=run.validated_output
            )
        except Exception:  # noqa: BLE001
            run.status = RunStatus.CANCELLED.value
        for stage in self._stages.get_run_stages(int(run.id)):
            if StageStatus(stage.status) in (
                StageStatus.PENDING,
                StageStatus.RUNNING,
                StageStatus.PAUSED,
                StageStatus.INTERRUPTED,
            ):
                try:
                    self._stages.transition_stage(
                        int(run.id), stage.stage_key, StageStatus.CANCELLED
                    )
                except Exception:  # noqa: BLE001
                    pass
        self._registry.mark_finished(int(run.id))
        self._concurrency.note_run_status(int(run.id), WholeBookRunViewStatus.CANCELLED.value)
        self._session.commit()
        return PrivateLabExecutorActionResult(
            run_id=int(run.id),
            status=WholeBookRunViewStatus.CANCELLED.value,
            applied=True,
            detail={
                "module_results": results,
                "partial": True,
                "cancellation_ref": cancellation_ref,
            },
        )

    def _require(self, run_id: int) -> tuple[AnalysisRun, dict[str, Any]]:
        run = self._session.get(AnalysisRun, int(run_id))
        if run is None or not is_private_lab_run_metadata(run.validated_output):
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_NOT_PRIVATE_RUN,
                run_id=run_id,
            )
        return run, parse_metadata_json(run.validated_output)


__all__ = [
    "PrivateLabExecutorActionResult",
    "PrivateLabRunExecutor",
]
