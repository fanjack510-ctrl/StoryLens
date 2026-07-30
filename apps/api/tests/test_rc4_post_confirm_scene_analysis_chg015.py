"""CHG-20260730-015: post-confirm rematerialize must not mark analyze complete early."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import AnalysisArtifact, AnalysisRun, ReaderJourneyRun
from app.services.chapter_analysis_completion import effective_chapter_status
from app.services.confirmed_revision_scene_analysis import (
    mark_awaiting_post_confirm_scene_analysis,
    revision_scene_analysis_complete,
)
from app.services.reader_journey_v2_execution import execute_reader_journey_v2
from app.services.scene_boundary_manual_review import (
    confirm_scene_revision_and_start_journey_v1,
    create_or_get_scene_boundary_draft_v1,
    revision_scenes,
    save_scene_boundary_draft_v1,
)
from tests.test_chg041_scene_boundary_manual_review import (
    _attach_scene_analysis,
    _seed_chapter,
)
from tests.test_phase_1c_c1 import _enable_cloud


def _shrink_draft(session, draft, paragraphs, scene_count: int):
    span = max(1, len(paragraphs) // scene_count)
    partition = []
    for i in range(scene_count):
        start = paragraphs[i * span]
        end = paragraphs[min((i + 1) * span - 1, len(paragraphs) - 1)]
        partition.append(
            {
                "scene_order": i + 1,
                "start_paragraph_id": start.id,
                "end_paragraph_id": end.id,
                "included_in_journey": True,
            }
        )
    return save_scene_boundary_draft_v1(
        session, draft.id, partition, expected_etag=draft.revision_etag
    )


@pytest.mark.asyncio
async def test_confirm_edited_partition_does_not_mark_scenes_complete(testing_session):
    _enable_cloud(testing_session)
    book, chapter, paragraphs, run, scenes = _seed_chapter(
        testing_session, paragraph_count=12, scene_count=2
    )
    _attach_scene_analysis(testing_session, run, scenes)
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    testing_session.refresh(draft)
    # Edit to 3 scenes → rematerialize with new content hashes (no artifact carry).
    draft = _shrink_draft(testing_session, draft, paragraphs, scene_count=3)
    testing_session.commit()
    testing_session.refresh(draft)

    revision, journey, _, err = await confirm_scene_revision_and_start_journey_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    assert err is None or err == "WAITING_SCENE_ANALYSIS" or journey is not None
    testing_session.refresh(run)
    assert run.status == "scene_analysis_running"
    assert not revision_scene_analysis_complete(testing_session, run.id, revision.id)
    rematerialized = revision_scenes(testing_session, revision.id)
    assert len(rematerialized) == 3
    assert journey is not None
    assert journey.status == "starting"
    assert journey.root_error_code == "WAITING_SCENE_ANALYSIS"
    assert effective_chapter_status(testing_session, run) == "scene_analysis"


@pytest.mark.asyncio
async def test_v2_incomplete_scenes_wait_not_fail(testing_session, monkeypatch):
    _enable_cloud(testing_session)
    book, chapter, paragraphs, run, scenes = _seed_chapter(
        testing_session, paragraph_count=12, scene_count=3
    )
    # Do NOT attach scene analysis artifacts.
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    testing_session.refresh(draft)
    draft = _shrink_draft(testing_session, draft, paragraphs, scene_count=3)
    testing_session.commit()
    testing_session.refresh(draft)
    revision, journey, _, _ = await confirm_scene_revision_and_start_journey_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
        start_journey=True,
    )
    assert journey is not None
    journey_id = journey.id
    testing_session.commit()

    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=testing_session.get_bind(), autoflush=False, expire_on_commit=False)

    class _GW:
        providers = []

    await execute_reader_journey_v2(factory, _GW(), journey_id)
    with factory() as session:
        row = session.get(ReaderJourneyRun, journey_id)
        assert row is not None
        assert row.status == "starting"
        assert row.root_error_code == "WAITING_SCENE_ANALYSIS"
        assert row.completed_at is None
        run2 = session.get(AnalysisRun, row.analysis_run_id)
        assert effective_chapter_status(session, run2) == "scene_analysis"
