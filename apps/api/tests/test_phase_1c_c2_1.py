"""Phase 1C-C.2.1 Reader Journey visual calibration tests — zero cloud."""

from __future__ import annotations

import copy

from sqlalchemy import func, select

from app.db.models import ModelInvocation, ReaderJourneyPhase, ReaderJourneyRun
from app.schemas.reader_journey import SceneReaderJourneyProfileItem
from app.services.reader_journey_contract_migrate import migrate_v11_profile_dict_to_v12
from app.services.reader_journey_pipeline import _persist_profile
from app.services.reader_journey_visual_calibration import (
    VISUALIZATION_VERSION,
    build_density_warnings,
    build_question_clusters,
    classify_scene_levels,
    derive_and_select_payoffs,
    select_visible_hooks,
)
from app.services.reader_journey_visualization import build_reader_journey_visualization
from tests.test_phase_1c_c1 import _enable_cloud, _seed_run55_like
from tests.test_phase_1c_c1_3 import _base_profile_dict


def _item(data: dict) -> SceneReaderJourneyProfileItem:
    return SceneReaderJourneyProfileItem.model_validate(migrate_v11_profile_dict_to_v12(data))


def _scene_paragraph_ids(scene) -> list[str]:
    start = int(scene.start_paragraph_id.rsplit("-P", 1)[-1])
    end = int(scene.end_paragraph_id.rsplit("-P", 1)[-1])
    pids = [f"B0001-C0002-P{start:04d}", f"B0001-C0002-P{min(end, 68):04d}"]
    if pids[0] == pids[1]:
        pids = [pids[0], f"B0001-C0002-P{min(end + 1, 68):04d}"]
    return pids


def _profile(
    ordinal: int,
    *,
    hook_score: int = 40,
    payoff_score: int = 40,
    engagement: int = 45,
    hooks: list | None = None,
    payoffs: list | None = None,
    information_changes: list | None = None,
    reader_question_created: list | None = None,
    reader_question_answered: list | None = None,
    paragraph_count: int = 4,
) -> tuple[SceneReaderJourneyProfileItem, dict[int, int], dict[int, int]]:
    data = _base_profile_dict(
        scene_id=ordinal,
        scene_ordinal=ordinal,
        paragraph_ids=[f"B0001-C0002-P{ordinal:04d}", f"B0001-C0002-P{ordinal + 1:04d}"],
    )
    data["hook_score"] = hook_score
    data["payoff_score"] = payoff_score
    if hooks is not None:
        data["hooks"] = hooks
    if payoffs is not None:
        data["payoffs"] = payoffs
    if information_changes is not None:
        data["information_changes"] = information_changes
    if reader_question_created is not None:
        data["reader_question_created"] = reader_question_created
    if reader_question_answered is not None:
        data["reader_question_answered"] = reader_question_answered
    profile = _item(data)
    return (
        profile,
        {ordinal: engagement},
        {ordinal: paragraph_count},
    )


def test_core_distribution_warning_when_too_many_cores():
    profiles: list[SceneReaderJourneyProfileItem] = []
    engagement: dict[int, int] = {}
    paragraphs: dict[int, int] = {}
    for ordinal in range(1, 5):
        profile, eng, para = _profile(ordinal, hook_score=85, payoff_score=85, engagement=80)
        profiles.append(profile)
        engagement.update(eng)
        paragraphs.update(para)
    rows = classify_scene_levels(
        profiles=profiles,
        engagement_by_ordinal=engagement,
        paragraph_counts=paragraphs,
        chain_importance_by_scene={},
        phase_start_ordinals=set(),
        phase_end_ordinals=set(),
        primary_created_scene=1,
        primary_answer_or_transform_scenes=set(),
        max_ordinal=4,
    )
    role_counts = {
        "core": sum(1 for row in rows if row["final_level"] == "core"),
        "secondary": sum(1 for row in rows if row["final_level"] == "secondary"),
        "beat": sum(1 for row in rows if row["final_level"] == "beat"),
    }
    warnings = build_density_warnings(
        scene_count=4,
        role_counts=role_counts,
        visible_hook_count=4,
        visible_cluster_count=1,
    )
    assert any(item["code"] == "VISUAL_CORE_DISTRIBUTION_SUSPICIOUS" for item in warnings)


def test_chapter_end_scene_stays_core():
    profile, engagement, paragraphs = _profile(
        14,
        hook_score=30,
        payoff_score=30,
        engagement=35,
        paragraph_count=1,
    )
    rows = classify_scene_levels(
        profiles=[profile],
        engagement_by_ordinal=engagement,
        paragraph_counts=paragraphs,
        chain_importance_by_scene={},
        phase_start_ordinals=set(),
        phase_end_ordinals=set(),
        primary_created_scene=None,
        primary_answer_or_transform_scenes=set(),
        max_ordinal=14,
    )
    assert rows[0]["final_level"] == "core"
    assert rows[0]["forced_floor_reason"] == "chapter_end"


def test_mid_engagement_scene_not_auto_core():
    data = _base_profile_dict(
        scene_id=5,
        scene_ordinal=5,
        paragraph_ids=["B0001-C0002-P0050", "B0001-C0002-P0051"],
    )
    data["hook_score"] = 20
    data["payoff_score"] = 20
    data["hooks"] = []
    data["payoffs"] = []
    data["information_changes"] = []
    data["reader_question_created"] = []
    data["reader_question_out"] = []
    profile = _item(data)
    rows = classify_scene_levels(
        profiles=[profile],
        engagement_by_ordinal={5: 50},
        paragraph_counts={5: 4},
        chain_importance_by_scene={},
        phase_start_ordinals=set(),
        phase_end_ordinals=set(),
        primary_created_scene=None,
        primary_answer_or_transform_scenes=set(),
        max_ordinal=10,
    )
    assert rows[0]["final_level"] != "core"


def test_hook_selection_and_suppression_reasons():
    profile, _, _ = _profile(
        1,
        hooks=[
            {
                "type": "identity",
                "summary": "强钩子",
                "strength": 90,
                "gap": "",
                "continue_drive": "",
                "evidence_paragraph_ids": ["B0001-C0002-P0001"],
            },
            {
                "type": "information",
                "summary": "弱钩子",
                "strength": 40,
                "gap": "",
                "continue_drive": "",
                "evidence_paragraph_ids": ["B0001-C0002-P0002"],
            },
        ],
    )
    profile.reader_question_in = []
    profile.reader_question_created = []
    profile.reader_question_out = []
    weak_profile, _, _ = _profile(
        2,
        hooks=[
            {
                "type": "information",
                "summary": "中等钩子但不达主图阈值",
                "strength": 70,
                "gap": "",
                "continue_drive": "",
                "evidence_paragraph_ids": ["B0001-C0002-P0003"],
            }
        ],
    )
    weak_profile.reader_question_in = []
    weak_profile.reader_question_created = []
    weak_profile.reader_question_out = []
    result = select_visible_hooks(
        profiles=[profile, weak_profile],
        phase_end_ordinals=set(),
        max_ordinal=10,
        primary_chain=None,
        phase_chains=[],
    )
    assert result["visible_hook_count"] == 1
    assert result["suppressed_hook_count"] == 2
    assert any(item["suppression_reason"] == "selected_stronger_hook_in_scene" for item in result["suppressed_hooks"])
    assert any(item["suppression_reason"] == "below_visible_strength_threshold" for item in result["suppressed_hooks"])


def test_all_hooks_remain_on_scene_nodes(client):
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
            client_request_id="viz-c2-1-hooks",
            genre="suspense",
        )
        session.add(journey)
        session.flush()
        by_id = {p.id: p for p in paragraphs}
        for scene in scenes:
            pids = _scene_paragraph_ids(scene)
            data = _base_profile_dict(scene_id=scene.id, scene_ordinal=scene.ordinal, paragraph_ids=pids)
            data["hooks"] = data["hooks"] + [
                {
                    "type": "information",
                    "summary": f"额外钩子 {scene.ordinal}",
                    "strength": 35,
                    "gap": "测试",
                    "continue_drive": "中",
                    "evidence_paragraph_ids": pids[:1],
                }
            ]
            item = _item(data)
            _persist_profile(session, journey, item, paragraphs_by_id=by_id, genre="suspense")
        session.commit()
        run_id = run.id

    resp = client.get(f"/api/v1/analysis-runs/{run_id}/reader-journey")
    viz = resp.json()["visualization"]
    total_hooks = sum(len(node["hooks"]) for node in viz["scene_nodes"])
    assert total_hooks >= viz["all_hook_count"]
    assert viz["all_hook_count"] > viz["visible_hook_count"]


def test_micro_payoff_derivation_and_dedupe():
    profile, _, _ = _profile(
        1,
        payoffs=[{"type": "information", "summary": "同一回报", "strength": 60, "evidence_paragraph_ids": ["B0001-C0002-P0001"]}],
        reader_question_answered=[
            {
                "question": "身份是什么",
                "answer_summary": "同一回报",
                "answer_degree": "full",
                "evidence_paragraph_ids": ["B0001-C0002-P0001"],
            }
        ],
        information_changes=[
            {
                "type": "identity_clue",
                "summary": "线索回报",
                "certainty": "fact",
                "evidence_paragraph_ids": ["B0001-C0002-P0002"],
            }
        ],
    )
    result = derive_and_select_payoffs(
        profiles=[profile],
        phases=[],
        max_ordinal=1,
    )
    assert result["derived_payoff_count"] >= 2
    assert result["deduped_payoff_count"] < result["semantic_payoff_count"] + result["derived_payoff_count"]


def test_question_clusters_alias_vs_escalation():
    ranked = [
        {
            "canonical_id": "cqc-a",
            "canonical_question": "戏鬼身份是什么",
            "question_type": "identity",
            "created_scene": 1,
            "importance": 80,
            "status": "carried",
        },
        {
            "canonical_id": "cqc-b",
            "canonical_question": "戏鬼身份是什么",
            "question_type": "identity",
            "created_scene": 2,
            "importance": 70,
            "status": "carried",
        },
    ]
    result = build_question_clusters(
        ranked,
        phase_boundaries=[{"ordinal": 1, "start_scene_ordinal": 1, "end_scene_ordinal": 5}],
    )
    assert result["question_cluster_count"] == 1
    assert len(result["question_clusters"][0]["member_chain_ids"]) == 2
    assert result["question_clusters"][0]["merge_reason"] in {"alias", "escalation"}


def test_different_entities_not_clustered():
    ranked = [
        {
            "canonical_id": "cqc-a",
            "canonical_question": "戏鬼身份究竟是什么",
            "question_type": "identity",
            "created_scene": 1,
            "importance": 80,
            "status": "carried",
        },
        {
            "canonical_id": "cqc-b",
            "canonical_question": "井中水鬼危险从何而来",
            "question_type": "danger",
            "created_scene": 5,
            "importance": 70,
            "status": "created",
        },
    ]
    result = build_question_clusters(
        ranked,
        phase_boundaries=[
            {"ordinal": 1, "start_scene_ordinal": 1, "end_scene_ordinal": 3},
            {"ordinal": 2, "start_scene_ordinal": 4, "end_scene_ordinal": 7},
        ],
    )
    assert result["question_cluster_count"] == 2


def test_visible_clusters_limited_to_five():
    ranked = [
        {
            "canonical_id": f"cqc-{index}",
            "canonical_question": f"独立问题{index}关于空间边界",
            "question_type": "space",
            "created_scene": 1 + index * 2,
            "importance": 90 - index,
            "status": "created",
        }
        for index in range(8)
    ]
    phase_boundaries = [
        {"ordinal": index + 1, "start_scene_ordinal": 1 + index * 2, "end_scene_ordinal": 2 + index * 2}
        for index in range(8)
    ]
    result = build_question_clusters(ranked, phase_boundaries=phase_boundaries)
    assert len(result["visible_question_clusters"]) <= 5


def test_visualization_version_is_1_1(client):
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
            client_request_id="viz-c2-1-version",
            genre="suspense",
        )
        session.add(journey)
        session.flush()
        by_id = {p.id: p for p in paragraphs}
        original_payloads: list[str] = []
        for scene in scenes:
            pids = _scene_paragraph_ids(scene)
            data = _base_profile_dict(scene_id=scene.id, scene_ordinal=scene.ordinal, paragraph_ids=pids)
            item = _item(data)
            original_payloads.append(item.model_dump_json())
            _persist_profile(session, journey, item, paragraphs_by_id=by_id, genre="suspense")
        session.commit()
        run_id = run.id
        journey_id = journey.id

    resp = client.get(f"/api/v1/analysis-runs/{run_id}/reader-journey")
    viz = resp.json()["visualization"]
    assert viz["visualization_version"] == VISUALIZATION_VERSION == "1.1"
    assert viz["formula_versions"]["hook_select_formula_version"] == "1.1"
    assert "question_clusters" in viz
    assert "visual_density_warnings" in viz

    with factory() as session:
        journey = session.get(ReaderJourneyRun, journey_id)
        built = build_reader_journey_visualization(session, journey)
        assert built is not None
        assert built["visualization_version"] == "1.1"


def test_does_not_mutate_profile_payload(client):
    from app.db.models import SceneReaderJourneyProfile
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
            client_request_id="viz-c2-1-immutable",
            genre="suspense",
        )
        session.add(journey)
        session.flush()
        by_id = {p.id: p for p in paragraphs}
        snapshots: dict[int, str] = {}
        for scene in scenes:
            pids = _scene_paragraph_ids(scene)
            data = copy.deepcopy(
                _base_profile_dict(scene_id=scene.id, scene_ordinal=scene.ordinal, paragraph_ids=pids)
            )
            item = _item(data)
            _persist_profile(session, journey, item, paragraphs_by_id=by_id, genre="suspense")
        for row in session.scalars(
            select(SceneReaderJourneyProfile).where(
                SceneReaderJourneyProfile.reader_journey_run_id == journey.id
            )
        ):
            snapshots[row.scene_id] = row.payload_json
        session.commit()
        run_id = run.id
        journey_id = journey.id

    client.get(f"/api/v1/analysis-runs/{run_id}/reader-journey")

    with factory() as session:
        rows = session.scalars(
            select(SceneReaderJourneyProfile).where(
                SceneReaderJourneyProfile.reader_journey_run_id == journey_id
            )
        )
        for row in rows:
            assert row.payload_json == snapshots[row.scene_id]


def test_visualization_api_zero_cloud_no_new_invocations(client):
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
            client_request_id="viz-c2-1-zero-cloud",
            genre="suspense",
        )
        session.add(journey)
        session.flush()
        by_id = {p.id: p for p in paragraphs}
        for scene in scenes:
            pids = _scene_paragraph_ids(scene)
            data = _base_profile_dict(scene_id=scene.id, scene_ordinal=scene.ordinal, paragraph_ids=pids)
            item = _item(data)
            _persist_profile(session, journey, item, paragraphs_by_id=by_id, genre="suspense")
        for ordinal, (start, end) in enumerate([(1, 3), (4, 7), (8, 11), (12, 14)], start=1):
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
        session.commit()
        run_id = run.id
        inv_before = session.scalar(select(func.count()).select_from(ModelInvocation))

    resp = client.get(f"/api/v1/analysis-runs/{run_id}/reader-journey")
    assert resp.status_code == 200

    with factory() as session:
        inv_after = session.scalar(select(func.count()).select_from(ModelInvocation))
        assert inv_after == inv_before
