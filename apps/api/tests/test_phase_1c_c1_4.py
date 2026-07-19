"""Phase 1C-C.1.4: resume preflight refresh after offline replay (zero cloud)."""

from __future__ import annotations

import json

from sqlalchemy import select, func

from app.db.models import ModelInvocation, ReaderJourneyRun, SceneReaderJourneyProfile
from app.schemas.reader_journey import SCENE_CONTRACT_VERSION, SceneReaderJourneyProfileItem
from app.services.reader_journey_contract_migrate import migrate_v11_profile_dict_to_v12
from app.services.reader_journey_offline_replay import offline_replay_journey_profiles
from app.services.reader_journey_progress import reader_journey_progress, recovery_flags
from tests.test_phase_1c_c1 import _enable_cloud, _seed_run55_like
from tests.test_phase_1c_c1_3 import _base_profile_dict, _invocation134_payload, _make_invocation


def test_recovery_flags_partial_after_offline_allows_resume(testing_session):
    _enable_cloud(testing_session)
    _book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(testing_session)
    journey_run = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=_book.id,
        chapter_id=chapter.id,
        status="scene_profiles_partial",
        provider_name="fake",
        model_name="fake-scene-model",
        planner_version="1.1",
        scene_prompt_version="v1.1",
        scene_contract_version="1.1",
        total_scene_count=len(scenes),
        completed_scene_count=1,
        remaining_scene_count=len(scenes) - 1,
        remaining_scene_ids_json=json.dumps([s.id for s in scenes[1:]]),
        completed_scene_ids_json=json.dumps([scenes[0].id]),
        cloud_consent=True,
        client_request_id="rj-flags-partial",
        root_error_code="STRUCTURAL_VALIDATION_FAILED",
        root_error_message="reader_question_in 不得全部为空",
        retryable=True,
    )
    testing_session.add(journey_run)
    testing_session.commit()

    safe, blocked, reason = recovery_flags(
        journey_run,
        completed_scene_count=1,
        offline_replay_available=False,
    )
    assert safe is True
    assert blocked is False
    assert reason is None


def test_offline_replay_then_resume_preflight_excludes_completed(testing_session):
    _enable_cloud(testing_session)
    _book, chapter, run, _revision, scenes, paragraphs = _seed_run55_like(testing_session)
    scene = scenes[0]
    paragraph_ids = [p.id for p in paragraphs[:12]]
    journey_run = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=_book.id,
        chapter_id=chapter.id,
        status="failed",
        provider_name="fake",
        model_name="fake-scene-model",
        planner_version="1.1",
        scene_prompt_version="v1.1",
        scene_contract_version="1.1",
        total_scene_count=len(scenes),
        remaining_scene_count=len(scenes),
        remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
        completed_scene_count=0,
        cloud_consent=True,
        client_request_id="rj-resume-refresh",
        root_error_code="STRUCTURAL_VALIDATION_FAILED",
        root_error_message="reader_question_in 不得全部为空",
        failed_scene_id=scene.id,
        failed_scene_ordinal=scene.ordinal,
        retryable=False,
    )
    testing_session.add(journey_run)
    testing_session.flush()
    parsed = _invocation134_payload(scene, paragraph_ids)
    inv = _make_invocation(
        run_id=run.id,
        task_type="reader_journey_scene",
        provider_name="fake",
        model_name="fake-scene-model",
        prompt_version="v1.1",
        schema_version="v1",
        attempt_no=2,
        invocation_kind="structural_repair",
        request_hash="r" * 64,
        input_snapshot_json=json.dumps(
            {
                "owned_scene_ids_json": json.dumps([scene.id]),
                "owned_scene_ordinals_json": json.dumps([scene.ordinal]),
            },
            ensure_ascii=False,
        ),
        parsed_response_json=json.dumps(parsed, ensure_ascii=False),
        status="failed",
        latency_ms=100,
        http_status_code=200,
        error_code="STRUCTURAL_VALIDATION_FAILED",
        error_message="reader_question_in 不得全部为空",
    )
    testing_session.add(inv)
    testing_session.commit()

    before = reader_journey_progress(testing_session, journey_run)
    assert before.completed_scene_count == 0
    assert before.offline_replay_available is True
    assert before.blind_resume_blocked is True
    assert before.resume_block_reason == "offline_replay_required"
    assert before.resume_preflight is None

    inv_count_before = testing_session.scalar(select(func.count()).select_from(ModelInvocation))
    result = offline_replay_journey_profiles(testing_session, journey_run.id)
    inv_count_after = testing_session.scalar(select(func.count()).select_from(ModelInvocation))
    assert result["http_requests"] == 0
    assert result["tokens"] == 0
    assert result["cost"] == 0.0
    assert scene.id in result["replayed_scene_ids"]
    assert inv_count_after == inv_count_before

    testing_session.refresh(journey_run)
    assert journey_run.status == "scene_profiles_partial"
    assert journey_run.completed_scene_count == 1
    assert journey_run.remaining_scene_count == len(scenes) - 1
    assert scene.id in json.loads(journey_run.completed_scene_ids_json)
    assert scene.id not in json.loads(journey_run.remaining_scene_ids_json)
    assert journey_run.scene_contract_version == SCENE_CONTRACT_VERSION
    assert journey_run.planner_version == "1.1"

    after = reader_journey_progress(testing_session, journey_run)
    assert after.completed_scene_count == 1
    assert after.remaining_scene_count == len(scenes) - 1
    assert scene.id in after.completed_scene_ids
    assert scene.id not in after.remaining_scene_ids
    assert after.offline_replay_available is False
    assert after.recovery_safe is True
    assert after.blind_resume_blocked is False
    assert after.resume_block_reason is None
    assert after.resume_preflight is not None

    plan_lines = after.resume_preflight["batch_plan"]
    assert isinstance(plan_lines, list)
    joined = "\n".join(plan_lines)
    assert f"Scene {scene.ordinal}单独" not in joined
    assert after.resume_preflight["remaining_scenes"] == len(scenes) - 1
    assert after.resume_preflight["scene_batch_count"] == len(plan_lines)
    assert after.resume_preflight["expected_requests"] == after.resume_preflight["scene_batch_count"] + 1
    assert after.resume_preflight["planner_version"] == "1.1"
    assert after.resume_preflight["scene_contract_version"] == SCENE_CONTRACT_VERSION

    journey_count = testing_session.scalar(select(func.count()).select_from(ReaderJourneyRun))
    assert journey_count == 1


def test_progress_api_resume_preflight_after_partial(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        _book, chapter, run, _revision, scenes, paragraphs = _seed_run55_like(session)
        scene = scenes[0]
        paragraph_ids = [p.id for p in paragraphs[:12]]
        journey_run = ReaderJourneyRun(
            analysis_run_id=run.id,
            book_id=_book.id,
            chapter_id=chapter.id,
            status="scene_profiles_partial",
            provider_name="fake",
            model_name="fake-scene-model",
            planner_version="1.1",
            scene_prompt_version="v1.2",
            scene_contract_version="1.2",
            total_scene_count=len(scenes),
            completed_scene_count=1,
            remaining_scene_count=len(scenes) - 1,
            completed_scene_ids_json=json.dumps([scene.id]),
            remaining_scene_ids_json=json.dumps([s.id for s in scenes[1:]]),
            cloud_consent=True,
            client_request_id="rj-api-partial",
            retryable=True,
        )
        session.add(journey_run)
        session.flush()
        migrated = migrate_v11_profile_dict_to_v12(
            _base_profile_dict(scene_id=scene.id, scene_ordinal=1, paragraph_ids=paragraph_ids)
        )
        profile_item = SceneReaderJourneyProfileItem.model_validate(migrated)
        from app.services.reader_journey_pipeline import _persist_profile

        _persist_profile(
            session,
            journey_run,
            profile_item,
            paragraphs_by_id={p.id: p for p in paragraphs},
            genre="suspense",
        )
        session.commit()
        journey_id = journey_run.id
        run_id = run.id
        scene_count = len(scenes)

    resp = client.get(f"/api/v1/reader-journey-runs/{journey_id}/progress")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "scene_profiles_partial"
    assert body["completed_scene_count"] == 1
    assert body["remaining_scene_count"] == scene_count - 1
    assert body["recovery_safe"] is True
    assert body["blind_resume_blocked"] is False
    assert body["resume_block_reason"] is None
    assert body["resume_preflight"] is not None
    assert body["resume_preflight"]["remaining_scenes"] == scene_count - 1
    assert "Scene 1单独" not in "\n".join(body["resume_preflight"]["batch_plan"])
    assert body["scene_contract_version"] == "1.2"
    assert body["planner_version"] == "1.1"

    create = client.post(
        f"/api/v1/analysis-runs/{run_id}/reader-journey",
        json={
            "client_request_id": "must-not-create-3",
            "cloud_consent": True,
            "force_new_version": False,
        },
    )
    assert create.status_code == 202
    accepted = create.json()
    assert accepted["journey_run_id"] == journey_id
    assert accepted.get("creation_blocked_reason") == "ACTIVE_OR_RECOVERABLE_JOURNEY_EXISTS"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ReaderJourneyRun)) == 1
        assert session.scalar(select(func.count()).select_from(SceneReaderJourneyProfile)) == 1
