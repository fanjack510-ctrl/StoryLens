"""Phase 1C-C.1.5 Reader Journey Semantic Calibration tests (zero cloud)."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.db.models import ChapterReaderJourneySummary, SceneReaderJourneyProfile
from app.schemas.reader_journey import (
    SCENE_CONTRACT_VERSION,
    SceneReaderJourneyProfileItem,
)
from app.services.reader_journey_contract_migrate import migrate_v11_profile_dict_to_v12
from app.services.reader_journey_semantic_calibrate import (
    apply_deterministic_qin,
    build_journey_nodes,
    contains_banned_chapter_phrase,
)
from app.services.reader_journey_validation import validate_chapter_synthesis, validate_score_distribution
from app.schemas.reader_journey import ChapterReaderJourneySynthesisResult, ReaderJourneyPhaseItem
from app.services.validation_errors import StructuralValidationError
from tests.test_phase_1c_c1 import _enable_cloud, _seed_run55_like
from tests.test_phase_1c_c1_3 import _base_profile_dict


def _profile_from_dict(data: dict) -> SceneReaderJourneyProfileItem:
    return SceneReaderJourneyProfileItem.model_validate(migrate_v11_profile_dict_to_v12(data))


def test_deterministic_qin_from_prior_outs():
    p1 = _profile_from_dict(
        {
            **_base_profile_dict(scene_id=1, scene_ordinal=1, paragraph_ids=["B0001-C0002-P0001", "B0001-C0002-P0002"]),
            "reader_question_in": [],
            "reader_question_created": [
                {
                    "question": "戏鬼身份是否可信",
                    "trigger_summary": "异常细节",
                    "strength": 70,
                    "evidence_paragraph_ids": ["B0001-C0002-P0001"],
                }
            ],
            "reader_question_out": [
                {
                    "question": "戏鬼身份是否可信",
                    "origin": "created_here",
                    "strength": 70,
                    "evidence_paragraph_ids": ["B0001-C0002-P0001"],
                    "hook_type": "identity",
                }
            ],
        }
    )
    p2 = _profile_from_dict(
        {
            **_base_profile_dict(scene_id=2, scene_ordinal=2, paragraph_ids=["B0001-C0002-P0003", "B0001-C0002-P0004"]),
            "reader_question_in": [],
            "reader_question_out": [
                {
                    "question": "危险来源是什么",
                    "origin": "created_here",
                    "strength": 60,
                    "evidence_paragraph_ids": ["B0001-C0002-P0003"],
                    "hook_type": "danger",
                }
            ],
        }
    )
    calibrated = apply_deterministic_qin([p1, p2])
    assert calibrated[0].reader_question_in == []
    assert calibrated[1].reader_question_in
    assert calibrated[1].reader_question_in[0].question == "戏鬼身份是否可信"
    assert calibrated[1].reader_question_in[0].source == "carried_from_previous"


def test_forbid_all_empty_qin_and_consecutive_no_payoff():
    profiles = []
    for ordinal in range(1, 5):
        data = _base_profile_dict(
            scene_id=ordinal,
            scene_ordinal=ordinal,
            paragraph_ids=[f"B0001-C0002-P{ordinal:04d}", f"B0001-C0002-P{ordinal+10:04d}"],
        )
        data["reader_question_in"] = []
        data["payoffs"] = []
        data["payoff_score"] = 10
        data["risk_points"] = []
        data["evidence_paragraph_ids"] = [f"B0001-C0002-P{ordinal:04d}", f"B0001-C0002-P{ordinal+10:04d}"]
        profiles.append(_profile_from_dict(data))
    try:
        validate_score_distribution(profiles)
        assert False, "expected failure"
    except StructuralValidationError as exc:
        assert exc.error_code == "JOURNEY_QUESTION_CHAIN_ALL_EMPTY_IN"


def test_chapter_diagnosis_bans_generic_phrases():
    result = ChapterReaderJourneySynthesisResult(
        contract_version="1.1",
        phases=[
            ReaderJourneyPhaseItem(
                ordinal=1,
                title="a",
                start_scene_ordinal=1,
                end_scene_ordinal=2,
                primary_reader_question="q",
                dominant_emotion="紧张",
                reading_payoff="信息",
                continuation_motivation="继续",
                summary="阶段一",
                confidence=0.5,
            ),
            ReaderJourneyPhaseItem(
                ordinal=2,
                title="b",
                start_scene_ordinal=3,
                end_scene_ordinal=4,
                primary_reader_question="q2",
                dominant_emotion="恐惧",
                reading_payoff="身份",
                continuation_motivation="核查",
                summary="阶段二",
                confidence=0.5,
            ),
            ReaderJourneyPhaseItem(
                ordinal=3,
                title="c",
                start_scene_ordinal=5,
                end_scene_ordinal=6,
                primary_reader_question="q3",
                dominant_emotion="不安",
                reading_payoff="规则",
                continuation_motivation="求证",
                summary="阶段三",
                confidence=0.5,
            ),
        ],
        chapter_reader_question_chain=["戏鬼身份"],
        pacing_diagnosis=["层层剥开真相"],
        chapter_strengths=["细节"],
        chapter_risks=["节奏"],
        one_sentence_diagnosis="成功确立了恐怖氛围并推向高潮",
    )
    assert contains_banned_chapter_phrase(result.one_sentence_diagnosis)
    try:
        validate_chapter_synthesis(result, total_scene_count=6, enforce_anti_generic=True)
        assert False, "expected banned phrase failure"
    except StructuralValidationError as exc:
        assert exc.error_code == "JOURNEY_CHAPTER_DIAGNOSIS_GENERIC"


def test_journey_nodes_mark_short_scenes_as_beat(testing_session):
    _enable_cloud(testing_session)
    _book, chapter, run, revision, scenes, paragraphs = _seed_run55_like(testing_session)
    profiles = []
    for scene in scenes:
        start = int(scene.start_paragraph_id.rsplit("-P", 1)[-1])
        end = int(scene.end_paragraph_id.rsplit("-P", 1)[-1])
        pids = [f"B0001-C0002-P{start:04d}", f"B0001-C0002-P{end:04d}"]
        if pids[0] == pids[1]:
            pids = [pids[0], f"B0001-C0002-P{min(end + 1, 68):04d}"]
        data = _base_profile_dict(scene_id=scene.id, scene_ordinal=scene.ordinal, paragraph_ids=pids)
        data["evidence_paragraph_ids"] = pids
        if scene.ordinal > 1:
            data["reader_question_in"] = [
                {
                    "question": "上一场遗留问题",
                    "source": "carried_from_previous",
                    "confidence": 0.6,
                }
            ]
        profiles.append(_profile_from_dict(data))
    nodes = build_journey_nodes(scenes, profiles)
    by_ord = {node["scene_ordinal"]: node["role"] for node in nodes}
    assert by_ord[3] == "beat"
    assert by_ord[4] == "beat"
    assert by_ord[5] == "beat"
    assert by_ord[6] == "beat"
    assert by_ord[1] == "primary"


def test_semantic_recalibrate_api_zero_cost(client):
    from app.db.session import get_session_factory
    from app.main import app
    from app.db.models import ReaderJourneyRun
    from app.services.reader_journey_pipeline import _persist_profile

    factory = app.dependency_overrides[get_session_factory]()
    with factory() as session:
        _enable_cloud(session)
        _book, chapter, run, _revision, scenes, paragraphs = _seed_run55_like(session)
        journey = ReaderJourneyRun(
            analysis_run_id=run.id,
            book_id=_book.id,
            chapter_id=chapter.id,
            status="succeeded",
            provider_name="fake",
            model_name="fake",
            planner_version="1.1",
            scene_prompt_version="v1.2",
            scene_contract_version="1.2",
            total_scene_count=len(scenes),
            completed_scene_count=len(scenes),
            remaining_scene_count=0,
            cloud_consent=True,
            client_request_id="semantic-recal",
            genre="suspense",
        )
        session.add(journey)
        session.flush()
        by_id = {p.id: p for p in paragraphs}
        for scene in scenes:
            start = int(scene.start_paragraph_id.rsplit("-P", 1)[-1])
            end = int(scene.end_paragraph_id.rsplit("-P", 1)[-1])
            pids = [f"B0001-C0002-P{start:04d}", f"B0001-C0002-P{end:04d}"]
            if pids[0] == pids[1]:
                pids = [pids[0], f"B0001-C0002-P{min(end + 1, 68):04d}"]
            data = _base_profile_dict(scene_id=scene.id, scene_ordinal=scene.ordinal, paragraph_ids=pids)
            data["reader_question_in"] = []
            data["payoffs"] = []
            data["payoff_score"] = 15
            data["evidence_paragraph_ids"] = pids
            item = _profile_from_dict(data)
            _persist_profile(session, journey, item, paragraphs_by_id=by_id, genre="suspense")
        session.add(
            ChapterReaderJourneySummary(
                reader_journey_run_id=journey.id,
                chapter_value_summary="成功确立了恐怖氛围",
                chapter_reader_question_chain_json="[]",
                overall_engagement_score=50,
                strongest_hook_scene_ids_json="[]",
                strongest_payoff_scene_ids_json="[]",
                risk_scene_ids_json="[]",
                positive_feedback_distribution_json="{}",
                hook_distribution_json="{}",
                emotion_trend_summary="",
                pacing_diagnosis_json=json.dumps(["层层剥开并推向高潮"], ensure_ascii=False),
                one_sentence_diagnosis="成功确立了恐怖氛围并推向高潮",
                deterministic_statistics_json="{}",
                payload_json=json.dumps(
                    {
                        "one_sentence_diagnosis": "成功确立了恐怖氛围并推向高潮",
                        "pacing_diagnosis": ["层层剥开并推向高潮"],
                    },
                    ensure_ascii=False,
                ),
                validation_status="valid",
            )
        )
        session.commit()
        journey_id = journey.id

    resp = client.post(
        f"/api/v1/reader-journey-runs/{journey_id}/semantic-recalibrate",
        json={"confirmed": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["http_requests"] == 0
    assert body["tokens"] == 0
    assert body["cost"] == 0.0
    assert body["empty_qin_remaining"] == 0
    assert body["scene_contract_version"] == SCENE_CONTRACT_VERSION
    assert body["calibrated_profile_count"] == 14
    assert any(node["role"] == "beat" for node in body["journey_nodes"])
    assert not contains_banned_chapter_phrase(body["one_sentence_diagnosis"])

    with factory() as session:
        rows = list(
            session.scalars(
                select(SceneReaderJourneyProfile)
                .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_id)
                .order_by(SceneReaderJourneyProfile.scene_ordinal)
            )
        )
        empty_non_opening = 0
        for row in rows:
            payload = json.loads(row.payload_json)
            if row.scene_ordinal > 1 and not payload.get("reader_question_in"):
                empty_non_opening += 1
            if row.scene_ordinal > 1:
                assert payload.get("reader_question_in")
            if payload.get("hooks"):
                hook = payload["hooks"][0]
                assert hook.get("known") and hook.get("gap")
                assert hook.get("continue_drive") and hook.get("next_handoff")
        assert empty_non_opening == 0
        summary = session.scalar(
            select(ChapterReaderJourneySummary).where(
                ChapterReaderJourneySummary.reader_journey_run_id == journey_id
            )
        )
        assert summary is not None
        assert not contains_banned_chapter_phrase(summary.one_sentence_diagnosis)
        stats = json.loads(summary.deterministic_statistics_json)
        assert stats.get("journey_nodes")
        assert stats.get("question_chains")
