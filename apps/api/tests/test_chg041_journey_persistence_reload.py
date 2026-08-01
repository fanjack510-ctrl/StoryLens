"""CHG-041 Round 6: Journey result persists and reloads by explicit run id."""

from __future__ import annotations

import asyncio
import hashlib
import json

from sqlalchemy.orm import sessionmaker

from app.api.v1.reader_journey import _serialize_result
from app.db.models import (
    AnalysisArtifact,
    ReaderJourneyRun,
    SceneReaderJourneyProfile,
)
from app.model_gateway.registry import get_model_gateway
from app.services.reader_journey_pipeline import execute_reader_journey
from app.services.reader_journey_v2_execution import _load_v2_profiles_from_artifacts
from app.services.scene_boundary_manual_review import (
    confirm_scene_revision_and_start_journey_v1,
    create_or_get_scene_boundary_draft_v1,
    ensure_ai_model_revision_after_scenes_v1,
)
from tests.test_chg041_scene_boundary_manual_review import (
    _attach_scene_analysis,
    _seed_chapter,
)


def _digest(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _session_factory(testing_session):
    factory = testing_session.get_bind()
    return sessionmaker(bind=factory, autoflush=False, autocommit=False, expire_on_commit=False)


def _enable_fake(monkeypatch, tmp_path) -> None:
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


def _start_and_execute(testing_session, monkeypatch, tmp_path):
    _enable_fake(monkeypatch, tmp_path)
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
    journey_id = int(journey.id)
    Session = _session_factory(testing_session)
    asyncio.run(execute_reader_journey(Session, get_model_gateway(), journey_id))
    refreshed = testing_session.get(ReaderJourneyRun, journey_id)
    testing_session.refresh(refreshed)
    return Session, refreshed, run, chapter


def test_explicit_run_persists_and_reloads_after_new_session(
    testing_session, monkeypatch, tmp_path
):
    Session, journey, _run, _chapter = _start_and_execute(
        testing_session, monkeypatch, tmp_path
    )
    assert journey.status == "succeeded"
    journey_id = int(journey.id)

    with Session() as first_session:
        first = _serialize_result(first_session, first_session.get(ReaderJourneyRun, journey_id))
    assert first.visualization is not None
    assert first.is_current is True
    assert first.is_superseded is False
    assert first.scene_boundary_hash
    first_hash = _digest(
        {
            "profiles": [p.model_dump() for p in first.scene_profiles],
            "visualization": first.visualization,
            "chapter_summary": first.chapter_summary,
        }
    )

    with Session() as second_session:
        second = _serialize_result(
            second_session, second_session.get(ReaderJourneyRun, journey_id)
        )
    second_hash = _digest(
        {
            "profiles": [p.model_dump() for p in second.scene_profiles],
            "visualization": second.visualization,
            "chapter_summary": second.chapter_summary,
        }
    )
    assert second.visualization is not None
    assert second_hash == first_hash
    assert len(second.scene_profiles) == int(journey.total_scene_count or 0)


def test_v2_stub_loader_ignores_prior_journey_artifacts(
    testing_session, monkeypatch, tmp_path
):
    Session, journey, run, _chapter = _start_and_execute(
        testing_session, monkeypatch, tmp_path
    )
    journey_id = int(journey.id)
    included = json.loads(journey.included_scene_ids_json or "[]")
    assert included

    # Plant a stale artifact for a non-included scene id on the same analysis run.
    stale_scene_id = max(int(x) for x in included) + 99
    testing_session.add(
        AnalysisArtifact(
            run_id=run.id,
            artifact_type="reader_journey_scene_profile_v2",
            subject_type="scene",
            subject_id=str(stale_scene_id),
            schema_version="2.0",
            prompt_version="2.0",
            payload_json=json.dumps(
                {
                    "scene_id": stale_scene_id,
                    "scene_ordinal": 99,
                    "scene_value_summary": "stale",
                    "confidence": 0.5,
                    "evidence_paragraph_ids": [],
                },
                ensure_ascii=False,
            ),
            confidence=0.5,
            validation_status="valid",
        )
    )
    testing_session.commit()

    from sqlalchemy import select

    with Session() as session:
        loaded = _load_v2_profiles_from_artifacts(session, session.get(ReaderJourneyRun, journey_id))
    assert all(int(item.scene_id) in {int(x) for x in included} for item in loaded)
    assert all(int(item.scene_id) != stale_scene_id for item in loaded)

    profiles = list(
        testing_session.scalars(
            select(SceneReaderJourneyProfile).where(
                SceneReaderJourneyProfile.reader_journey_run_id == journey_id
            )
        )
    )
    assert {int(p.scene_id) for p in profiles} == {int(x) for x in included}


def test_superseded_run_still_serializes_visualization(
    testing_session, monkeypatch, tmp_path
):
    Session, journey, _run, _chapter = _start_and_execute(
        testing_session, monkeypatch, tmp_path
    )
    journey.result_status = "superseded"
    testing_session.commit()
    journey_id = int(journey.id)

    with Session() as session:
        payload = _serialize_result(session, session.get(ReaderJourneyRun, journey_id))
    assert payload.visualization is not None
    assert payload.is_superseded is True
    assert payload.is_current is False
    assert payload.result_status == "superseded"
