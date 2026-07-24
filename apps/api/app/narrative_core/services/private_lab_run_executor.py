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

        # Live must have ORM persistence capability before any Provider call.
        if live_requested:
            if self._use_recording_persistence or self._runtime_factory is None:
                raise PrivateWholeBookLabRunError(
                    PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                    run_id=int(run.id),
                    detail_code="LIVE_PERSISTENCE_CAPABILITY_MISSING",
                )

        usage = self._provider.execute_module(
            module_key=module_key,
            request={
                "run_id": int(run.id),
                "book_id": int(run.book_id or 0),
                "book_snapshot_id": int(run.book_snapshot_id or 0),
                "configuration_fingerprint": meta.get("configuration_fingerprint"),
                "dry_run": bool(meta.get("dry_run", True)),
                "consent_valid": True,
                "estimate_valid": True,
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
            raise PrivateWholeBookLabRunError(
                PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                run_id=int(run.id),
                detail_code=f"MODULE_{str(usage.status).upper()}",
            )

        persistence_summary: dict[str, Any] = {"orm_written": False}
        validation_summary: dict[str, Any] = {"accepted": False, "schema_valid": False}
        evidence_summary: dict[str, Any] = {"validated": False, "count": 0}
        output_fp = usage.output_fingerprint
        pipeline_status = "failed"

        if self._runtime_factory is not None:
            runtime = self._runtime_factory(
                session=self._session,
                book_id=int(run.book_id or 0),
                use_phase1b_persistence=not self._use_recording_persistence,
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
                ref = getattr(contract, "context_bundle_ref", None) or f"bundle:{run.id}"
                provider_kind = "fake" if not live_requested else str(
                    meta.get("provider_key") or "aliyun_qwen_plus"
                )
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
                    provider_policy={
                        "provider_kind": provider_kind,
                        "model_route": "lab-route",
                        "synthetic_output": synthetic or {"synthetic": True, "partial": True},
                        "evidence_candidates": evidence_candidates,
                    },
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
                persistence_summary = {
                    "orm_written": bool(persist.get("orm_written")),
                    "fallback": persist.get("fallback"),
                    "asset_count": persist.get("asset_count") or cand.get("asset_count"),
                    "evidence_count": persist.get("evidence_count"),
                    "rejected": bool(cand.get("rejected")),
                }
                engine_result = getattr(pipeline, "engine_result", None)
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
                # Live path: never accept port_only / recording fallback.
                if live_requested and (
                    persist.get("fallback") == "port_only"
                    or self._use_recording_persistence
                    or not persist.get("orm_written")
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
                    raise PrivateWholeBookLabRunError(
                        PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_OPERATION_NOT_ALLOWED,
                        run_id=int(run.id),
                        detail_code=f"LIVE_PIPELINE_FAILED:{type(exc).__name__}",
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
                usage=dict(usage.usage),
                validation_summary=validation_summary,
                evidence_summary=evidence_summary,
                persistence_summary=persistence_summary,
                pipeline_status=pipeline_status,
                run_id=int(run.id),
            )

        # Bind usage onto AnalysisRunStage (accumulate).
        token_in = int(usage.usage.get("input_tokens") or 0)
        token_out = int(usage.usage.get("output_tokens") or 0)
        cost_val = usage.usage.get("actual_cost")
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
                "output_fingerprint": output_fp,
                "private_lab": True,
                "non_production": True,
                "attempt": int(getattr(stage, "attempt_count", 0) or 0),
                "provider_request_id": usage.usage.get("provider_request_id"),
                "transport_kind": usage.usage.get("transport_kind"),
                "http_status": usage.usage.get("http_status"),
                "usage_source": usage.usage.get("usage_source"),
            },
            **accumulate,
        )

        return {
            "module_key": module_key,
            "stage_key": stage.stage_key,
            "run_stage_id": int(stage.id),
            "status": "success" if (not live_requested or usage.status == "success") else usage.status,
            "output_fingerprint": output_fp,
            "usage": dict(usage.usage),
            "validation_summary": validation_summary,
            "evidence_summary": evidence_summary,
            "persistence_summary": dict(persistence_summary),
            "raw_response_absent": True,
            "prompt_absent": True,
            "credential_absent": True,
            "http": bool(usage.usage.get("http")),
            "private_lab": True,
            "non_production": True,
            "candidate_only": True,
            "auto_canonical": False,
            "auto_lock": False,
        }

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
        if persistence_summary.get("fallback"):
            _fail("LIVE_PERSISTENCE_FALLBACK_FORBIDDEN")
        if pipeline_status in {"failed", "cancelled"}:
            _fail(f"LIVE_PIPELINE_{pipeline_status.upper()}")

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
