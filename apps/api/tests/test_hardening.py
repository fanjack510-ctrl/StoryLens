from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import AnalysisRun, Chapter, ModelInvocation
from app.model_gateway.base import ProviderRequestError
from app.model_gateway.gateway import ModelGateway
from app.schemas.scene import SceneBoundaryResult
from app.services.prompt_service import load_prompt
from app.services.scene_pipeline import aggregate_boundary_candidates, mark_interrupted_runs_failed
from app.services.structured_output import generate_validated
from tests.fakes import FakeProvider
from tests.profile_gate_helpers import confirm_book_profile
from tests.test_scene_pipeline import import_chapter


def make_run(session, status: str = "running") -> AnalysisRun:
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        prompt_hash="x",
        input_hash="x",
        status=status,
    )
    session.add(run)
    session.commit()
    return run


@pytest.mark.asyncio
async def test_repair_contains_snapshot_and_provider_retry_is_not_repair(testing_session) -> None:
    valid = '{"chapter_id":"B0001-C0001","boundaries":[],"overall_confidence":0.7}'
    provider = FakeProvider(["bad", valid])
    run = make_run(testing_session)
    snapshot = {"paragraphs": [{"id": "B0001-C0001-P0001", "text": "正文"}]}
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name="fake",
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot=snapshot,
        user_content="original task",
        business_validator=lambda _: None,
    )
    repair = provider.requests[1].messages[1]["content"]
    assert "B0001-C0001-P0001" in repair and "original task" in repair
    invocations = list(
        testing_session.scalars(select(ModelInvocation).order_by(ModelInvocation.id))
    )
    assert [item.invocation_kind for item in invocations] == ["initial", "json_repair"]

    provider = FakeProvider([ProviderRequestError("offline", 503), valid])
    run = make_run(testing_session)
    await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name="fake",
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot=snapshot,
        user_content="original task",
        business_validator=lambda _: None,
    )
    rows = list(
        testing_session.scalars(
            select(ModelInvocation)
            .where(ModelInvocation.run_id == run.id)
            .order_by(ModelInvocation.id)
        )
    )
    assert [item.invocation_kind for item in rows] == ["initial", "provider_retry"]
    assert rows[0].raw_response_text == "" and rows[0].http_status_code == 503
    assert provider.requests[0].messages == provider.requests[1].messages


def test_failed_run_scene_isolated_but_auditable(
    client: TestClient, fake_provider: FakeProvider
) -> None:
    chapter_id = import_chapter(client)
    boundary = '{"chapter_id":"B0001-C0001","boundaries":[{"after_paragraph_id":"B0001-C0001-P0002","reasons":["地点发生变化"],"confidence":0.9}],"overall_confidence":0.8}'
    fake_provider.responses = [boundary, "bad", "bad", "bad"]
    created = client.post(
        f"/api/v1/chapters/{chapter_id}/analysis-runs", json={"provider_name": "fake"}
    )
    run_id = created.json()["run_id"]
    assert client.get(f"/api/v1/analysis-runs/{run_id}").json()["status"] == "failed"
    partial = client.get(f"/api/v1/analysis-runs/{run_id}/scenes").json()
    assert len(partial) == 1
    assert client.get(f"/api/v1/scenes/{partial[0]['scene_key']}").status_code == 404
    audit = client.get(f"/api/v1/analysis-runs/{run_id}/model-invocations").json()
    assert audit and audit[0]["raw_response_text"] is None


def test_boundary_vote_and_no_boundary_confidence() -> None:
    class P:
        def __init__(self, identifier: str, index: int):
            self.id, self.paragraph_index = identifier, index

    paragraphs = [P(f"B0001-C0001-P{i:04d}", i) for i in range(1, 6)]
    windows = [paragraphs[:4], paragraphs[1:]]
    result1 = SceneBoundaryResult.model_validate(
        {
            "chapter_id": "B0001-C0001",
            "boundaries": [
                {
                    "after_paragraph_id": paragraphs[2].id,
                    "reasons": ["地点发生变化"],
                    "confidence": 0.8,
                }
            ],
            "overall_confidence": 0.6,
        }
    )
    result2 = SceneBoundaryResult.model_validate(
        {"chapter_id": "B0001-C0001", "boundaries": [], "overall_confidence": 0.4}
    )
    adopted, stats, rejected = aggregate_boundary_candidates(
        paragraphs, windows, [result1, result2], 0.65, 0.6
    )
    assert adopted == [] and rejected[0]["vote_ratio"] == 0.5
    assert sum(item.overall_confidence for item in [result1, result2]) / 2 == 0.5


def test_run_time_state_and_interruption(testing_session) -> None:
    queued = make_run(testing_session, "queued")
    running = make_run(testing_session, "running")
    assert queued.created_at and queued.queued_at and queued.started_at is None
    running.started_at = datetime.now(timezone.utc)
    testing_session.commit()
    mark_interrupted_runs_failed(testing_session)
    testing_session.refresh(queued)
    testing_session.refresh(running)
    assert queued.error_code == "PROCESS_INTERRUPTED_BEFORE_START"
    assert running.error_code == "PROCESS_INTERRUPTED"
    assert queued.completed_at and running.completed_at


def test_sqlite_foreign_keys_enabled(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'fk.db'}")
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
    from app.db.models import Base

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                Chapter.__table__.insert().values(
                    book_id=999, chapter_index=1, title="x", word_count=0
                )
            )


def test_prompt_injection_fixture_cannot_change_pipeline(client: TestClient) -> None:
    content = open(
        "data/fixtures/local_model_calibration/prompt_injection_text.txt", encoding="utf-8"
    ).read()
    imported = client.post(
        "/api/v1/books/import",
        files={"file": ("prompt_injection_text.txt", content.encode(), "text/plain")},
    )
    book_id = imported.json()["book_id"]
    confirm_book_profile(client, book_id)
    chapter_id = client.get(f"/api/v1/books/{book_id}/chapters").json()[0]["id"]
    created = client.post(
        f"/api/v1/chapters/{chapter_id}/analysis-runs", json={"provider_name": "fake"}
    )
    run = client.get(f"/api/v1/analysis-runs/{created.json()['run_id']}").json()
    assert run["status"] == "succeeded"
