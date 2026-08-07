"""Minimal window entity/event extraction orchestration (WB-1.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    BookSnapshot,
    WholeBookRun,
    WholeBookWindow,
    WholeBookWindowAnalysisResult,
    utc_now,
)
from app.narrative_core.contracts.whole_book_contract_v1 import (
    WHOLE_BOOK_CONTRACT_VERSION,
    BookSnapshotMetadataV1,
    SnapshotParagraphV1,
    WholeBookMode,
    WholeBookRunStatus,
    WholeBookRunV1,
    WholeBookUnitStatus,
    WholeBookWindowAnalysisRequestV1,
    WholeBookWindowAnalysisResponseV1,
    WholeBookWindowV1,
)
from app.narrative_core.services.fixture_window_analysis_sample_s import (
    build_fixture_window_analysis_response_v1,
    build_fixture_window_payload_from_request_dict,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (
    FIXTURE_ENGINE_ID,
    FIXTURE_ENGINE_VERSION,
    FIXTURE_PROMPT_VERSION,
    assert_run_not_terminal,
    build_run_contract_dict,
    build_window_contract_dict,
    ensure_fixture_consent,
    get_stage,
    load_window_paragraph_dicts,
    set_stage_completed,
    set_stage_running,
    snapshot_metadata_dict,
)
from app.narrative_core.services.whole_book_native_input_audit_v1 import (
    assert_native_input_independence_v1,
    persist_native_input_audit_v1,
)
from app.narrative_core.services.whole_book_runtime_control_v1_service import should_stop_claiming_units
from app.narrative_core.services.whole_book_provider_orchestrator import (
    CountingFakeWholeBookProvider,
    ProviderCallResult,
    UNIT_WINDOW,
    WholeBookProviderOrchestrator,
    WholeBookProviderTransport,
    stable_request_hash,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run, start_whole_book_run_v1
from app.narrative_core.services.whole_book_window_response_validation_v1 import (
    validate_window_response_against_snapshot_v1,
)
from app.narrative_core.services.whole_book_windowing_v1_service import (
    calculate_window_coverage_v1,
    list_windows,
)


@dataclass
class FixtureWindowAnalysisTransport:
    """CountingFake adapter that emits Sample S fixture responses."""

    inner: CountingFakeWholeBookProvider = field(default_factory=CountingFakeWholeBookProvider)

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        if unit_type != UNIT_WINDOW:
            return self.inner.invoke(
                unit_key=unit_key, unit_type=unit_type, request_payload=request_payload
            )
        try:
            payload = build_fixture_window_payload_from_request_dict(request_payload)
        except Exception as exc:
            return ProviderCallResult(
                ok=False,
                error_code="FIXTURE_BUILD_FAILED",
                error_message_safe=str(exc)[:500],
            )
        return ProviderCallResult(ok=True, result_payload=payload)


def _build_window_request(
    session: Session,
    run: WholeBookRun,
    snapshot: BookSnapshot,
    window: WholeBookWindow,
) -> WholeBookWindowAnalysisRequestV1:
    paragraph_dicts = load_window_paragraph_dicts(
        session,
        snapshot_id=snapshot.id,
        first_global=window.first_global_paragraph_index,
        last_global=window.last_global_paragraph_index,
    )
    return WholeBookWindowAnalysisRequestV1(
        run=WholeBookRunV1.model_validate(build_run_contract_dict(run)),
        snapshot=BookSnapshotMetadataV1.model_validate(snapshot_metadata_dict(session, snapshot.id)),
        window=WholeBookWindowV1.model_validate(build_window_contract_dict(window, run)),
        paragraphs=[SnapshotParagraphV1.model_validate(item) for item in paragraph_dicts],
        existing_confirmed_entities=[],
        existing_confirmed_assets=[],
    )


def _persist_window_result(
    session: Session,
    *,
    run: WholeBookRun,
    snapshot: BookSnapshot,
    window: WholeBookWindow,
    response: WholeBookWindowAnalysisResponseV1,
    validation_status: str,
    warning_count: int,
) -> WholeBookWindowAnalysisResult:
    blob = json.dumps(response.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    response_hash = stable_request_hash({"response": response.model_dump(mode="json")})
    existing = session.scalar(
        select(WholeBookWindowAnalysisResult).where(
            WholeBookWindowAnalysisResult.run_id == run.id,
            WholeBookWindowAnalysisResult.window_id == window.id,
        )
    )
    if existing is None:
        row = WholeBookWindowAnalysisResult(
            run_id=run.id,
            window_id=window.id,
            snapshot_id=snapshot.id,
            contract_version=WHOLE_BOOK_CONTRACT_VERSION,
            engine_id=FIXTURE_ENGINE_ID,
            engine_version=FIXTURE_ENGINE_VERSION,
            prompt_version=FIXTURE_PROMPT_VERSION,
            result_origin=run.result_origin,
            response_json=blob,
            response_hash=response_hash,
            validation_status=validation_status,
            warning_count=warning_count,
            created_at=utc_now(),
        )
        session.add(row)
    else:
        existing.response_json = blob
        existing.response_hash = response_hash
        existing.validation_status = validation_status
        existing.warning_count = warning_count
        row = existing
    session.flush()
    return row


def execute_minimal_entity_event_extraction_v1(
    session: Session,
    run_id: int,
    transport: WholeBookProviderTransport | None = None,
) -> dict[str, Any]:
    if transport is None:
        transport = FixtureWindowAnalysisTransport()
    run = assert_run_not_terminal(session, run_id)
    if run.mode != WholeBookMode.whole_book_native.value:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            "minimal extraction requires whole_book_native mode",
        )
    if run.snapshot_id is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"run {run_id} has no snapshot",
        )
    snapshot = session.get(BookSnapshot, run.snapshot_id)
    if snapshot is None or snapshot.snapshot_status != "completed":
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_COMPLETED,
            f"snapshot not completed for run {run_id}",
        )
    windows = list_windows(session, run_id)
    if not windows:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            "window set missing",
        )
    coverage = calculate_window_coverage_v1(
        session, snapshot_id=snapshot.id, run_id=run_id, windows=windows
    )
    if coverage["coverage_ratio"] != 1.0:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_WINDOW_SET_CONFLICT,
            "window coverage must be 100%",
        )

    if run.status == WholeBookRunStatus.pending.value:
        start_whole_book_run_v1(session, run_id)
        session.refresh(run)

    audit = assert_native_input_independence_v1(session, run_id)
    persist_native_input_audit_v1(session, audit)

    consent_id = ensure_fixture_consent(session, run)
    set_stage_running(session, run_id, "extract_entities_events")
    run.current_stage_code = "extract_entities_events"
    session.flush()

    orch = WholeBookProviderOrchestrator(
        session,
        engine_version=FIXTURE_ENGINE_VERSION,
        prompt_version=FIXTURE_PROMPT_VERSION,
    )

    completed_windows = 0
    failed_windows = 0
    valid_count = 0
    invalid_count = 0
    provider_calls = 0

    for window in windows:
        if should_stop_claiming_units(session, run_id):
            session.refresh(run)
            break

        request = _build_window_request(session, run, snapshot, window)
        request_payload = request.model_dump(mode="json")
        unit_key = f"window:{window.id}"
        unit_result = orch.execute_provider_unit(
            run_id=run.id,
            stage_code="extract_entities_events",
            unit_type=UNIT_WINDOW,
            unit_key=unit_key,
            request_payload=request_payload,
            consent_id=consent_id,
            transport=transport,
            window_id=window.id,
        )
        if unit_result.get("status") == "completed" and not unit_result.get("reused"):
            provider_calls += 1
        if unit_result.get("status") == "failed":
            window.status = WholeBookUnitStatus.failed.value
            failed_windows += 1
            continue

        if unit_result.get("status") == "reused":
            existing = session.scalar(
                select(WholeBookWindowAnalysisResult).where(
                    WholeBookWindowAnalysisResult.run_id == run.id,
                    WholeBookWindowAnalysisResult.window_id == window.id,
                    WholeBookWindowAnalysisResult.validation_status == "valid",
                )
            )
            if existing is not None:
                window.status = WholeBookUnitStatus.completed.value
                completed_windows += 1
                valid_count += 1
                continue

        # Build/validate response from transport for fresh calls.
        if isinstance(transport, FixtureWindowAnalysisTransport):
            response = build_fixture_window_analysis_response_v1(request)
        else:
            payload = unit_result.get("result_payload")
            if not isinstance(payload, dict) or not payload:
                raw = transport.invoke(
                    unit_key=unit_key, unit_type=UNIT_WINDOW, request_payload=request_payload
                )
                if not raw.ok:
                    window.status = WholeBookUnitStatus.failed.value
                    failed_windows += 1
                    continue
                payload = raw.result_payload
            response = WholeBookWindowAnalysisResponseV1.model_validate(payload)

        paragraph_models = request.paragraphs
        validation = validate_window_response_against_snapshot_v1(
            session, run, snapshot, window, paragraph_models, response
        )
        if not validation.valid:
            _persist_window_result(
                session,
                run=run,
                snapshot=snapshot,
                window=window,
                response=response,
                validation_status="invalid",
                warning_count=len(validation.warnings),
            )
            window.status = WholeBookUnitStatus.failed.value
            failed_windows += 1
            invalid_count += 1
            continue

        _persist_window_result(
            session,
            run=run,
            snapshot=snapshot,
            window=window,
            response=response,
            validation_status="valid",
            warning_count=len(validation.warnings),
        )
        window.status = WholeBookUnitStatus.completed.value
        completed_windows += 1
        valid_count += 1

        stage = get_stage(session, run_id, "extract_entities_events")
        if stage is not None:
            stage.progress_current = completed_windows
            stage.progress_total = len(windows)
            session.flush()

        if should_stop_claiming_units(session, run_id):
            session.refresh(run)
            break

    session.flush()

    run = get_run(session, run_id)
    if run.status == WholeBookRunStatus.paused.value:
        return {
            "run_id": run_id,
            "windows_total": len(windows),
            "windows_completed": completed_windows,
            "windows_failed": failed_windows,
            "valid_results": valid_count,
            "invalid_results": invalid_count,
            "provider_calls": provider_calls,
            "current_stage_code": run.current_stage_code,
            "run_status": run.status,
            "paused": True,
        }

    if run.status == WholeBookRunStatus.cancelled.value:
        return {
            "run_id": run_id,
            "windows_total": len(windows),
            "windows_completed": completed_windows,
            "windows_failed": failed_windows,
            "valid_results": valid_count,
            "invalid_results": invalid_count,
            "provider_calls": provider_calls,
            "current_stage_code": run.current_stage_code,
            "run_status": run.status,
            "cancelled": True,
        }

    session.flush()

    if failed_windows == 0 and completed_windows == len(windows):
        set_stage_completed(
            session, run_id, "extract_entities_events", progress_total=len(windows)
        )
        run.current_stage_code = "materialize_assets"
        run.status = WholeBookRunStatus.running.value
    else:
        run.status = WholeBookRunStatus.recoverable.value

    session.flush()
    return {
        "run_id": run_id,
        "windows_total": len(windows),
        "windows_completed": completed_windows,
        "windows_failed": failed_windows,
        "valid_results": valid_count,
        "invalid_results": invalid_count,
        "provider_calls": provider_calls,
        "current_stage_code": run.current_stage_code,
        "run_status": run.status,
    }
