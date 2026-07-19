# -*- coding: utf-8 -*-
"""DEFECT-CANARY-010: journey repair budget + error causality (change v1.0.5)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text

from app.db.models import AnalysisRun, ModelInvocation
from app.model_gateway.base import ProviderRequestError
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.provider_errors import TRANSPORT_REMOTE_DISCONNECT
from app.schemas.scene import SceneBoundaryResult
from app.services.prompt_service import load_prompt
from app.services.structured_output import StructuredOutputError, generate_validated
from app.services.validation_errors import StructuralValidationError
from tests.test_aliyun_provider import CloudFake

ROOT = Path(__file__).resolve().parents[3]
MAIN_DB = ROOT / "data" / "storylens.db"
CANARY_V6 = (
    ROOT
    / "artifacts"
    / "single-chapter-pipeline-certification"
    / "real-canary"
    / "canary-v6.sqlite3"
)
VALID = '{"chapter_id":"B0001-C0001","boundaries":[],"overall_confidence":0.9}'
JOURNEY_PROMPT = load_prompt("reader_journey_scene", "v1.5")
BOUNDARY_PROMPT = load_prompt("scene_boundary")
ATTEMPT2_RESPONSE = (
    ROOT
    / "audits"
    / "single-chapter-pipeline"
    / "real-canary-v6"
    / "defects"
    / "DEFECT-CANARY-010-attempt2-response.json"
)
OOS_MSG = "Evidence paragraph out of scope for current Scene: ['B0001-C0001-P0004']"


def _disconnect() -> ProviderRequestError:
    return ProviderRequestError(
        "Server disconnected without sending a response.",
        http_request_sent=True,
        error_code="PROVIDER_REMOTE_DISCONNECT",
        transport_kind=TRANSPORT_REMOTE_DISCONNECT,
        retryable=True,
        exception_type="RemoteProtocolError",
    )


def make_run(session) -> AnalysisRun:
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v1",
        schema_version="v1",
        prompt_hash="x",
        input_hash="x",
        status="running",
    )
    session.add(run)
    session.commit()
    return run


def _oos_once():
    state = {"n": 0}

    def _biz(_result: SceneBoundaryResult) -> None:
        state["n"] += 1
        if state["n"] == 1:
            raise StructuralValidationError(OOS_MSG, "JOURNEY_EVIDENCE_OUT_OF_SCOPE")

    return _biz


def _oos_always():
    def _biz(_result: SceneBoundaryResult) -> None:
        raise StructuralValidationError(OOS_MSG, "JOURNEY_EVIDENCE_OUT_OF_SCOPE")

    return _biz


@pytest.fixture
def zero_delay_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MIN", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_1_MAX", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MIN", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_RETRY_DELAY_2_MAX", "0")
    monkeypatch.setenv("STORYLENS_ALIYUN_TRANSPORT_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("STORYLENS_ALIYUN_MAX_RETRIES", "3")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _rows(session, run_id: int) -> list[ModelInvocation]:
    return list(
        session.scalars(
            select(ModelInvocation)
            .where(ModelInvocation.run_id == run_id)
            .order_by(ModelInvocation.id)
        )
    )


def test_0_offline_replay_attempt2_oos_is_real():
    assert ATTEMPT2_RESPONSE.exists()
    payload = json.loads(ATTEMPT2_RESPONSE.read_text(encoding="utf-8"))
    assert CANARY_V6.exists()
    con = sqlite3.connect(f"file:{CANARY_V6.as_posix()}?mode=ro", uri=True)
    scenes = {
        r[0]: (r[1], r[2])
        for r in con.execute(
            "SELECT id, start_paragraph_id, end_paragraph_id FROM scenes ORDER BY id"
        )
    }
    paras = [
        r[0]
        for r in con.execute(
            "SELECT id FROM paragraphs WHERE chapter_id=1 ORDER BY paragraph_index"
        )
    ]
    con.close()
    assert scenes[1][0] == "B0001-C0001-P0001"
    assert scenes[1][1] == "B0001-C0001-P0004"
    assert scenes[2][0] == "B0001-C0001-P0005"

    def _range(start: str, end: str) -> set[str]:
        i0 = paras.index(start)
        i1 = paras.index(end)
        return set(paras[i0 : i1 + 1])

    allowed = {1: _range(*scenes[1]), 2: _range(*scenes[2])}
    oos: list[tuple[int, str]] = []
    for profile in payload["profiles"]:
        sid = int(profile["scene_id"])
        for field in (
            "reader_question_created",
            "reader_question_answered",
            "reader_question_out",
            "payoffs",
            "hooks",
            "techniques",
            "emotion_beats",
            "information_changes",
            "character_effects",
        ):
            for item in profile.get(field) or []:
                for pid in item.get("evidence_paragraph_ids") or []:
                    if pid not in allowed.get(sid, set()):
                        oos.append((sid, pid))
        for pid in profile.get("evidence_paragraph_ids") or []:
            if pid not in allowed.get(sid, set()):
                oos.append((sid, pid))
    assert any(sid == 2 and pid == "B0001-C0001-P0004" for sid, pid in oos)


@pytest.mark.asyncio
async def test_1_normal_first_disconnect_second_success(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [_disconnect(), VALID])
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=BOUNDARY_PROMPT,
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=lambda _: None,
    )
    rows = _rows(testing_session, run.id)
    assert [r.invocation_kind for r in rows] == ["initial", "provider_retry"]
    assert rows[0].error_code == "PROVIDER_REMOTE_DISCONNECT"
    assert rows[1].status == "succeeded"
    assert rows[0].request_hash == rows[1].request_hash


@pytest.mark.asyncio
async def test_2_normal_success_but_evidence_oos(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [VALID, VALID])
    run = make_run(testing_session)
    with pytest.raises(StructuredOutputError) as exc:
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([provider]),
            run_id=run.id,
            provider_name=provider.name,
            task_type="reader_journey_scene",
            prompt=JOURNEY_PROMPT,
            schema=SceneBoundaryResult,
            input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
            user_content="task",
            business_validator=_oos_always(),
            initial_invocation_kind="normal_batch_request",
        )
    assert exc.value.error_code == "JOURNEY_REPAIR_VALIDATION_FAILED"
    assert exc.value.primary_error == "JOURNEY_EVIDENCE_OUT_OF_SCOPE"
    rows = _rows(testing_session, run.id)
    assert rows[0].error_code == "JOURNEY_EVIDENCE_OUT_OF_SCOPE"
    assert rows[0].invocation_kind == "normal_batch_request"
    assert any(r.invocation_kind == "structural_repair" for r in rows)


@pytest.mark.asyncio
async def test_3_repair_first_disconnect_second_success(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [VALID, _disconnect(), VALID])
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="reader_journey_scene",
        prompt=JOURNEY_PROMPT,
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=_oos_once(),
        initial_invocation_kind="normal_batch_request",
    )
    rows = _rows(testing_session, run.id)
    kinds = [r.invocation_kind for r in rows]
    assert kinds == ["normal_batch_request", "structural_repair", "repair_provider_retry"]
    assert rows[0].error_code == "JOURNEY_EVIDENCE_OUT_OF_SCOPE"
    assert rows[1].error_code == "PROVIDER_REMOTE_DISCONNECT"
    assert rows[2].status == "succeeded"
    assert rows[1].request_hash == rows[2].request_hash
    assert rows[0].request_hash != rows[1].request_hash


@pytest.mark.asyncio
async def test_4_repair_three_disconnects(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake(
        "aliyun_qwen_plus", [VALID, _disconnect(), _disconnect(), _disconnect()]
    )
    run = make_run(testing_session)
    with pytest.raises(StructuredOutputError) as exc:
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([provider]),
            run_id=run.id,
            provider_name=provider.name,
            task_type="reader_journey_scene",
            prompt=JOURNEY_PROMPT,
            schema=SceneBoundaryResult,
            input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
            user_content="task",
            business_validator=_oos_once(),
            initial_invocation_kind="normal_batch_request",
        )
    assert exc.value.error_code == "JOURNEY_REPAIR_PROVIDER_FAILURE"
    assert exc.value.primary_error == "JOURNEY_EVIDENCE_OUT_OF_SCOPE"
    assert exc.value.transport_error == "PROVIDER_REMOTE_DISCONNECT"
    rows = _rows(testing_session, run.id)
    kinds = [r.invocation_kind for r in rows]
    assert kinds[0] == "normal_batch_request"
    assert kinds[1] == "structural_repair"
    assert kinds[2:] == ["repair_provider_retry", "repair_provider_retry"]
    assert all(
        r.estimated_cost is None
        for r in rows
        if r.error_code == "PROVIDER_REMOTE_DISCONNECT"
    )


@pytest.mark.asyncio
async def test_5_repair_returns_valid_result(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [VALID, VALID])
    run = make_run(testing_session)
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="reader_journey_scene",
        prompt=JOURNEY_PROMPT,
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=_oos_once(),
        initial_invocation_kind="normal_batch_request",
    )
    assert result.boundaries == []
    rows = _rows(testing_session, run.id)
    assert [r.status for r in rows] == ["failed", "succeeded"]
    assert rows[1].invocation_kind == "structural_repair"


@pytest.mark.asyncio
async def test_6_repair_again_evidence_oos(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [VALID, VALID])
    run = make_run(testing_session)
    with pytest.raises(StructuredOutputError) as exc:
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([provider]),
            run_id=run.id,
            provider_name=provider.name,
            task_type="reader_journey_scene",
            prompt=JOURNEY_PROMPT,
            schema=SceneBoundaryResult,
            input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
            user_content="task",
            business_validator=_oos_always(),
            initial_invocation_kind="normal_batch_request",
        )
    assert exc.value.error_code == "JOURNEY_REPAIR_VALIDATION_FAILED"
    assert exc.value.primary_error == "JOURNEY_EVIDENCE_OUT_OF_SCOPE"
    rows = _rows(testing_session, run.id)
    assert len(rows) == 2
    assert rows[1].invocation_kind == "structural_repair"
    assert rows[1].error_code == "JOURNEY_EVIDENCE_OUT_OF_SCOPE"


@pytest.mark.asyncio
async def test_7_normal_and_repair_counters_independent(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake(
        "aliyun_qwen_plus",
        [_disconnect(), VALID, _disconnect(), VALID],
    )
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="reader_journey_scene",
        prompt=JOURNEY_PROMPT,
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=_oos_once(),
        initial_invocation_kind="normal_batch_request",
    )
    rows = _rows(testing_session, run.id)
    kinds = [r.invocation_kind for r in rows]
    assert kinds == [
        "normal_batch_request",
        "provider_retry",
        "structural_repair",
        "repair_provider_retry",
    ]
    assert [r.attempt_no for r in rows] == [1, 2, 1, 2]
    params = [json.loads(r.request_parameters_json) for r in rows]
    assert params[1]["normal_transport_used"] == 2
    assert params[3]["repair_transport_used"] == 2
    assert params[3]["normal_transport_used"] == 2


@pytest.mark.asyncio
async def test_8_total_request_hard_cap_still_effective(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [_disconnect()] * 10)
    run = make_run(testing_session)
    with pytest.raises(StructuredOutputError):
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([provider]),
            run_id=run.id,
            provider_name=provider.name,
            task_type="scene_boundary",
            prompt=BOUNDARY_PROMPT,
            schema=SceneBoundaryResult,
            input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
            user_content="task",
            business_validator=lambda _: None,
        )
    rows = _rows(testing_session, run.id)
    assert len(rows) == 3
    assert all(r.error_code == "PROVIDER_REMOTE_DISCONNECT" for r in rows)


@pytest.mark.asyncio
async def test_9_normal_request_hash_retry_consistent(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [_disconnect(), _disconnect(), VALID])
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=BOUNDARY_PROMPT,
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=lambda _: None,
    )
    hashes = [r.request_hash for r in _rows(testing_session, run.id)]
    assert len(hashes) == 3 and len(set(hashes)) == 1


@pytest.mark.asyncio
async def test_10_repair_request_hash_retry_consistent(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake(
        "aliyun_qwen_plus", [VALID, _disconnect(), _disconnect(), VALID]
    )
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="reader_journey_scene",
        prompt=JOURNEY_PROMPT,
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=_oos_once(),
        initial_invocation_kind="normal_batch_request",
    )
    rows = _rows(testing_session, run.id)
    repair_rows = [
        r
        for r in rows
        if r.invocation_kind in {"structural_repair", "repair_provider_retry"}
    ]
    assert len(repair_rows) == 3
    assert len({r.request_hash for r in repair_rows}) == 1


@pytest.mark.asyncio
async def test_11_normal_and_repair_request_hash_differ(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake("aliyun_qwen_plus", [VALID, VALID])
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="reader_journey_scene",
        prompt=JOURNEY_PROMPT,
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
        user_content="task",
        business_validator=_oos_once(),
        initial_invocation_kind="normal_batch_request",
    )
    rows = _rows(testing_session, run.id)
    assert rows[0].request_hash != rows[1].request_hash
    repair_body = provider.requests[1].messages[1]["content"]
    assert "JOURNEY_EVIDENCE_OUT_OF_SCOPE" in repair_body or "B0001-C0001-P0004" in repair_body
    assert "structural_repair" in repair_body
    assert repair_body != "task"


@pytest.mark.asyncio
async def test_12_primary_and_transport_errors_both_preserved(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    provider = CloudFake(
        "aliyun_qwen_plus", [VALID, _disconnect(), _disconnect(), _disconnect()]
    )
    run = make_run(testing_session)
    with pytest.raises(StructuredOutputError) as exc:
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([provider]),
            run_id=run.id,
            provider_name=provider.name,
            task_type="reader_journey_scene",
            prompt=JOURNEY_PROMPT,
            schema=SceneBoundaryResult,
            input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
            user_content="task",
            business_validator=_oos_once(),
            initial_invocation_kind="normal_batch_request",
        )
    payload = exc.value.as_safe_dict()
    assert payload["error_code"] == "JOURNEY_REPAIR_PROVIDER_FAILURE"
    assert payload["primary_error"] == "JOURNEY_EVIDENCE_OUT_OF_SCOPE"
    assert payload["transport_error"] == "PROVIDER_REMOTE_DISCONNECT"
    assert payload["error_code"] != "PIPELINE_UNEXPECTED_ERROR"


@pytest.mark.asyncio
async def test_13_no_partial_profile_entities(
    testing_session, zero_delay_settings, monkeypatch
):
    monkeypatch.setattr("app.services.structured_output.asyncio.sleep", AsyncMock())
    before_profiles = testing_session.execute(
        text("SELECT COUNT(*) FROM scene_reader_journey_profiles")
    ).scalar()
    before_journeys = testing_session.execute(
        text("SELECT COUNT(*) FROM reader_journey_runs")
    ).scalar()
    provider = CloudFake(
        "aliyun_qwen_plus", [VALID, _disconnect(), _disconnect(), _disconnect()]
    )
    run = make_run(testing_session)
    with pytest.raises(StructuredOutputError):
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([provider]),
            run_id=run.id,
            provider_name=provider.name,
            task_type="reader_journey_scene",
            prompt=JOURNEY_PROMPT,
            schema=SceneBoundaryResult,
            input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "t"}]},
            user_content="task",
            business_validator=_oos_once(),
            initial_invocation_kind="normal_batch_request",
        )
    assert (
        testing_session.execute(
            text("SELECT COUNT(*) FROM scene_reader_journey_profiles")
        ).scalar()
        == before_profiles
    )
    assert (
        testing_session.execute(text("SELECT COUNT(*) FROM reader_journey_runs")).scalar()
        == before_journeys
    )


def test_14_reservations_released_on_canary_v6():
    assert CANARY_V6.exists()
    con = sqlite3.connect(f"file:{CANARY_V6.as_posix()}?mode=ro", uri=True)
    active = con.execute(
        "SELECT COUNT(*) FROM cloud_budget_reservations WHERE status='active'"
    ).fetchone()[0]
    con.close()
    assert active == 0


def test_15_main_db_55_2_unchanged():
    assert MAIN_DB.exists()
    con = sqlite3.connect(f"file:{MAIN_DB.as_posix()}?mode=ro", uri=True)
    ar = con.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
    jr = con.execute("SELECT COUNT(*) FROM reader_journey_runs").fetchone()[0]
    s55 = con.execute("SELECT status FROM analysis_runs WHERE id=55").fetchone()[0]
    j2 = con.execute("SELECT status FROM reader_journey_runs WHERE id=2").fetchone()[0]
    con.close()
    assert ar == 55 and jr == 2
    assert s55 == "succeeded" and j2 == "succeeded"
