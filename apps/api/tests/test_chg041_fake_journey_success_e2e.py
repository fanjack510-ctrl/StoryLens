"""CHG-041 Round 4: Fake Journey end-to-end success under Manual Gate fixture."""

from __future__ import annotations

import asyncio
import os

from app.db.models import ReaderJourneyRun
from app.model_gateway.registry import get_model_gateway
from app.services.chapter_analysis_smoke_fake_transport import (
    validate_manual_gate_journey_fixture_v1,
)
from app.services.reader_journey_pipeline import execute_reader_journey
from app.services.scene_boundary_manual_review import (
    confirm_scene_revision_and_start_journey_v1,
    create_or_get_scene_boundary_draft_v1,
    ensure_ai_model_revision_after_scenes_v1,
)
from tests.test_chg041_scene_boundary_manual_review import (
    _attach_scene_analysis,
    _seed_chapter,
)


def test_validate_then_confirm_start_journey_succeeds(testing_session, monkeypatch, tmp_path):
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE", "1")
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL", "0")
    monkeypatch.setenv("STORYLENS_JOURNEY_FAKE_MODE", "success")
    monkeypatch.setenv("STORYLENS_APP_ENV", "development")
    monkeypatch.setenv("STORYLENS_REAL_PROVIDER_ENABLED", "0")
    monkeypatch.setenv("STORYLENS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "STORYLENS_DATABASE_URL",
        "sqlite:///" + (tmp_path / "unused.db").as_posix(),
    )
    from app.core import config as config_mod

    config_mod.get_settings.cache_clear()

    validate_manual_gate_journey_fixture_v1()
    _, chapter, _, run, scenes = _seed_chapter(testing_session)
    run.provider = "aliyun_qwen_plus"
    run.model = "qwen-plus"
    testing_session.flush()
    _attach_scene_analysis(testing_session, run, scenes)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    _revision, journey, _, err = asyncio.run(
        confirm_scene_revision_and_start_journey_v1(
            testing_session,
            draft.id,
            expected_etag=draft.revision_etag,
            start_journey=True,
            session_factory=None,
            gateway=None,
        )
    )
    assert err is None
    assert journey is not None
    journey_id = journey.id
    assert journey.status == "queued"

    # Bind execute to the same in-memory testing session factory.
    factory = testing_session.get_bind()
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=factory, autoflush=False, autocommit=False, expire_on_commit=False)
    gateway = get_model_gateway()
    asyncio.run(execute_reader_journey(Session, gateway, journey_id))

    refreshed = testing_session.get(ReaderJourneyRun, journey_id)
    testing_session.refresh(refreshed)
    assert refreshed is not None
    assert refreshed.status == "succeeded", (
        refreshed.root_error_code,
        refreshed.root_error_message,
    )
    assert refreshed.completed_scene_count == 4
    assert refreshed.total_scene_count == 4

    # Simulate first render and a process/session restart: both responses must be
    # reconstructed exclusively from committed rows, with no regeneration.
    from app.api.v1.reader_journey import _serialize_result

    with Session() as first_session:
        first = _serialize_result(
            first_session, first_session.get(ReaderJourneyRun, journey_id)
        )
    with Session() as refresh_session:
        after_refresh = _serialize_result(
            refresh_session, refresh_session.get(ReaderJourneyRun, journey_id)
        )
    assert first.visualization is not None
    assert after_refresh.visualization == first.visualization
    assert after_refresh.journey_run_id == journey_id
