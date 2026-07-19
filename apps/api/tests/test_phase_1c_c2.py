"""Phase 1C-C.2 Reader Journey visualization tests — zero cloud."""

from __future__ import annotations

import json

from sqlalchemy import func, select

from app.db.models import (
    ChapterReaderJourneySummary,
    ModelInvocation,
    ReaderJourneyPhase,
    ReaderJourneyRun,
    SceneReaderJourneyProfile,
)
from app.schemas.reader_journey import SceneReaderJourneyProfileItem
from app.services.reader_journey_contract_migrate import migrate_v11_profile_dict_to_v12
from app.services.reader_journey_pipeline import _persist_profile
from app.services.reader_journey_visual_calibration import VISUALIZATION_VERSION
from app.services.reader_journey_visualization import (
    canonicalize_question_chains,
    compute_scene_importance,
    rank_canonical_chains,
)
from tests.test_phase_1c_c1 import _enable_cloud, _seed_run55_like
from tests.test_phase_1c_c1_3 import _base_profile_dict


def _item(data: dict) -> SceneReaderJourneyProfileItem:
    return SceneReaderJourneyProfileItem.model_validate(migrate_v11_profile_dict_to_v12(data))


def test_canonicalize_merges_synonyms_not_distinct_objects():
    chains = [
        {
            "question_chain_id": "qc-a",
            "question_summary": "戏鬼身份究竟是什么",
            "created_scene_ordinal": 1,
            "carried_scene_ordinals": [2],
            "answered_scene_ordinal": None,
            "status": "carried",
            "strength": 70,
        },
        {
            "question_chain_id": "qc-b",
            "question_summary": "戏鬼真实身份到底是什么",
            "created_scene_ordinal": 2,
            "carried_scene_ordinals": [3],
            "answered_scene_ordinal": None,
            "status": "carried",
            "strength": 65,
        },
        {
            "question_chain_id": "qc-c",
            "question_summary": "井中水鬼危险从何而来",
            "created_scene_ordinal": 5,
            "carried_scene_ordinals": [],
            "answered_scene_ordinal": None,
            "status": "created",
            "strength": 60,
        },
    ]
    canonical = canonicalize_question_chains(chains)
    # Synonymous identity questions may merge; danger must stay separate.
    texts = [item["canonical_question"] for item in canonical]
    assert any("水鬼" in text or "危险" in text for text in texts)
    ids = {item["canonical_id"] for item in canonical}
    assert len(ids) >= 2


def test_rank_limits_primary_and_phase_chains():
    chains = [
        {
            "question_chain_id": f"qc-{i}",
            "question_summary": f"问题{i}关于戏鬼身份",
            "created_scene_ordinal": 1 + (i % 5),
            "carried_scene_ordinals": list(range(2, 2 + (i % 4))),
            "answered_scene_ordinal": None,
            "status": "carried",
            "strength": 40 + i,
        }
        for i in range(12)
    ]
    canonical = canonicalize_question_chains(chains)
    ranked = rank_canonical_chains(
        canonical,
        total_scenes=14,
        phase_boundaries=[
            {"ordinal": 1, "start_scene_ordinal": 1, "end_scene_ordinal": 3},
            {"ordinal": 2, "start_scene_ordinal": 4, "end_scene_ordinal": 7},
            {"ordinal": 3, "start_scene_ordinal": 8, "end_scene_ordinal": 11},
            {"ordinal": 4, "start_scene_ordinal": 12, "end_scene_ordinal": 14},
        ],
    )
    assert ranked
    assert all(0 <= item["importance"] <= 100 for item in ranked)
    primary = ranked[0]
    phase = ranked[1:5]
    secondary = ranked[5:]
    assert primary is not None
    assert len(phase) <= 4
    assert len(secondary) == max(0, len(ranked) - 5)


def test_chapter_end_short_scene_not_beat():
    data = _base_profile_dict(
        scene_id=19,
        scene_ordinal=14,
        paragraph_ids=["B0001-C0002-P0060", "B0001-C0002-P0061"],
    )
    data["hook_score"] = 40
    data["payoff_score"] = 40
    profile = _item(data)
    result = compute_scene_importance(
        profile=profile,
        engagement_score=45,
        paragraph_count=1,
        question_chain_importance=20,
        is_chapter_end=True,
        is_phase_boundary=False,
        beat_hint=True,
    )
    assert result["role"] == "core"
    assert any("chapter_end" in reason for reason in result["deterministic_reasons"])


def test_visualization_api_zero_cloud(client):
    from app.db.session import get_session_factory
    from app.main import app

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
            scene_prompt_version="v1.3",
            scene_contract_version="1.3",
            formula_version="1.0",
            total_scene_count=len(scenes),
            completed_scene_count=len(scenes),
            remaining_scene_count=0,
            cloud_consent=True,
            client_request_id="viz-c2",
            genre="suspense",
        )
        session.add(journey)
        session.flush()
        by_id = {p.id: p for p in paragraphs}
        for scene in scenes:
            start = int(scene.start_paragraph_id.rsplit("-P", 1)[-1])
            end = int(scene.end_paragraph_id.rsplit("-P", 1)[-1])
            pids = [f"B0001-C0002-P{start:04d}", f"B0001-C0002-P{min(end, 68):04d}"]
            if pids[0] == pids[1]:
                pids = [pids[0], f"B0001-C0002-P{min(end + 1, 68):04d}"]
            data = _base_profile_dict(scene_id=scene.id, scene_ordinal=scene.ordinal, paragraph_ids=pids)
            if scene.ordinal > 1:
                data["reader_question_in"] = [
                    {
                        "question": "戏鬼身份是否可信",
                        "source": "carried_from_previous",
                        "confidence": 0.6,
                    }
                ]
            item = _item(data)
            _persist_profile(session, journey, item, paragraphs_by_id=by_id, genre="suspense")
        # 4 phases covering 1-14
        bounds = [(1, 3), (4, 7), (8, 11), (12, 14)]
        for ordinal, (start, end) in enumerate(bounds, start=1):
            session.add(
                ReaderJourneyPhase(
                    reader_journey_run_id=journey.id,
                    ordinal=ordinal,
                    title=f"阶段{ordinal}",
                    start_scene_ordinal=start,
                    end_scene_ordinal=end,
                    primary_reader_question="戏鬼身份",
                    dominant_emotion="紧张",
                    reading_payoff="信息",
                    continuation_motivation="继续追查",
                    summary=f"阶段{ordinal}摘要",
                    confidence=0.7,
                    payload_json="{}",
                )
            )
        session.add(
            ChapterReaderJourneySummary(
                reader_journey_run_id=journey.id,
                chapter_value_summary="诊断",
                chapter_reader_question_chain_json='["戏鬼身份"]',
                overall_engagement_score=55,
                strongest_hook_scene_ids_json="[]",
                strongest_payoff_scene_ids_json="[]",
                risk_scene_ids_json="[]",
                positive_feedback_distribution_json="{}",
                hook_distribution_json="{}",
                emotion_trend_summary="",
                pacing_diagnosis_json='["节奏正常"]',
                one_sentence_diagnosis="主牵引是戏鬼身份的跨Scene承接，薄弱区间在前段。",
                deterministic_statistics_json=json.dumps(
                    {
                        "question_chains": [
                            {
                                "question_chain_id": "qc-1",
                                "question_summary": "戏鬼身份是什么",
                                "created_scene_ordinal": 1,
                                "carried_scene_ordinals": [2, 3],
                                "answered_scene_ordinal": None,
                                "status": "carried",
                                "strength": 80,
                            },
                            {
                                "question_chain_id": "qc-2",
                                "question_summary": "戏鬼真实身份到底是什么",
                                "created_scene_ordinal": 2,
                                "carried_scene_ordinals": [4],
                                "answered_scene_ordinal": None,
                                "status": "carried",
                                "strength": 70,
                            },
                        ]
                        + [
                            {
                                "question_chain_id": f"qc-x{i}",
                                "question_summary": f"次要问题{i}关于规则禁忌",
                                "created_scene_ordinal": 3 + (i % 8),
                                "carried_scene_ordinals": [],
                                "answered_scene_ordinal": None,
                                "status": "created",
                                "strength": 30 + i,
                            }
                            for i in range(10)
                        ],
                        "evidence_coverage_rate": 1.0,
                        "semantic_calibration_version": "1.3",
                    },
                    ensure_ascii=False,
                ),
                payload_json=json.dumps(
                    {"chapter_strengths": ["问题链"], "chapter_risks": ["前段低回报"]},
                    ensure_ascii=False,
                ),
                validation_status="valid",
            )
        )
        session.commit()
        run_id = run.id
        inv_before = session.scalar(select(func.count()).select_from(ModelInvocation))

    resp = client.get(f"/api/v1/analysis-runs/{run_id}/reader-journey")
    assert resp.status_code == 200
    body = resp.json()
    viz = body["visualization"]
    assert viz is not None
    assert viz["visualization_version"] == VISUALIZATION_VERSION
    assert len(viz["curve_series"]["engagement"]) == 14
    assert len(viz["phases"]) == 4
    assert len(viz["scene_nodes"]) == 14
    assert viz["primary_question_chain"] is not None
    assert len(viz["phase_question_chains"]) <= 4
    assert "formula_versions" in viz
    assert viz["calibration_status"]["semantic_source"] == "model+deterministic_calibration"
    assert viz["scene_nodes"][-1]["role"] == "core"
    assert "api_key" not in json.dumps(viz).lower()
    assert "sk-" not in json.dumps(viz)

    with factory() as session:
        inv_after = session.scalar(select(func.count()).select_from(ModelInvocation))
        assert inv_after == inv_before
        assert session.scalar(select(func.count()).select_from(ReaderJourneyRun)) == 1
        assert session.scalar(select(func.count()).select_from(SceneReaderJourneyProfile)) == 14
