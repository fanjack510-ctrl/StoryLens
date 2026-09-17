"""Regression coverage for scene-boundary review scoped to one AnalysisRun."""

from __future__ import annotations

from fastapi import HTTPException

from app.api.v1.scene_boundaries import save_scene_boundary_draft
from app.db.models import AnalysisRun
from app.schemas.scene_boundaries import SceneBoundaryDraftSaveRequest, ScenePartitionItem
from app.services.scene_boundary_manual_review import (
    confirm_scene_revision_v1,
    create_or_get_scene_boundary_draft_v1,
    ensure_model_revision_from_boundaries_v1,
    get_scene_boundaries_overview_v1,
)
from tests.test_chg041_scene_boundary_manual_review import _seed_chapter


def _new_run_for_same_chapter(session, chapter, *, client_request_id: str) -> AnalysisRun:
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="fake",
        model="fake",
        prompt_version="v4.0",
        schema_version="v1",
        input_hash=(client_request_id[0] * 64),
        status="awaiting_boundary_review",
        execution_mode="local",
        cloud_consent=False,
        sends_content_to_cloud=False,
        client_request_id=client_request_id,
    )
    session.add(run)
    session.flush()
    return run


def test_new_run_review_never_reuses_the_same_chapters_old_confirmed_revision(
    testing_session,
):
    _, chapter, paragraphs, old_run, _ = _seed_chapter(testing_session)
    old_proposal = ensure_model_revision_from_boundaries_v1(
        testing_session,
        old_run,
        boundary_paragraph_ids=[paragraphs[4].id, paragraphs[9].id],
    )
    old_confirmed, _ = confirm_scene_revision_v1(
        testing_session,
        old_proposal.id,
        expected_etag=old_proposal.revision_etag,
    )

    new_run = _new_run_for_same_chapter(
        testing_session,
        chapter,
        client_request_id="new-run-boundary-scope",
    )
    new_proposal = ensure_model_revision_from_boundaries_v1(
        testing_session,
        new_run,
        boundary_paragraph_ids=[paragraphs[2].id, paragraphs[7].id, paragraphs[14].id],
    )
    testing_session.commit()

    overview = get_scene_boundaries_overview_v1(
        testing_session,
        chapter.id,
        analysis_run_id=new_run.id,
    )
    assert overview["confirmed_revision"] is None
    assert overview["draft_revision"] is None
    assert overview["model_revision"]["revision_id"] == new_proposal.id
    assert overview["awaiting_confirmation"] is True

    draft = create_or_get_scene_boundary_draft_v1(
        testing_session,
        chapter.id,
        analysis_run_id=new_run.id,
    )
    assert draft.analysis_run_id == new_run.id
    assert draft.based_on_revision_id == new_proposal.id

    new_confirmed, already_confirmed = confirm_scene_revision_v1(
        testing_session,
        draft.id,
        expected_etag=draft.revision_etag,
    )
    testing_session.commit()

    assert already_confirmed is False
    assert new_confirmed.analysis_run_id == new_run.id
    assert old_confirmed.status == "confirmed"
    assert old_confirmed.analysis_run_id == old_run.id


def test_mutation_api_fails_closed_when_revision_and_run_do_not_match(testing_session):
    _, chapter, paragraphs, old_run, _ = _seed_chapter(testing_session)
    old_proposal = ensure_model_revision_from_boundaries_v1(
        testing_session,
        old_run,
        boundary_paragraph_ids=[paragraphs[4].id, paragraphs[9].id],
    )
    new_run = _new_run_for_same_chapter(
        testing_session,
        chapter,
        client_request_id="mismatched-run-scope",
    )
    testing_session.commit()

    scenes = [
        ScenePartitionItem(**item)
        for item in get_scene_boundaries_overview_v1(
            testing_session,
            chapter.id,
            analysis_run_id=old_run.id,
        )["model_revision"]["scenes"]
    ]
    body = SceneBoundaryDraftSaveRequest(
        expected_etag=old_proposal.revision_etag,
        scenes=scenes,
    )

    try:
        save_scene_boundary_draft(
            chapter.id,
            old_proposal.id,
            body,
            analysis_run_id=new_run.id,
            session=testing_session,
        )
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail["error_code"] == "SCENE_REVISION_NOT_FOUND"
    else:
        raise AssertionError("mismatched AnalysisRun unexpectedly changed a boundary revision")
