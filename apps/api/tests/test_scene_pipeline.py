from fastapi.testclient import TestClient

import pytest

from app.schemas.scene import EvidenceField, SceneAnalysisResult, SceneBoundaryResult
from app.services.scene_pipeline import scene_ranges, validate_boundaries, validate_scene_analysis
from tests.fakes import FakeProvider

TEXT = """第一章 测试

清晨，林舟走进空荡的车站。

他要在发车前找到遗失的信封。

广播忽然宣布列车改到另一站台。

林舟赶到站台，终于从长椅下找到信封。
"""


def import_chapter(client: TestClient) -> int:
    response = client.post(
        "/api/v1/books/import", files={"file": ("原创测试.txt", TEXT.encode(), "text/plain")}
    )
    assert response.status_code == 201
    book_id = response.json()["book_id"]
    return client.get(f"/api/v1/books/{book_id}/chapters").json()[0]["id"]


def test_provider_api(client: TestClient) -> None:
    providers = client.get("/api/v1/model-providers")
    assert providers.status_code == 200
    assert providers.json()[0]["name"] == "fake"
    assert providers.json()[0]["capabilities"]["supports_json_schema"] is False
    body = providers.json()[0]
    assert body["capability_schema_version"] == "1c-a-2"
    for field in (
        "enabled", "configured", "connected", "healthy",
        "supports_boundary_candidates", "requires_boundary_review",
        "automatic_boundary_routing", "manual_boundary_candidate_eligible",
        "automatic_route_eligible", "manual_short_task_eligible", "allow_auto_route",
    ):
        assert type(body[field]) is bool
    assert type(body["manual_selection_blockers"]) is list
    assert type(body["automatic_route_blockers"]) is list
    health = client.get("/api/v1/model-providers/fake/health")
    assert health.json()["status"] == "healthy"
    assert client.get("/api/v1/model-providers/missing/health").status_code == 404


def test_fake_provider_complete_pipeline(client: TestClient) -> None:
    chapter_id = import_chapter(client)
    response = client.post(
        f"/api/v1/chapters/{chapter_id}/analysis-runs",
        json={"task_type": "scene_pipeline", "provider_name": "fake", "force": False},
    )
    assert response.status_code == 202
    run = client.get(f"/api/v1/analysis-runs/{response.json()['run_id']}").json()
    assert run["status"] == "succeeded"
    assert run["progress_current"] == run["progress_total"]
    assert run["progress_current"] > 0
    assert run["progress_current"] <= run["progress_total"]
    scenes = client.get(f"/api/v1/chapters/{chapter_id}/scenes").json()
    assert [item["scene_key"] for item in scenes] == ["B0001-C0001-S0001", "B0001-C0001-S0002"]
    assert scenes[0]["boundary_detected"] is True
    assert scenes[-1]["boundary_detected"] is False
    assert scenes[-1]["boundary_confidence"] == 0.0
    paragraphs = client.get(f"/api/v1/chapters/{chapter_id}/paragraphs").json()
    covered = []
    positions = {item["id"]: index for index, item in enumerate(paragraphs)}
    for scene in scenes:
        covered.extend(
            paragraphs[
                positions[scene["start_paragraph_id"]] : positions[scene["end_paragraph_id"]] + 1
            ]
        )
        artifacts = client.get(f"/api/v1/scenes/{scene['id']}/analysis-artifacts").json()
        assert len(artifacts) == 1
        assert artifacts[0]["validation_status"] == "valid"
    assert [item["id"] for item in covered] == [item["id"] for item in paragraphs]


def test_raise_if_cancel_requested_preserves_progress_total(testing_session) -> None:
    """Cooperative cancel refresh must not drop pending progress_total updates."""
    from app.db.models import AnalysisRun
    from app.services.task_cancellation import raise_if_cancel_requested

    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="fake",
        model="fake-scene-model",
        prompt_version="v1",
        schema_version="v1",
        input_hash="a" * 64,
        prompt_hash="b" * 64,
        status="running",
        progress_current=1,
        progress_total=1,
    )
    testing_session.add(run)
    testing_session.commit()
    run.progress_total = 3
    raise_if_cancel_requested(testing_session, run.id)
    assert run.progress_total == 3
    assert run.progress_current == 1


def test_failed_run_can_retry_without_overwrite(
    client: TestClient, fake_provider: FakeProvider
) -> None:
    chapter_id = import_chapter(client)
    fake_provider.responses = ["bad", "bad", "bad"]
    created = client.post(
        f"/api/v1/chapters/{chapter_id}/analysis-runs", json={"provider_name": "fake"}
    )
    old_id = created.json()["run_id"]
    assert client.get(f"/api/v1/analysis-runs/{old_id}").json()["status"] == "failed"
    retried = client.post(f"/api/v1/analysis-runs/{old_id}/retry")
    assert retried.status_code == 202
    new_id = retried.json()["run_id"]
    new_run = client.get(f"/api/v1/analysis-runs/{new_id}").json()
    assert new_run["status"] == "succeeded"
    assert new_run["retry_of_run_id"] == old_id
    assert client.get(f"/api/v1/analysis-runs/{old_id}").json()["status"] == "failed"


def analysis_with_evidence(scene_id: str, paragraph_id: str) -> SceneAnalysisResult:
    field = EvidenceField(summary="有依据", evidence_paragraph_ids=[paragraph_id])
    empty = EvidenceField(summary="", evidence_paragraph_ids=[])
    return SceneAnalysisResult(
        scene_id=scene_id,
        entry_state=field,
        goal=field,
        obstacle=empty,
        key_actions=[],
        turning_point=empty,
        outcome=field,
        unresolved_question=empty,
        function_tags=["事件推进"],
        confidence=0.8,
    )


def test_single_paragraph_scene_allows_identical_evidence() -> None:
    pid = "B0001-C0001-P0001"
    result = SceneAnalysisResult(
        scene_id="B0001-C0001-S0001",
        entry_state=EvidenceField(summary="进入", evidence_paragraph_ids=[pid]),
        goal=EvidenceField(summary="目标", evidence_paragraph_ids=[pid]),
        obstacle=EvidenceField(summary="阻碍", evidence_paragraph_ids=[pid]),
        key_actions=[EvidenceField(summary="行动", evidence_paragraph_ids=[pid])],
        turning_point=EvidenceField(summary="", evidence_paragraph_ids=[]),
        outcome=EvidenceField(summary="结果", evidence_paragraph_ids=[pid]),
        unresolved_question=EvidenceField(summary="悬念", evidence_paragraph_ids=[pid]),
        function_tags=["悬念设置"],
        confidence=0.9,
    )
    validate_scene_analysis(result, "B0001-C0001-S0001", {pid}, True)


def test_multi_paragraph_identical_evidence_allowed_on_short_scene() -> None:
    """Short scenes (2 paragraphs) may share full-scene evidence across fields."""
    ids = {"B0001-C0001-P0001", "B0001-C0001-P0002"}
    whole = ["B0001-C0001-P0001", "B0001-C0001-P0002"]
    result = SceneAnalysisResult(
        scene_id="B0001-C0001-S0001",
        entry_state=EvidenceField(summary="进入状态：对话开始", evidence_paragraph_ids=list(whole)),
        goal=EvidenceField(summary="目标：弄清对方态度", evidence_paragraph_ids=list(whole)),
        obstacle=EvidenceField(summary="阻碍：信息不完整", evidence_paragraph_ids=list(whole)),
        key_actions=[EvidenceField(summary="行动：追问细节", evidence_paragraph_ids=list(whole))],
        turning_point=EvidenceField(summary="", evidence_paragraph_ids=[]),
        outcome=EvidenceField(summary="结果：悬念仍在", evidence_paragraph_ids=list(whole)),
        unresolved_question=EvidenceField(summary="悬念：对方隐瞒什么", evidence_paragraph_ids=list(whole)),
        function_tags=["事件推进"],
        confidence=0.9,
    )
    validate_scene_analysis(
        result,
        "B0001-C0001-S0001",
        ids,
        True,
        ordered_paragraph_ids=whole,
    )


def test_boundary_and_range_validation() -> None:
    class P:
        def __init__(self, identifier: str, index: int):
            self.id, self.paragraph_index = identifier, index

    paragraphs = [P(f"B0001-C0001-P{i:04d}", i) for i in range(1, 5)]
    result = SceneBoundaryResult(
        chapter_id="B0001-C0001",
        boundaries=[
            {"after_paragraph_id": paragraphs[1].id, "reasons": ["地点发生变化"], "confidence": 0.8}
        ],
        overall_confidence=0.8,
    )
    validate_boundaries(result, "B0001-C0001", paragraphs)
    ranges = scene_ranges(paragraphs, [paragraphs[1].id])
    assert [(a.id, b.id) for a, b in ranges] == [
        (paragraphs[0].id, paragraphs[1].id),
        (paragraphs[2].id, paragraphs[3].id),
    ]
    invalid = SceneBoundaryResult(
        chapter_id="B0001-C0001",
        boundaries=[
            {
                "after_paragraph_id": "B0001-C0001-P9999",
                "reasons": ["地点发生变化"],
                "confidence": 0.8,
            }
        ],
        overall_confidence=0.8,
    )
    with pytest.raises(ValueError):
        validate_boundaries(invalid, "B0001-C0001", paragraphs)
