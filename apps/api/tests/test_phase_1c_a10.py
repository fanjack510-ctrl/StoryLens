"""Phase 1C-A.10 Scene Analysis resume, runtime assembly, failure persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    ApplicationSetting,
    BoundaryRevision,
    BoundaryReviewSession,
    Book,
    Chapter,
    ModelInvocation,
    Paragraph,
    ProviderConfiguration,
    Scene,
)
from app.model_gateway.base import ProviderRequestError
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.schemas.settings import CloudBudgetUpdate
from app.services.boundary_review_service import analyze_confirmed_review
from app.services.provider_runtime_service import ProviderRuntimeService
from tests.fakes import FakeProvider


def _enable_cloud(session):
    session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    payload = CloudBudgetUpdate().model_dump()
    payload.update(
        {
            "daily_request_limit": 500,
            "daily_token_limit": 2_000_000,
            "daily_cost_limit": 50.0,
        }
    )
    session.merge(
        ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload))
    )
    session.commit()


def _seed_confirmed_run(session, *, scene_count: int = 3):
    book = Book(title="A10", source_file_name="a10.txt", source_file_hash="a" * 64)
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id, chapter_index=1, title="第一章", section_type="chapter"
    )
    session.add(chapter)
    session.flush()
    paragraphs = []
    for index in range(1, scene_count * 2 + 1):
        row = Paragraph(
            id=f"B0001-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=f"段落正文{index}" * 4,
            normalized_text=f"段落正文{index}" * 4,
            char_start=index * 10,
            char_end=index * 10 + 8,
        )
        session.add(row)
        paragraphs.append(row)
    run = AnalysisRun(
        task_type="scene_pipeline",
        provider="fake",
        model="fake-scene-model",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="b" * 64,
        status="failed",
        subject_type="chapter",
        subject_id=str(chapter.id),
        prompt_hash="c" * 64,
        progress_current=1,
        progress_total=1,
        error_code="SCENE_ANALYSIS_FAILED",
        failed_stage="scene_analysis",
        analysis_mode="assisted_boundary_review",
        execution_mode="local",
        cloud_consent=True,
        cloud_consent_at=datetime.now(timezone.utc),
        sends_content_to_cloud=False,
    )
    session.add(run)
    session.flush()
    review = BoundaryReviewSession(
        book_id=book.id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        prompt_version="v3.5",
        provider="fake",
        model="fake-scene-model",
        status="confirmed",
        candidate_count=0,
        accepted_count=0,
        rejected_count=0,
        manually_added_count=scene_count - 1,
        confirmed_by="tester",
        completed_at=datetime.now(timezone.utc),
    )
    session.add(review)
    session.flush()
    revision = BoundaryRevision(
        review_session_id=review.id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        revision_number=1,
        final_boundaries_json=json.dumps(
            [
                {
                    "after_paragraph_id": paragraphs[index * 2 - 1].id,
                    "source": "user_added",
                }
                for index in range(1, scene_count)
            ],
            ensure_ascii=False,
        ),
        confirmed_by="tester",
        confirmed_at=datetime.now(timezone.utc),
        coverage_rate=1.0,
    )
    session.add(revision)
    session.flush()
    scenes = []
    for index in range(scene_count):
        start = paragraphs[index * 2]
        end = paragraphs[index * 2 + 1] if index < scene_count - 1 or len(paragraphs) > index * 2 + 1 else paragraphs[-1]
        if index == scene_count - 1:
            end = paragraphs[-1]
        else:
            end = paragraphs[index * 2 + 1]
        scene = Scene(
            scene_key=f"B0001-C0001-R0001-S{index + 1:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            ordinal=index + 1,
            start_paragraph_id=start.id,
            end_paragraph_id=end.id,
            content_hash="d" * 64,
            created_by_run_id=run.id,
            boundary_confidence=0.9,
            boundary_detected=True,
            boundary_revision_id=revision.id,
            boundary_source="user_added" if index < scene_count - 1 else None,
        )
        session.add(scene)
        scenes.append(scene)
    session.commit()
    return book, chapter, run, review, revision, scenes, paragraphs


def _scene_payload(scene: Scene, paragraphs: list[Paragraph]) -> str:
    ids = []
    collecting = False
    for item in paragraphs:
        if item.id == scene.start_paragraph_id:
            collecting = True
        if collecting:
            ids.append(item.id)
        if item.id == scene.end_paragraph_id:
            break
    first, last = ids[0], ids[-1]

    def field(summary: str, evidence: list[str]) -> dict:
        return {"summary": summary, "evidence_paragraph_ids": evidence}

    return json.dumps(
        {
            "scene_id": scene.scene_key,
            "entry_state": field(f"进入-{scene.ordinal}", [first]),
            "goal": field(f"目标-{scene.ordinal}", [first]),
            "obstacle": field("", []),
            "key_actions": [
                {"summary": f"行动-{scene.ordinal}", "evidence_paragraph_ids": [first]}
            ],
            "turning_point": field("", []),
            "outcome": field(f"结果-{scene.ordinal}", [last]),
            "unresolved_question": field("", []),
            "function_tags": ["事件推进"],
            "confidence": 0.8,
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_runtime_service_overlays_db_enabled_over_registry_false(testing_session):
    _enable_cloud(testing_session)
    testing_session.add(
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            display_name="plus",
            region="cn-beijing",
            base_url="https://example.invalid/v1",
            plus_model="qwen3.7-plus",
            enabled=True,
            disconnected=False,
            allow_auto_route=False,
            credential_reference="keyring:aliyun_qwen_plus",
        )
    )
    testing_session.commit()
    provider = OpenAICompatibleProvider(
        name="aliyun_qwen_plus",
        base_url="https://disabled.invalid/v1",
        api_key="test-key",
        default_model="qwen3.7-plus",
        timeout_seconds=30,
        max_context_tokens=8192,
        enabled=False,
        cloud=True,
        supports_scene_analysis=True,
        supports_boundary_candidates=True,
        requires_boundary_review=True,
    )
    gateway = ModelGateway([provider])
    run = AnalysisRun(
        task_type="scene_pipeline",
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v3.1",
        schema_version="v1",
        input_hash="e" * 64,
        status="failed",
        subject_type="chapter",
        subject_id="1",
        prompt_hash="f" * 64,
        analysis_mode="assisted_boundary_review",
        cloud_consent=True,
        sends_content_to_cloud=True,
    )
    testing_session.add(run)
    testing_session.commit()
    assert provider.enabled is False
    resolved = ProviderRuntimeService.resolve_for_run(
        gateway, testing_session, run, store=None, task_type="scene_analysis"
    )
    assert resolved.provider.enabled is True
    assert "provider_disabled" not in resolved.eligibility["blockers"]


@pytest.mark.asyncio
async def test_scene_analysis_failure_persists_root_and_invocation(testing_session):
    _book, _ch, run, review, _rev, scenes, paragraphs = _seed_confirmed_run(
        testing_session, scene_count=2
    )
    factory = testing_session.get_bind()
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=factory, autoflush=False, expire_on_commit=False)
    provider = FakeProvider(
        responses=[
            ProviderRequestError(
                "Provider已停用，拒绝发送请求",
                http_request_sent=False,
                error_code="PROVIDER_DISABLED",
                exception_type="ProviderDisabled",
                provider="fake",
                phase="pre_send",
                retryable=False,
            )
        ]
        * 5
    )
    gateway = ModelGateway([provider])
    with pytest.raises(Exception):
        await analyze_confirmed_review(session_factory, gateway, review.id)
    testing_session.expire_all()
    run = testing_session.get(AnalysisRun, run.id)
    assert run.error_code == "SCENE_ANALYSIS_FAILED"
    assert run.root_error_code == "PROVIDER_DISABLED"
    assert run.root_error_message and "停用" in run.root_error_message
    assert run.failed_stage == "scene_analysis"
    assert run.failed_invocation_id is not None
    failure = json.loads(run.provider_health_at_failure or "{}").get("failure") or {}
    assert failure.get("failed_scene_id") == scenes[0].id
    assert failure.get("failed_scene_index") == 1


@pytest.mark.asyncio
async def test_partial_success_then_resume_skips_completed(client):
    from app.db.session import get_session_factory
    from app.main import app
    from app.model_gateway.registry import get_model_gateway

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, chapter, run, review, revision, scenes, paragraphs = _seed_confirmed_run(
            session, scene_count=3
        )
        first = scenes[0]
        payload = _scene_payload(first, paragraphs)
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(first.id),
            schema_version="v1",
            prompt_version="v3.1",
            payload_json=payload,
            confidence=0.8,
            validation_status="valid",
        )
        session.add(artifact)
        session.flush()
        session.add(
            AnalysisEvidence(
                artifact_id=artifact.id,
                field_path="goal.evidence_paragraph_ids[0]",
                paragraph_id=first.start_paragraph_id,
                paragraph_hash="g" * 64,
            )
        )
        run.status = "scene_analysis_partial"
        run.root_error_code = "PROVIDER_DISABLED"
        run.failed_stage = "scene_analysis"
        run_id = run.id
        revision_id = revision.id
        remaining_ids = [scenes[1].id, scenes[2].id]
        responses = [_scene_payload(scene, paragraphs) for scene in scenes[1:]]
        session.commit()

    fake = FakeProvider(responses=list(responses))
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([fake])
    pre = client.get(f"/api/v1/analysis-runs/{run_id}/resume-scene-analysis/preflight")
    assert pre.status_code == 200, pre.text
    body = pre.json()
    assert body["completed_scene_count"] == 1
    assert body["remaining_scene_count"] == 2
    assert body["boundary_revision_id"] == revision_id
    assert set(body["remaining_scene_ids"]) == set(remaining_ids)

    resume = client.post(
        f"/api/v1/analysis-runs/{run_id}/resume-scene-analysis",
        json={
            "client_request_id": "resume-a10-partial-001",
            "cloud_consent": True,
            "confirmed": True,
            "provider_state_version": body["provider_state_version"],
        },
    )
    assert resume.status_code == 202, resume.text
    with factory() as session:
        run = session.get(AnalysisRun, run_id)
        assert run.status == "succeeded"
        arts = session.scalars(
            select(AnalysisArtifact).where(
                AnalysisArtifact.run_id == run.id,
                AnalysisArtifact.artifact_type == "scene_analysis",
            )
        ).all()
        assert len(arts) == 3
        assert session.get(BoundaryRevision, revision_id) is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(Scene)
                .where(Scene.boundary_revision_id == revision_id)
            )
            == 3
        )
        det = session.scalar(
            select(func.count())
            .select_from(ModelInvocation)
            .where(
                ModelInvocation.run_id == run.id,
                ModelInvocation.task_type == "scene_boundary",
            )
        )
        assert int(det or 0) == 0
    # Scene resume must invoke FakeProvider once per remaining scene; auto-continue
    # Reader Journey may add further calls after scenes complete (CHG-20260722-003).
    scene_calls = sum(
        1
        for req in fake.requests
        if not any(
            ("reader_journey" in (msg.get("content") or ""))
            or ("读者阅读旅程" in (msg.get("content") or ""))
            or ("章节阅读旅程" in (msg.get("content") or ""))
            or ("reading_momentum" in (msg.get("content") or ""))
            for msg in req.messages
        )
    )
    assert scene_calls == 2


def test_resume_rejects_running_concurrent(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, _ch, run, _review, _rev, _scenes, _paras = _seed_confirmed_run(
            session, scene_count=2
        )
        run.status = "scene_analysis_running"
        run.raw_output = json.dumps(
            {"kind": "scene_analysis_resume", "client_request_id": "other-id"},
            ensure_ascii=False,
        )
        run_id = run.id
        session.commit()
    response = client.post(
        f"/api/v1/analysis-runs/{run_id}/resume-scene-analysis",
        json={
            "client_request_id": "new-id-xxxx",
            "cloud_consent": True,
            "confirmed": True,
        },
    )
    assert response.status_code == 409, response.text
    detail = response.json().get("detail") or response.json()
    assert (detail.get("error_code") if isinstance(detail, dict) else None) == (
        "SCENE_ANALYSIS_ALREADY_RUNNING"
    )


def test_serialize_run_hides_detection_recovery_for_scene_failure(client):
    from app.db.models import BoundaryDetectionBatchCheckpoint
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, chapter, run, _review, revision, scenes, _paras = _seed_confirmed_run(
            session, scene_count=2
        )
        for index in range(1, 3):
            session.add(
                BoundaryDetectionBatchCheckpoint(
                    run_id=run.id,
                    chapter_id=chapter.id,
                    batch_index=index,
                    prompt_version="v3.5",
                    owned_transition_ids_json="[]",
                    context_paragraph_ids_json="[]",
                    transition_map_json="{}",
                    status="completed",
                )
            )
        run.status = "failed"
        run.failed_stage = "scene_analysis"
        run.root_error_code = "PROVIDER_DISABLED"
        run.root_error_message = "Provider已停用，拒绝发送请求"
        run_id = run.id
        revision_id = revision.id
        session.commit()
    response = client.get(f"/api/v1/analysis-runs/{run_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["scene_analysis_resume_available"] is True
    assert body["detection_recovery_available"] is False
    assert body["checkpoint_available"] is False
    assert body["remaining_detection_batch_count"] == 0
    assert body["total_scene_count"] == 2
    assert body["completed_scene_count"] == 0
    assert body["remaining_scene_count"] == 2
    assert body["boundary_revision_id"] == revision_id


@pytest.mark.asyncio
async def test_analyze_binds_runtime_before_generate(testing_session):
    """Local FakeProvider succeeds for Stage 2 after runtime resolve path."""
    _book, _ch, run, review, _rev, scenes, paragraphs = _seed_confirmed_run(
        testing_session, scene_count=2
    )
    run.status = "boundary_confirmed"
    run.error_code = None
    run.failed_stage = None
    testing_session.commit()
    responses = [_scene_payload(scene, paragraphs) for scene in scenes]
    fake = FakeProvider(responses=list(responses))
    fake.enabled = False  # type: ignore[attr-defined]
    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(
        bind=testing_session.get_bind(), autoflush=False, expire_on_commit=False
    )
    await analyze_confirmed_review(session_factory, ModelGateway([fake]), review.id)
    testing_session.expire_all()
    run = testing_session.get(AnalysisRun, run.id)
    assert run.status in {"succeeded", "reader_journey_running", "reader_journey_pending", "reader_journey_failed"}
    scene_calls = sum(
        1
        for req in fake.requests
        if not any(
            ("reader_journey" in (msg.get("content") or ""))
            or ("读者阅读旅程" in (msg.get("content") or ""))
            or ("章节阅读旅程" in (msg.get("content") or ""))
            or ("reading_momentum" in (msg.get("content") or ""))
            for msg in req.messages
        )
    )
    assert scene_calls == 2


def test_resume_idempotent_same_client_request(client):
    from app.db.session import get_session_factory
    from app.main import app
    from app.model_gateway.registry import get_model_gateway

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, _ch, run, review, _rev, scenes, paragraphs = _seed_confirmed_run(
            session, scene_count=1
        )
        run.status = "failed"
        run.failed_stage = "scene_analysis"
        run_id = run.id
        responses = [_scene_payload(scenes[0], paragraphs)]
        session.commit()
    fake = FakeProvider(responses=list(responses))
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([fake])
    pre = client.get(f"/api/v1/analysis-runs/{run_id}/resume-scene-analysis/preflight")
    assert pre.status_code == 200, pre.text
    body = pre.json()
    payload = {
        "client_request_id": "idempotent-resume-55aa",
        "cloud_consent": True,
        "confirmed": True,
        "provider_state_version": body["provider_state_version"],
    }
    first = client.post(
        f"/api/v1/analysis-runs/{run_id}/resume-scene-analysis", json=payload
    )
    assert first.status_code == 202
    with factory() as session:
        run = session.get(AnalysisRun, run_id)
        if run.status != "succeeded":
            run.status = "scene_analysis_running"
            run.raw_output = json.dumps(
                {
                    "kind": "scene_analysis_resume",
                    "client_request_id": payload["client_request_id"],
                },
                ensure_ascii=False,
            )
            session.commit()
    second = client.post(
        f"/api/v1/analysis-runs/{run_id}/resume-scene-analysis", json=payload
    )
    assert second.status_code == 202


def test_offline_replay_idempotent_when_artifact_exists(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, _ch, run, _review, _rev, scenes, paragraphs = _seed_confirmed_run(
            session, scene_count=3
        )
        target = scenes[0]
        target.end_paragraph_id = target.start_paragraph_id
        session.add(target)
        payload = json.loads(_scene_payload(target, paragraphs))
        only = target.start_paragraph_id
        for key in ("entry_state", "goal", "obstacle", "outcome", "unresolved_question"):
            payload[key] = {
                "summary": f"{key}-{target.ordinal}",
                "evidence_paragraph_ids": [only],
            }
        payload["key_actions"] = [
            {"summary": f"行动-{target.ordinal}", "evidence_paragraph_ids": [only]}
        ]
        payload["turning_point"] = {"summary": "", "evidence_paragraph_ids": []}
        payload["scene_id"] = target.scene_key
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(target.id),
            schema_version="v1",
            prompt_version="v3.1",
            payload_json=json.dumps(payload, ensure_ascii=False),
            confidence=0.8,
            validation_status="valid",
        )
        session.add(artifact)
        session.flush()
        session.add(
            AnalysisEvidence(
                artifact_id=artifact.id,
                field_path="goal.evidence",
                paragraph_id=only,
                paragraph_hash="g" * 64,
            )
        )
        session.add(
            ModelInvocation(
                run_id=run.id,
                task_type="scene_analysis",
                provider_name="fake",
                model_name="fake",
                prompt_version="v3.1",
                schema_version="v1",
                attempt_no=2,
                invocation_kind="business_repair",
                request_hash="h" * 64,
                input_snapshot_json=json.dumps(
                    {
                        "content_hash": "x" * 64,
                        "paragraph_ids": [only],
                        "character_count": 10,
                    }
                ),
                raw_response_text="{}",
                parsed_response_json=json.dumps(payload, ensure_ascii=False),
                status="failed",
                latency_ms=10,
                http_request_sent=True,
                http_status_code=200,
                error_code="BUSINESS_VALIDATION_ERROR",
                audit_type="provider_invocation",
            )
        )
        run.status = "scene_analysis_partial"
        run.failed_stage = "scene_analysis"
        run.failed_invocation_id = 999
        run.root_error_code = "BUSINESS_VALIDATION_FAILED"
        run.provider_health_at_failure = json.dumps(
            {
                "failure": {
                    "failed_scene_id": target.id,
                    "failed_scene_index": target.ordinal,
                    "failed_invocation_id": 999,
                }
            },
            ensure_ascii=False,
        )
        run.raw_output = json.dumps({"kind": "scene_analysis_partial"}, ensure_ascii=False)
        run_id = run.id
        scene_id = target.id
        artifact_id = artifact.id
        session.commit()

    before = client.get(f"/api/v1/analysis-runs/{run_id}").json()
    assert before["completed_scene_count"] == 1
    assert before["failed_scene_id"] is None
    assert before["historical_failed_scene_id"] == scene_id
    assert before["offline_replay_available"] is False

    response = client.post(
        f"/api/v1/analysis-runs/{run_id}/scene-analysis/offline-replay",
        json={"scene_id": scene_id, "invocation_id": 999, "confirmed": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["idempotent_replay"] is True
    assert body["artifact_id"] == artifact_id
    assert body["offline_replay_available"] is False
    assert body["completed_scene_count"] == 1
    assert body["remaining_scene_count"] == 2

    after = client.get(f"/api/v1/analysis-runs/{run_id}").json()
    assert after["failed_scene_id"] is None
    assert after["historical_failed_scene_id"] == scene_id
    assert after["offline_replay_available"] is False
    assert after["scene_analysis_resume_available"] is True

    with factory() as session:
        run = session.get(AnalysisRun, run_id)
        inv_count = session.scalar(
            select(func.count())
            .select_from(ModelInvocation)
            .where(ModelInvocation.run_id == run_id, ModelInvocation.task_type == "scene_analysis")
        )
        art_count = session.scalar(
            select(func.count())
            .select_from(AnalysisArtifact)
            .where(
                AnalysisArtifact.run_id == run_id,
                AnalysisArtifact.artifact_type == "scene_analysis",
            )
        )
        assert int(inv_count or 0) == 1
        assert int(art_count or 0) == 1


def test_offline_replay_commits_artifact_without_http(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, _ch, run, _review, _rev, scenes, paragraphs = _seed_confirmed_run(
            session, scene_count=2
        )
        target = scenes[0]
        # Make it a single-paragraph scene (Run #55 Scene#10 pattern).
        target.end_paragraph_id = target.start_paragraph_id
        session.add(target)
        session.flush()
        payload = json.loads(_scene_payload(target, paragraphs))
        only = target.start_paragraph_id
        for key in ("entry_state", "goal", "obstacle", "outcome", "unresolved_question"):
            payload[key] = {
                "summary": f"{key}-{target.ordinal}",
                "evidence_paragraph_ids": [only],
            }
        payload["key_actions"] = [
            {"summary": f"行动-{target.ordinal}", "evidence_paragraph_ids": [only]}
        ]
        payload["turning_point"] = {"summary": "", "evidence_paragraph_ids": []}
        payload["scene_id"] = target.scene_key
        session.add(
            ModelInvocation(
                run_id=run.id,
                task_type="scene_analysis",
                provider_name="fake",
                model_name="fake",
                prompt_version="v3.1",
                schema_version="v1",
                attempt_no=1,
                invocation_kind="initial",
                request_hash="h" * 64,
                input_snapshot_json=json.dumps(
                    {
                        "content_hash": "x" * 64,
                        "paragraph_ids": [target.start_paragraph_id],
                        "character_count": 10,
                    }
                ),
                raw_response_text="{}",
                parsed_response_json=json.dumps(payload, ensure_ascii=False),
                status="failed",
                latency_ms=10,
                http_request_sent=True,
                http_status_code=200,
                error_code="BUSINESS_VALIDATION_ERROR",
                error_message="all analysis fields must not cite the whole scene indiscriminately",
                audit_type="provider_invocation",
            )
        )
        run.status = "scene_analysis_partial"
        run.failed_stage = "scene_analysis"
        run.root_error_code = "BUSINESS_VALIDATION_FAILED"
        run.raw_output = json.dumps(
            {
                "kind": "scene_analysis_failure",
                "failed_scene_id": target.id,
                "failed_scene_index": target.ordinal,
                "completed_scene_count": 0,
                "remaining_scene_count": 2,
            },
            ensure_ascii=False,
        )
        run_id = run.id
        scene_id = target.id
        session.commit()

    response = client.post(
        f"/api/v1/analysis-runs/{run_id}/replay-scene-analysis-offline",
        json={"scene_id": scene_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["http_request_sent"] is False
    assert body["completed_scene_count"] == 1
    assert body["remaining_scene_count"] == 1
    assert body["artifact_id"] > 0
    with factory() as session:
        arts = session.scalars(
            select(AnalysisArtifact).where(
                AnalysisArtifact.run_id == run_id,
                AnalysisArtifact.artifact_type == "scene_analysis",
            )
        ).all()
        assert len(arts) == 1
        assert session.scalar(
            select(func.count())
            .select_from(AnalysisEvidence)
            .where(AnalysisEvidence.artifact_id == arts[0].id)
        )


def test_resume_blocks_when_scene_http_attempts_exceeded(client):
    from app.db.session import get_session_factory
    from app.main import app
    from app.services.scene_analysis_offline_replay import SCENE_ANALYSIS_MAX_HTTP_ATTEMPTS

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, _ch, run, _review, _rev, scenes, _paras = _seed_confirmed_run(
            session, scene_count=2
        )
        target = scenes[0]
        for attempt in range(1, SCENE_ANALYSIS_MAX_HTTP_ATTEMPTS + 1):
            session.add(
                ModelInvocation(
                    run_id=run.id,
                    task_type="scene_analysis",
                    provider_name="fake",
                    model_name="fake",
                    prompt_version="v3.1",
                    schema_version="v1",
                    attempt_no=attempt,
                    invocation_kind="initial",
                    request_hash=f"{attempt}" * 32,
                    input_snapshot_json=json.dumps(
                        {
                            "content_hash": "y" * 64,
                            "paragraph_ids": [target.start_paragraph_id, target.end_paragraph_id],
                            "character_count": 10,
                        }
                    ),
                    raw_response_text="{}",
                    status="failed",
                    latency_ms=10,
                    http_request_sent=True,
                    http_status_code=200,
                    error_code="BUSINESS_VALIDATION_ERROR",
                    audit_type="provider_invocation",
                )
            )
        run.status = "scene_analysis_partial"
        run.failed_stage = "scene_analysis"
        run_id = run.id
        session.commit()

    response = client.post(
        f"/api/v1/analysis-runs/{run_id}/resume-scene-analysis",
        json={
            "client_request_id": "limit-block-aaaa",
            "cloud_consent": True,
            "confirmed": True,
        },
    )
    assert response.status_code == 409, response.text
    detail = response.json().get("detail") or response.json()
    assert detail["error_code"] == "SCENE_ANALYSIS_ATTEMPT_LIMIT"


def test_same_client_request_id_after_failure_is_idempotent(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    client_id = "same-client-after-fail1"
    with factory() as session:
        _book, _ch, run, _review, _rev, scenes, _paras = _seed_confirmed_run(
            session, scene_count=2
        )
        run.status = "scene_analysis_partial"
        run.failed_stage = "scene_analysis"
        run.root_error_code = "BUSINESS_VALIDATION_FAILED"
        run.raw_output = json.dumps(
            {
                "kind": "scene_analysis_failure",
                "failed_scene_id": scenes[0].id,
                "last_resume_client_request_id": client_id,
                "completed_scene_count": 0,
                "remaining_scene_count": 2,
            },
            ensure_ascii=False,
        )
        run_id = run.id
        session.commit()

    response = client.post(
        f"/api/v1/analysis-runs/{run_id}/resume-scene-analysis",
        json={
            "client_request_id": client_id,
            "cloud_consent": True,
            "confirmed": True,
        },
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "scene_analysis_partial"
    with factory() as session:
        inv_count = session.scalar(
            select(func.count())
            .select_from(ModelInvocation)
            .where(ModelInvocation.run_id == run_id, ModelInvocation.task_type == "scene_analysis")
        )
        assert int(inv_count or 0) == 0


def test_empty_key_actions_single_paragraph_offline_replay(client):
    """Short/static scenes may legally return key_actions=[]; never fabricate from goal."""
    from app.db.session import get_session_factory
    from app.main import app
    from app.services.scene_pipeline import (
        is_evidence_paragraph_validation_error,
        normalize_scene_analysis_result,
        validate_scene_analysis,
    )
    from app.schemas.scene import SceneAnalysisResult

    assert is_evidence_paragraph_validation_error(
        "key_actions requires at least one evidenced action"
    ) is False
    assert is_evidence_paragraph_validation_error(
        "key_actions 每项必须包含非空 summary 与当前场景内证据"
    ) is True
    assert is_evidence_paragraph_validation_error("entry_state、goal、outcome 必须包含证据") is True

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, _ch, run, _review, _rev, scenes, paragraphs = _seed_confirmed_run(
            session, scene_count=3
        )
        target = scenes[1]
        target.end_paragraph_id = target.start_paragraph_id
        session.add(target)
        only = target.start_paragraph_id
        payload = {
            "scene_id": target.scene_key,
            "entry_state": {"summary": "客厅陷入死寂。", "evidence_paragraph_ids": [only]},
            "goal": {
                "summary": "维持或打破当前的死寂状态（隐含）。",
                "evidence_paragraph_ids": [only],
            },
            "obstacle": {
                "summary": "缺乏明确的行动主体或外部干扰，处于静态僵局。",
                "evidence_paragraph_ids": [only],
            },
            "key_actions": [],
            "turning_point": {"summary": "", "evidence_paragraph_ids": []},
            "outcome": {
                "summary": "场景保持在死寂的状态中。",
                "evidence_paragraph_ids": [only],
            },
            "unresolved_question": {
                "summary": "死寂之后会发生什么？",
                "evidence_paragraph_ids": [only],
            },
            "function_tags": ["过渡", "悬念设置"],
            "confidence": 0.7,
        }
        result = normalize_scene_analysis_result(
            SceneAnalysisResult.model_validate(payload), {only}
        )
        validate_scene_analysis(result, target.scene_key, {only}, True)
        assert result.key_actions == []

        first_scene_id = scenes[0].id
        third_scene_id = scenes[2].id
        for sid in (first_scene_id,):
            art = AnalysisArtifact(
                run_id=run.id,
                artifact_type="scene_analysis",
                subject_type="scene",
                subject_id=str(sid),
                schema_version="v1",
                prompt_version="v3.1",
                payload_json="{}",
                confidence=0.8,
                validation_status="valid",
            )
            session.add(art)
            session.flush()
            session.add(
                AnalysisEvidence(
                    artifact_id=art.id,
                    field_path="goal.evidence",
                    paragraph_id=scenes[0].start_paragraph_id,
                    paragraph_hash="z" * 64,
                )
            )
        session.add(
            ModelInvocation(
                run_id=run.id,
                task_type="scene_analysis",
                provider_name="fake",
                model_name="fake",
                prompt_version="v3.1",
                schema_version="v1",
                attempt_no=2,
                invocation_kind="evidence_repair",
                request_hash="h" * 64,
                input_snapshot_json=json.dumps(
                    {
                        "content_hash": "x" * 64,
                        "paragraph_ids": [only],
                        "character_count": 10,
                    }
                ),
                raw_response_text="{}",
                parsed_response_json=json.dumps(payload, ensure_ascii=False),
                status="failed",
                latency_ms=10,
                http_request_sent=True,
                http_status_code=200,
                error_code="EVIDENCE_VALIDATION_FAILED",
                error_message="key_actions requires at least one evidenced action",
                audit_type="provider_invocation",
            )
        )
        run.status = "scene_analysis_partial"
        run.failed_stage = "scene_analysis"
        run.root_error_code = "EVIDENCE_VALIDATION_FAILED"
        run.root_error_message = "key_actions requires at least one evidenced action"
        session.flush()
        inv_row = session.scalars(
            select(ModelInvocation)
            .where(ModelInvocation.run_id == run.id, ModelInvocation.task_type == "scene_analysis")
            .order_by(ModelInvocation.id.desc())
        ).first()
        assert inv_row is not None
        run.failed_invocation_id = inv_row.id
        run.provider_health_at_failure = json.dumps(
            {
                "failure": {
                    "failed_scene_id": target.id,
                    "failed_scene_index": target.ordinal,
                    "failed_invocation_id": inv_row.id,
                    "completed_scene_count": 1,
                    "remaining_scene_count": 2,
                }
            },
            ensure_ascii=False,
        )
        run_id = run.id
        scene_id = target.id
        session.commit()

    before = client.get(f"/api/v1/analysis-runs/{run_id}").json()
    assert before["completed_scene_count"] == 1
    assert before["remaining_scene_count"] == 2
    assert before["offline_replay_available"] is True
    assert before["scene_validation_detail"]["offline_replay_eligible"] is True
    assert "key_actions_empty" in before["scene_validation_detail"]["categories"]

    inv_before = client.get(f"/api/v1/analysis-runs/{run_id}/model-invocations").json()
    assert len([i for i in inv_before if i["task_type"] == "scene_analysis"]) == 1

    response = client.post(
        f"/api/v1/analysis-runs/{run_id}/scene-analysis/offline-replay",
        json={"scene_id": scene_id, "confirmed": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["http_request_sent"] is False
    assert body["completed_scene_count"] == 2
    assert body["remaining_scene_count"] == 1
    assert body["offline_replay_available"] is False

    after = client.get(f"/api/v1/analysis-runs/{run_id}").json()
    assert after["completed_scene_ids"] == [first_scene_id, scene_id]
    assert after["remaining_scene_ids"] == [third_scene_id]

    inv_after = client.get(f"/api/v1/analysis-runs/{run_id}/model-invocations").json()
    assert len([i for i in inv_after if i["task_type"] == "scene_analysis"]) == 1


def test_resume_only_remaining_scene_after_offline_replay(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _book, _ch, run, _review, _rev, scenes, paragraphs = _seed_confirmed_run(
            session, scene_count=14
        )
        for index, scene in enumerate(scenes[:12]):
            only = scene.start_paragraph_id
            payload = json.loads(_scene_payload(scene, paragraphs))
            art = AnalysisArtifact(
                run_id=run.id,
                artifact_type="scene_analysis",
                subject_type="scene",
                subject_id=str(scene.id),
                schema_version="v1",
                prompt_version="v3.1",
                payload_json=json.dumps(payload, ensure_ascii=False),
                confidence=0.8,
                validation_status="valid",
            )
            session.add(art)
            session.flush()
            session.add(
                AnalysisEvidence(
                    artifact_id=art.id,
                    field_path="goal.evidence",
                    paragraph_id=only,
                    paragraph_hash="e" * 64,
                )
            )
        failed = scenes[12]
        failed.end_paragraph_id = failed.start_paragraph_id
        session.add(failed)
        only = failed.start_paragraph_id
        fail_payload = {
            "scene_id": failed.scene_key,
            "entry_state": {"summary": "死寂。", "evidence_paragraph_ids": [only]},
            "goal": {"summary": "等待变化。", "evidence_paragraph_ids": [only]},
            "obstacle": {"summary": "", "evidence_paragraph_ids": []},
            "key_actions": [],
            "turning_point": {"summary": "", "evidence_paragraph_ids": []},
            "outcome": {"summary": "仍死寂。", "evidence_paragraph_ids": [only]},
            "unresolved_question": {"summary": "", "evidence_paragraph_ids": []},
            "function_tags": ["过渡"],
            "confidence": 0.6,
        }
        session.add(
            ModelInvocation(
                run_id=run.id,
                task_type="scene_analysis",
                provider_name="fake",
                model_name="fake",
                prompt_version="v3.1",
                schema_version="v1",
                attempt_no=2,
                invocation_kind="evidence_repair",
                request_hash="k" * 64,
                input_snapshot_json=json.dumps(
                    {"paragraph_ids": [only], "content_hash": "x" * 64, "character_count": 10}
                ),
                raw_response_text="{}",
                parsed_response_json=json.dumps(fail_payload, ensure_ascii=False),
                status="failed",
                latency_ms=10,
                http_request_sent=True,
                error_code="EVIDENCE_VALIDATION_FAILED",
                error_message="key_actions requires at least one evidenced action",
                audit_type="provider_invocation",
            )
        )
        run.status = "scene_analysis_partial"
        run.failed_stage = "scene_analysis"
        run_id = run.id
        session.commit()

    replay = client.post(
        f"/api/v1/analysis-runs/{run_id}/scene-analysis/offline-replay",
        json={"confirmed": True},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["completed_scene_count"] == 13
    assert replay.json()["remaining_scene_count"] == 1

    pre = client.get(f"/api/v1/analysis-runs/{run_id}/resume-scene-analysis/preflight")
    assert pre.status_code == 200
    assert pre.json()["remaining_scene_count"] == 1
    assert pre.json()["expected_requests"] == 1
