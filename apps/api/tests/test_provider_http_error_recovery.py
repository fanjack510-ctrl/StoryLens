# -*- coding: utf-8 -*-
"""Provider HTTP error structure, retry policy, and boundary recovery feedback."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from app.db.models import AnalysisRun, ApplicationSetting, Book, Chapter, Paragraph
from app.model_gateway.base import ProviderRequestError
from app.model_gateway.provider_errors import (
    ERROR_CATEGORY_AUTHENTICATION,
    ERROR_CATEGORY_INVALID_REQUEST,
    ERROR_CATEGORY_RATE_LIMITED,
    ERROR_CATEGORY_SERVER,
    NON_RETRYABLE_HTTP_STATUSES,
    RETRYABLE_HTTP_STATUSES,
    build_provider_http_error_snapshot,
    categorize_provider_error,
    extract_provider_error_fields,
    is_retryable,
    safe_message,
)
from app.model_gateway.transport_retry import (
    TransportRetryPolicy,
    compute_provider_retry_delay_seconds,
    should_retry_provider_error,
)
from app.services.analysis_recovery_center import (
    MAX_AUTO_PROVIDER_RECOVERY_ATTEMPTS,
    MAX_MANUAL_RECOVERY_ATTEMPTS,
    build_recovery_plan,
    execute_unified_recover,
)
from app.schemas.analysis_recovery import AnalysisRecoverRequest
from app.services.run_scoped_budget_auth import (
    load_unified_recover_marker,
    store_unified_recover_marker,
)
from app.schemas.settings import CloudBudgetUpdate
from app.model_gateway.registry import get_model_gateway
from app.services.credentials.service import get_credential_store


@pytest.mark.parametrize("status", sorted(NON_RETRYABLE_HTTP_STATUSES))
def test_non_retryable_http_statuses(status: int) -> None:
    assert is_retryable("http_error", http_status=status) is False
    err = ProviderRequestError("x", status, transport_kind="http_error", retryable=None)
    assert should_retry_provider_error(err) is False


@pytest.mark.parametrize("status", sorted(RETRYABLE_HTTP_STATUSES))
def test_retryable_http_statuses(status: int) -> None:
    assert is_retryable("http_error", http_status=status) is True
    err = ProviderRequestError("x", status, transport_kind="http_error", retryable=None)
    assert should_retry_provider_error(err) is True


def test_error_categories_for_http() -> None:
    assert categorize_provider_error("http_error", http_status=400) == ERROR_CATEGORY_INVALID_REQUEST
    assert categorize_provider_error("authentication_failed", http_status=401) == ERROR_CATEGORY_AUTHENTICATION
    assert categorize_provider_error("http_error", http_status=429) == ERROR_CATEGORY_RATE_LIMITED
    assert categorize_provider_error("http_error", http_status=503) == ERROR_CATEGORY_SERVER


def test_snapshot_redacts_secrets_and_keeps_nulls() -> None:
    req = httpx.Request("POST", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
    resp = httpx.Response(
        429,
        request=req,
        headers={"content-type": "application/json", "Retry-After": "3"},
        content=json.dumps(
            {
                "error": {
                    "code": "Throttling.RateQuota",
                    "message": "Too many requests Bearer sk-secretKEY url https://evil.example/a",
                    "request_id": "req-abc-1",
                }
            }
        ).encode(),
    )
    snap = build_provider_http_error_snapshot(
        http_status=429,
        transport_kind="http_error",
        endpoint_host="dashscope.aliyuncs.com",
        response=resp,
        retry_after=3.0,
    )
    assert snap["http_status"] == 429
    assert snap["provider_error_code"] == "Throttling.RateQuota"
    assert snap["provider_request_id"] == "req-abc-1"
    assert snap["endpoint_host"] == "dashscope.aliyuncs.com"
    assert snap["error_category"] == ERROR_CATEGORY_RATE_LIMITED
    assert snap["retryable"] is True
    assert snap["retry_after"] == 3.0
    assert "sk-secret" not in (snap["provider_message"] or "")
    assert "evil.example" not in (snap["sanitized_response_excerpt"] or "")
    assert "Bearer" not in (snap["provider_message"] or "") or "[REDACTED]" in (
        snap["provider_message"] or ""
    )
    assert "Authorization" not in json.dumps(snap)
    assert snap["occurred_at"]


def test_extract_missing_fields_stay_null() -> None:
    req = httpx.Request("POST", "https://example.com/v1/chat/completions")
    resp = httpx.Response(500, request=req, content=b"not-json")
    fields = extract_provider_error_fields(resp)
    assert fields["provider_error_code"] is None
    assert fields["provider_request_id"] is None


def test_retry_after_respected_in_backoff() -> None:
    delay = compute_provider_retry_delay_seconds(
        1,
        TransportRetryPolicy(delay_1_min_seconds=2, delay_1_max_seconds=2),
        retry_after=10.0,
    )
    assert delay == 10.0


def test_auto_retry_cap_constant() -> None:
    assert MAX_AUTO_PROVIDER_RECOVERY_ATTEMPTS == 3
    assert MAX_MANUAL_RECOVERY_ATTEMPTS == 5


def _seed_boundary_failed(session, *, http_status: int, retryable: bool) -> AnalysisRun:
    book = Book(title="t", source_file_name="t.txt", source_file_hash="h" * 64)
    session.add(book)
    session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=1, title="c1", section_type="chapter")
    session.add(chapter)
    session.flush()
    session.add(
        Paragraph(
            id="B0001-C0001-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="hello",
            normalized_text="hello",
            char_start=0,
            char_end=5,
        )
    )
    category = categorize_provider_error("http_error", http_status=http_status)
    snap = build_provider_http_error_snapshot(
        http_status=http_status,
        transport_kind="http_error",
        endpoint_host="dashscope.aliyuncs.com",
        retryable=retryable,
    )
    failure = {
        "error_code": "PROVIDER_HTTP_ERROR",
        "failed_stage": "provider_request",
        "retryable": retryable,
        "http_status": http_status,
        "error_category": category,
        "http_error_snapshot": snap,
        "provider_error": {
            "error_code": "PROVIDER_HTTP_ERROR",
            "http_status": http_status,
            "retryable": retryable,
            "error_category": category,
            "message": f"HTTP {http_status}",
        },
    }
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        prompt_hash="x",
        input_hash="x",
        status="failed_provider",
        error_code="SCENE_PIPELINE_FAILED",
        root_error_code="PROVIDER_HTTP_ERROR",
        failed_stage="provider_request",
        retryable=retryable,
        analysis_mode="assisted_boundary_review",
        provider_health_at_failure=json.dumps(
            {"health": {"status": "healthy"}, "failure": failure}, ensure_ascii=False
        ),
    )
    session.add(run)
    session.merge(
        ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True))
    )
    payload = CloudBudgetUpdate().model_dump()
    payload["cloud_daily_request_limit"] = 100
    session.merge(
        ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload))
    )
    session.commit()
    return run


def test_recovery_plan_boundary_copy_not_journey_root(testing_session) -> None:
    run = _seed_boundary_failed(testing_session, http_status=429, retryable=True)
    gateway = get_model_gateway()
    store = get_credential_store()
    plan = build_recovery_plan(testing_session, run, gateway, store)
    assert plan.resume_stage == "boundary_detection"
    assert plan.details.get("http_status") == 429
    assert plan.details.get("error_category") == ERROR_CATEGORY_RATE_LIMITED
    user_error = plan.details.get("user_error") or {}
    assert user_error.get("title") == "场景边界识别请求失败"
    assert "阅读旅程未到阶段" not in json.dumps(plan.model_dump(), ensure_ascii=False)
    labels = [c.user_label for c in plan.checks]
    assert any(c and "场景边界识别" in c for c in labels)
    assert any(a.action == "fix_and_continue" for a in plan.recommended_actions)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_recovery_plan_non_retryable_no_blind_continue(testing_session, status: int) -> None:
    run = _seed_boundary_failed(testing_session, http_status=status, retryable=False)
    gateway = get_model_gateway()
    store = get_credential_store()
    plan = build_recovery_plan(testing_session, run, gateway, store)
    assert plan.details.get("provider_not_retryable") is True
    assert not any(a.action == "fix_and_continue" for a in plan.recommended_actions)
    assert any(a.action == "check_model_config" for a in plan.recommended_actions)


def test_manual_recovery_cap_stops_fix_continue(testing_session) -> None:
    run = _seed_boundary_failed(testing_session, http_status=429, retryable=True)
    store_unified_recover_marker(
        run,
        client_request_id="manual-cap-test-001",
        actions=[],
        resume_stage="boundary_detection",
        recovery_attempts=MAX_MANUAL_RECOVERY_ATTEMPTS,
        manual_recovery_attempts=MAX_MANUAL_RECOVERY_ATTEMPTS,
        auto_recovery_attempts=0,
    )
    testing_session.commit()
    gateway = get_model_gateway()
    store = get_credential_store()
    plan = build_recovery_plan(testing_session, run, gateway, store)
    assert plan.details.get("recovery_exhausted") is True
    assert not any(a.action == "fix_and_continue" for a in plan.recommended_actions)
    assert any(a.action == "revalidate_ai_service" for a in plan.recommended_actions)


def test_execute_recover_boundary_calls_callback_once(testing_session) -> None:
    run = _seed_boundary_failed(testing_session, http_status=429, retryable=True)
    gateway = get_model_gateway()
    store = get_credential_store()
    calls: list[int] = []

    def _resume() -> int:
        calls.append(1)
        return 99

    resp = execute_unified_recover(
        testing_session,
        run,
        AnalysisRecoverRequest(
            client_request_id="boundary-resume-001",
            cloud_consent=True,
            confirmed=True,
            recovery_mode="unified",
            resume=True,
        ),
        gateway,
        store,
        background_resume_boundary=_resume,
    )
    assert calls == [1]
    assert resp.model_invocations_started is True
    assert "resume_boundary_detection" in resp.actions_executed
    marker = load_unified_recover_marker(run)
    assert marker is not None
    assert int(marker.get("manual_recovery_attempts") or 0) == 1
    assert int(marker.get("recovery_attempts") or 0) == 1


def test_execute_recover_exhausted_does_not_resume(testing_session) -> None:
    run = _seed_boundary_failed(testing_session, http_status=429, retryable=True)
    store_unified_recover_marker(
        run,
        client_request_id="exhausted-001",
        actions=["resume_boundary_detection"],
        resume_stage="boundary_detection",
        recovery_attempts=MAX_MANUAL_RECOVERY_ATTEMPTS,
        manual_recovery_attempts=MAX_MANUAL_RECOVERY_ATTEMPTS,
    )
    testing_session.commit()
    gateway = get_model_gateway()
    store = get_credential_store()
    called = MagicMock(return_value=1)
    resp = execute_unified_recover(
        testing_session,
        run,
        AnalysisRecoverRequest(
            client_request_id="exhausted-002",
            cloud_consent=True,
            confirmed=True,
            recovery_mode="unified",
            resume=True,
        ),
        gateway,
        store,
        background_resume_boundary=called,
    )
    called.assert_not_called()
    assert resp.model_invocations_started is False
    assert resp.details.get("recovery_exhausted") is True


def test_safe_message_never_keeps_api_key() -> None:
    text = safe_message("key=sk-abcdefghijklmnopqrstuv Authorization: Bearer tok", fallback="x")
    assert "sk-abc" not in text
    assert "Bearer tok" not in text
