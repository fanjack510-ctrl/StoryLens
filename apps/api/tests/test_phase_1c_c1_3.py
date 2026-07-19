"""Phase 1C-C.1.3 Reader Journey question lifecycle + offline replay tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import ModelInvocation, ReaderJourneyRun, Scene, SceneReaderJourneyProfile
from app.model_gateway.base import ModelRequest, ModelResponse
from app.model_gateway.gateway import ModelGateway
from app.schemas.reader_journey import ReaderQuestionIn, ReaderQuestionOut, SceneReaderJourneyProfileItem
from app.services.reader_journey_contract_migrate import migrate_v11_profile_dict_to_v12
from app.services.reader_journey_offline_replay import (
    find_replayable_journey_invocations,
    offline_replay_journey_profiles,
)
from app.services.reader_journey_pipeline import execute_reader_journey
from app.services.reader_journey_question_lifecycle import build_question_chains
from app.services.reader_journey_validation import validate_scene_profile_item
from app.services.validation_errors import StructuralValidationError
from tests.fakes import FakeProvider
from tests.test_phase_1c_c1 import _enable_cloud, _seed_run55_like


def _session_factory_from(testing_session):
    return sessionmaker(
        bind=testing_session.get_bind(), autoflush=False, expire_on_commit=False
    )


def _base_profile_dict(*, scene_id: int = 1, scene_ordinal: int = 1, paragraph_ids: list[str]) -> dict:
    first, last = paragraph_ids[0], paragraph_ids[-1]
    return {
        "scene_id": scene_id,
        "scene_ordinal": scene_ordinal,
        "scene_value_summary": "开篇通过异常细节建立情境，引入主角出场",
        "reader_question_in": [],
        "reader_question_answered": [],
        "reader_question_out": [
            {
                "question": "戏鬼身份与回家动机是否一致",
                "hook_type": "identity",
                "strength": 62,
            },
            {
                "question": "村中异常是否预示更大危险",
                "hook_type": "danger",
                "strength": 58,
            },
        ],
        "dominant_emotion": "好奇",
        "emotional_valence_start": -5,
        "emotional_valence_end": 10,
        "arousal_start": 35,
        "arousal_end": 50,
        "curiosity_score": 65,
        "tension_score": 55,
        "payoff_score": 40,
        "hook_score": 60,
        "information_gain_score": 50,
        "emotional_resonance_score": 45,
        "cognitive_load_score": 25,
        "dropoff_risk_score": 20,
        "payoffs": [
            {
                "type": "information",
                "summary": "揭示主角戏鬼身份线索",
                "strength": 55,
                "evidence_paragraph_ids": [last],
            }
        ],
        "hooks": [
            {
                "type": "identity",
                "summary": "回家动机与身份形成张力",
                "strength": 60,
                "evidence_paragraph_ids": [first],
            }
        ],
        "techniques": [
            {
                "code": "contrast_reveal",
                "name": "反差揭示",
                "mechanism": "日常回家动作中露出戏鬼细节",
                "reader_effect": "读者比对身份与行为",
                "transfer_formula": "日常+异常细节",
                "risk": "细节弱则像笔误",
                "evidence_paragraph_ids": [first],
            }
        ],
        "risk_points": [
            {
                "type": "weak_hook",
                "summary": "若下一场不承接身份疑问则牵引衰减",
                "severity": 30,
                "evidence_paragraph_ids": [last],
            }
        ],
        "emotion_beats": [
            {"label": "疑惑", "valence": -5, "arousal": 40, "evidence_paragraph_ids": [first]}
        ],
        "information_changes": [
            {
                "type": "new_information",
                "summary": "主角戏鬼身份首次可观察",
                "certainty": "fact",
                "evidence_paragraph_ids": [first],
            }
        ],
        "character_effects": [
            {
                "character_name": "主角",
                "trait_or_change": "戏鬼身份与回家行动形成对照",
                "method": "action",
                "evidence_paragraph_ids": [first],
            }
        ],
        "writing_takeaways": [
            {
                "summary": "用可验证细节承载开场悬念",
                "applicable_when": "悬疑开场",
                "avoid_when": "需快速交代世界观",
            }
        ],
        "confidence": 0.75,
        "evidence_paragraph_ids": [first, last],
    }


def _invocation134_payload(scene: Scene, paragraphs: list[str]) -> dict:
    profile = _base_profile_dict(
        scene_id=scene.id,
        scene_ordinal=scene.ordinal,
        paragraph_ids=paragraphs,
    )
    return {"contract_version": "1.1", "profiles": [profile]}


class RepeatedValidationErrorFakeProvider(FakeProvider):
    """Return profiles with no valid question lifecycle (repeat structural errors)."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        combined = "\n".join(item["content"] for item in request.messages)
        payload = self._reader_journey_scene_payload(combined)
        for profile in payload.get("profiles", []):
            if isinstance(profile, dict):
                profile["reader_question_in"] = []
                profile["reader_question_created"] = []
                profile["reader_question_out"] = []
                profile["scene_value_summary"] = "普通推进"
        return ModelResponse(
            text=json.dumps(payload, ensure_ascii=False),
            model=self.default_model,
            http_status_code=200,
        )


def _make_invocation(**kwargs) -> ModelInvocation:
    defaults = {
        "raw_response_text": "",
        "http_request_sent": True,
        "audit_type": "provider_invocation",
    }
    defaults.update(kwargs)
    return ModelInvocation(**defaults)


def test_opening_empty_in_allowed_with_out():
    paragraph_ids = [f"B0001-C0002-P{i:04d}" for i in range(1, 13)]
    raw = migrate_v11_profile_dict_to_v12(_base_profile_dict(paragraph_ids=paragraph_ids))
    profile = SceneReaderJourneyProfileItem.model_validate(raw)
    validate_scene_profile_item(
        profile,
        allowed_paragraph_ids=set(paragraph_ids),
        is_chapter_opening=True,
    )


def test_opening_empty_everything_fails():
    paragraph_ids = [f"B0001-C0002-P{i:04d}" for i in range(1, 13)]
    profile = SceneReaderJourneyProfileItem.model_validate(
        {
            **_base_profile_dict(paragraph_ids=paragraph_ids),
            "scene_value_summary": "普通推进",
            "reader_question_out": [],
            "reader_question_created": [],
        }
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(
            profile,
            allowed_paragraph_ids=set(paragraph_ids),
            is_chapter_opening=True,
        )
    assert exc.value.error_code == "JOURNEY_QUESTION_CHAIN_INVALID"


def test_migrate_created_in_scene_to_created():
    paragraph_ids = ["B0001-C0002-P0001", "B0001-C0002-P0012"]
    payload = _base_profile_dict(paragraph_ids=paragraph_ids)
    payload["reader_question_in"] = [
        {"question": "本Scene新问题", "source": "created_in_scene", "confidence": 0.6}
    ]
    migrated = migrate_v11_profile_dict_to_v12(payload)
    assert migrated["reader_question_in"] == []
    assert len(migrated["reader_question_created"]) >= 1
    assert migrated["reader_question_created"][0]["question"] == "本Scene新问题"
    assert migrated["reader_question_out"][0]["origin"] == "created_here"


def test_reader_question_in_rejects_created_in_scene_at_schema():
    with pytest.raises(ValidationError):
        SceneReaderJourneyProfileItem.model_validate(
            {
                **_base_profile_dict(paragraph_ids=["B0001-C0002-P0001"]),
                "reader_question_in": [
                    {"question": "q", "source": "created_in_scene", "confidence": 0.5}
                ],
            }
        )


def test_offline_replay_invocation134_shaped(testing_session):
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
        scene_prompt_version="v1.1",
        scene_contract_version="1.1",
        total_scene_count=len(scenes),
        remaining_scene_count=len(scenes),
        remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
        cloud_consent=True,
        client_request_id="rj-offline-134",
        root_error_code="JOURNEY_QUESTION_CHAIN_INVALID",
        root_error_message="reader_question_in 不得全部为空",
        failed_scene_id=scene.id,
        failed_scene_ordinal=scene.ordinal,
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
        request_hash="h" * 64,
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
        error_code="JOURNEY_QUESTION_CHAIN_INVALID",
        error_message="reader_question_in 不得全部为空",
    )
    testing_session.add(inv)
    testing_session.commit()

    candidates = find_replayable_journey_invocations(testing_session, journey_run)
    assert any(item.invocation_id == inv.id for item in candidates)

    result = offline_replay_journey_profiles(testing_session, journey_run.id)
    assert scene.id in result["replayed_scene_ids"]
    assert result["http_requests"] == 0
    assert result["tokens"] == 0
    assert result["cost"] == 0.0
    assert result["migrated_from_contract_version"] == "1.1"
    assert result["current_contract_version"] == "1.3"

    profile = testing_session.scalar(
        select(SceneReaderJourneyProfile).where(
            SceneReaderJourneyProfile.reader_journey_run_id == journey_run.id,
            SceneReaderJourneyProfile.scene_id == scene.id,
        )
    )
    assert profile is not None
    payload = json.loads(profile.payload_json)
    assert payload.get("reader_question_created")
    assert payload["reader_question_in"] == []


def test_offline_replay_idempotent(testing_session):
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
        scene_contract_version="1.1",
        total_scene_count=len(scenes),
        remaining_scene_count=len(scenes) - 1,
        remaining_scene_ids_json=json.dumps([s.id for s in scenes[1:]]),
        completed_scene_count=1,
        cloud_consent=True,
        client_request_id="rj-idempotent",
    )
    testing_session.add(journey_run)
    testing_session.flush()
    migrated = migrate_v11_profile_dict_to_v12(_base_profile_dict(scene_id=scene.id, scene_ordinal=1, paragraph_ids=paragraph_ids))
    profile_item = SceneReaderJourneyProfileItem.model_validate(migrated)
    from app.services.reader_journey_pipeline import _persist_profile

    by_id = {p.id: p for p in paragraphs}
    _persist_profile(
        testing_session,
        journey_run,
        profile_item,
        paragraphs_by_id=by_id,
        genre="suspense",
    )
    inv = _make_invocation(
        run_id=run.id,
        task_type="reader_journey_scene",
        provider_name="fake",
        model_name="fake-scene-model",
        prompt_version="v1.1",
        schema_version="v1",
        attempt_no=1,
        invocation_kind="normal_batch_request",
        request_hash="i" * 64,
        input_snapshot_json=json.dumps({"owned_scene_ids_json": json.dumps([scene.id])}),
        parsed_response_json=json.dumps(
            {
                "contract_version": "1.1",
                "profiles": [
                    _base_profile_dict(scene_id=scene.id, scene_ordinal=1, paragraph_ids=paragraph_ids)
                ],
            }
        ),
        status="failed",
        latency_ms=50,
        http_status_code=200,
        error_code="JOURNEY_QUESTION_CHAIN_INVALID",
        error_message="reader_question_in 不得全部为空",
    )
    testing_session.add(inv)
    testing_session.commit()

    result = offline_replay_journey_profiles(testing_session, journey_run.id)
    assert result["idempotent_replay"] is True
    assert result["replayed_scene_ids"] == []


@pytest.mark.asyncio
async def test_same_validation_error_stops_at_two_attempts(testing_session):
    _enable_cloud(testing_session)
    _book, chapter, run, _revision, scenes, _paragraphs = _seed_run55_like(testing_session, scene_count=2)
    fake = RepeatedValidationErrorFakeProvider()
    gateway = ModelGateway([fake])
    session_factory = _session_factory_from(testing_session)
    journey_run = ReaderJourneyRun(
        analysis_run_id=run.id,
        book_id=_book.id,
        chapter_id=chapter.id,
        status="queued",
        provider_name="fake",
        model_name="fake-scene-model",
        total_scene_count=2,
        remaining_scene_count=2,
        remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
        cloud_consent=True,
        client_request_id="rj-repeat-abort",
    )
    testing_session.add(journey_run)
    testing_session.commit()
    await execute_reader_journey(session_factory, gateway, journey_run.id)
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ModelInvocation)
                .where(
                    ModelInvocation.run_id == run.id,
                    ModelInvocation.task_type == "reader_journey_scene",
                )
                .order_by(ModelInvocation.id)
            )
        )
        assert len(rows) <= 2
        if rows:
            assert rows[-1].error_code == "JOURNEY_QUESTION_CHAIN_INVALID"


def test_contract_conflict_no_model_repair():
    profile = SceneReaderJourneyProfileItem.model_construct(
        scene_id=1,
        scene_ordinal=2,
        scene_value_summary="价值",
        reader_question_in=[
            ReaderQuestionIn.model_construct(
                question="bad",
                source="created_in_scene",
                confidence=0.5,
            )
        ],
        reader_question_created=[],
        reader_question_answered=[],
        reader_question_out=[
            ReaderQuestionOut.model_construct(
                question="out",
                origin="carried",
                strength=50,
                evidence_paragraph_ids=["B0001-C0002-P0001"],
            )
        ],
        dominant_emotion="好奇",
        curiosity_score=50,
        tension_score=50,
        payoff_score=50,
        hook_score=50,
        information_gain_score=50,
        emotional_resonance_score=50,
        cognitive_load_score=20,
        dropoff_risk_score=20,
        confidence=0.7,
        evidence_paragraph_ids=["B0001-C0002-P0001"],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_scene_profile_item(
            profile,
            allowed_paragraph_ids={"B0001-C0002-P0001"},
            is_chapter_opening=False,
        )
    assert exc.value.error_code == "JOURNEY_CONTRACT_VALIDATION_CONFLICT"
    assert exc.value.no_model_repair is True


def test_question_chains_built():
    profiles = [
        SceneReaderJourneyProfileItem.model_validate(
            migrate_v11_profile_dict_to_v12(
                _base_profile_dict(
                    scene_id=1,
                    scene_ordinal=1,
                    paragraph_ids=["B0001-C0002-P0001", "B0001-C0002-P0012"],
                )
            )
        ),
        SceneReaderJourneyProfileItem.model_validate(
            {
                **migrate_v11_profile_dict_to_v12(
                    _base_profile_dict(
                        scene_id=2,
                        scene_ordinal=2,
                        paragraph_ids=["B0001-C0002-P0013", "B0001-C0002-P0014"],
                    )
                ),
                "evidence_paragraph_ids": ["B0001-C0002-P0013", "B0001-C0002-P0014"],
                "reader_question_in": [
                    {
                        "question": "戏鬼身份与回家动机是否一致",
                        "source": "carried_from_previous",
                        "confidence": 0.7,
                    }
                ],
                "reader_question_created": [],
                "reader_question_out": [
                    {
                        "question": "村中异常是否预示更大危险",
                        "origin": "carried",
                        "strength": 55,
                        "evidence_paragraph_ids": ["B0001-C0002-P0014"],
                    }
                ],
            }
        ),
    ]
    chains = build_question_chains(profiles)
    assert chains
    assert any(item["status"] in {"created", "carried"} for item in chains)


def test_progress_offline_replay_available(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        _book, chapter, run, _revision, scenes, paragraphs = _seed_run55_like(session)
        scene = scenes[0]
        journey_run = ReaderJourneyRun(
            analysis_run_id=run.id,
            book_id=_book.id,
            chapter_id=chapter.id,
            status="failed",
            provider_name="fake",
            model_name="fake-scene-model",
            scene_contract_version="1.1",
            total_scene_count=len(scenes),
            remaining_scene_count=len(scenes),
            remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
            cloud_consent=True,
            client_request_id="rj-progress-offline",
            root_error_code="JOURNEY_QUESTION_CHAIN_INVALID",
        )
        session.add(journey_run)
        session.flush()
        parsed = _invocation134_payload(scene, [p.id for p in paragraphs[:12]])
        session.add(
            _make_invocation(
                run_id=run.id,
                task_type="reader_journey_scene",
                provider_name="fake",
                model_name="fake-scene-model",
                prompt_version="v1.1",
                schema_version="v1",
                attempt_no=2,
                invocation_kind="structural_repair",
                request_hash="j" * 64,
                input_snapshot_json=json.dumps({"owned_scene_ids_json": json.dumps([scene.id])}),
                parsed_response_json=json.dumps(parsed, ensure_ascii=False),
                status="failed",
                latency_ms=80,
                http_status_code=200,
                error_code="JOURNEY_QUESTION_CHAIN_INVALID",
                error_message="reader_question_in 不得全部为空",
            )
        )
        session.commit()
        journey_id = journey_run.id

    resp = client.get(f"/api/v1/reader-journey-runs/{journey_id}/progress")
    assert resp.status_code == 200
    body = resp.json()
    assert body["offline_replay_available"] is True
    assert body["offline_replayable_scene_count"] >= 1
    assert body["current_contract_version"] == "1.3"
    assert "旧版" in (body.get("user_error_message") or "")


def test_offline_replay_api(client):
    from app.db.session import get_session_factory
    from app.main import app

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        _book, chapter, run, _revision, scenes, paragraphs = _seed_run55_like(session)
        scene = scenes[0]
        journey_run = ReaderJourneyRun(
            analysis_run_id=run.id,
            book_id=_book.id,
            chapter_id=chapter.id,
            status="failed",
            provider_name="fake",
            model_name="fake-scene-model",
            scene_contract_version="1.1",
            total_scene_count=len(scenes),
            remaining_scene_count=len(scenes),
            remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
            cloud_consent=True,
            client_request_id="rj-api-offline",
            root_error_code="JOURNEY_QUESTION_CHAIN_INVALID",
        )
        session.add(journey_run)
        session.flush()
        parsed = _invocation134_payload(scene, [p.id for p in paragraphs[:12]])
        session.add(
            _make_invocation(
                run_id=run.id,
                task_type="reader_journey_scene",
                provider_name="fake",
                model_name="fake-scene-model",
                prompt_version="v1.1",
                schema_version="v1",
                attempt_no=2,
                invocation_kind="structural_repair",
                request_hash="k" * 64,
                input_snapshot_json=json.dumps({"owned_scene_ids_json": json.dumps([scene.id])}),
                parsed_response_json=json.dumps(parsed, ensure_ascii=False),
                status="failed",
                latency_ms=80,
                http_status_code=200,
                error_code="JOURNEY_QUESTION_CHAIN_INVALID",
                error_message="reader_question_in 不得全部为空",
            )
        )
        session.commit()
        journey_id = journey_run.id

    resp = client.post(
        f"/api/v1/reader-journey-runs/{journey_id}/scene-profiles/offline-replay",
        json={"confirmed": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["http_requests"] == 0
    assert scene.id in body["replayed_scene_ids"]
