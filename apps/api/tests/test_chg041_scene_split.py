"""CHG-041 Round 5: split_scene_at_paragraph_v1 contract tests."""

from __future__ import annotations

import json

import pytest

from app.services.scene_boundary_manual_review import (
    SceneBoundaryError,
    create_or_get_scene_boundary_draft_v1,
    ensure_ai_model_revision_after_scenes_v1,
    save_scene_boundary_draft_v1,
    split_scene_at_paragraph_v1,
    validate_scene_partition_v1,
)
from app.services.scene_boundary_partition_ops import add_boundary, delete_boundary
from tests.test_chg041_scene_boundary_manual_review import _seed_chapter


def _paragraph_ids(paragraphs):
    return [p.id for p in paragraphs]


def test_split_six_paragraph_scene_at_3_4(testing_session):
    _, chapter, paragraphs, run, _ = _seed_chapter(testing_session, paragraph_count=6, scene_count=1)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    pids = _paragraph_ids(paragraphs)
    before_etag = draft.revision_etag
    before_hash = draft.boundary_hash
    result = split_scene_at_paragraph_v1(
        testing_session,
        chapter.id,
        draft.id,
        boundary_after_paragraph_id=pids[2],
        expected_etag=before_etag,
        client_request_id="split-6-3-4",
        scene_order=1,
    )
    testing_session.commit()
    scenes = result["scenes"]
    assert len(scenes) == 2
    assert scenes[0]["start_paragraph_id"] == pids[0]
    assert scenes[0]["end_paragraph_id"] == pids[2]
    assert scenes[1]["start_paragraph_id"] == pids[3]
    assert scenes[1]["end_paragraph_id"] == pids[5]
    assert [s["scene_order"] for s in scenes] == [1, 2]
    assert result["revision_etag"] != before_etag
    assert result["boundary_hash"] != before_hash
    validate_scene_partition_v1(testing_session, chapter.id, scenes)


def test_single_paragraph_scene_cannot_split():
    with pytest.raises(ValueError, match="SCENE_SPLIT_INVALID_POSITION"):
        add_boundary(
            [
                {
                    "scene_order": 1,
                    "start_paragraph_id": "P1",
                    "end_paragraph_id": "P1",
                    "included_in_journey": True,
                }
            ],
            after_paragraph_id="P1",
            paragraph_ids=["P1"],
        )


def test_cannot_split_after_last_paragraph(testing_session):
    _, chapter, paragraphs, run, _ = _seed_chapter(testing_session, paragraph_count=6, scene_count=1)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    pids = _paragraph_ids(paragraphs)
    with pytest.raises(SceneBoundaryError) as exc:
        split_scene_at_paragraph_v1(
            testing_session,
            chapter.id,
            draft.id,
            boundary_after_paragraph_id=pids[-1],
            expected_etag=draft.revision_etag,
        )
    assert exc.value.error_code == "SCENE_SPLIT_INVALID_POSITION"


def test_existing_boundary_is_idempotent_already_split(testing_session):
    _, chapter, paragraphs, run, _ = _seed_chapter(testing_session, paragraph_count=10, scene_count=2)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    end_first = json.loads(draft.final_boundaries_json)["scenes"][0]["end_paragraph_id"]
    result = split_scene_at_paragraph_v1(
        testing_session,
        chapter.id,
        draft.id,
        boundary_after_paragraph_id=end_first,
        expected_etag=draft.revision_etag,
        client_request_id="already-boundary",
    )
    assert result["already_split"] is True
    assert len(result["scenes"]) == 2


def test_duplicate_client_request_id_does_not_double_split(testing_session):
    _, chapter, paragraphs, run, _ = _seed_chapter(testing_session, paragraph_count=8, scene_count=1)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    pids = _paragraph_ids(paragraphs)
    first = split_scene_at_paragraph_v1(
        testing_session,
        chapter.id,
        draft.id,
        boundary_after_paragraph_id=pids[3],
        expected_etag=draft.revision_etag,
        client_request_id="idem-1",
    )
    testing_session.commit()
    second = split_scene_at_paragraph_v1(
        testing_session,
        chapter.id,
        draft.id,
        boundary_after_paragraph_id=pids[3],
        expected_etag="stale-ignored-for-idem",
        client_request_id="idem-1",
    )
    assert first["revision_etag"] == second["revision_etag"]
    assert len(second["scenes"]) == 2


def test_included_inherited_and_merge_roundtrip(testing_session):
    _, chapter, paragraphs, run, _ = _seed_chapter(testing_session, paragraph_count=10, scene_count=2)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    pids = _paragraph_ids(paragraphs)
    scenes = json.loads(draft.final_boundaries_json)["scenes"]
    scenes[0]["included_in_journey"] = False
    scenes[1]["included_in_journey"] = True
    saved = save_scene_boundary_draft_v1(
        testing_session, draft.id, scenes, expected_etag=draft.revision_etag
    )
    testing_session.commit()
    result = split_scene_at_paragraph_v1(
        testing_session,
        chapter.id,
        draft.id,
        boundary_after_paragraph_id=pids[2],
        expected_etag=saved.revision_etag,
        client_request_id="inc-false",
        scene_order=1,
    )
    testing_session.commit()
    assert result["scenes"][0]["included_in_journey"] is False
    assert result["scenes"][1]["included_in_journey"] is False
    assert result["scenes"][2]["included_in_journey"] is True
    merged = delete_boundary(result["scenes"], boundary_index=0, paragraph_ids=pids)
    assert len(merged) == 2
    assert merged[0]["included_in_journey"] is False
    assert merged[0]["start_paragraph_id"] == pids[0]
    assert merged[0]["end_paragraph_id"] == pids[4]


def test_confirmed_and_ai_revision_cannot_split_in_place(testing_session):
    _, chapter, paragraphs, run, _ = _seed_chapter(testing_session, paragraph_count=6, scene_count=1)
    model = ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    pids = _paragraph_ids(paragraphs)
    with pytest.raises(SceneBoundaryError) as exc:
        split_scene_at_paragraph_v1(
            testing_session,
            chapter.id,
            model.id,
            boundary_after_paragraph_id=pids[2],
            expected_etag=model.revision_etag,
        )
    assert exc.value.error_code == "SCENE_REVISION_NOT_DRAFT"


def test_gap_overlap_coverage_after_split(testing_session):
    _, chapter, paragraphs, run, _ = _seed_chapter(testing_session)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    pids = _paragraph_ids(paragraphs)
    result = split_scene_at_paragraph_v1(
        testing_session,
        chapter.id,
        draft.id,
        boundary_after_paragraph_id=pids[1],
        expected_etag=draft.revision_etag,
        client_request_id="cov-1",
    )
    testing_session.commit()
    scenes = result["scenes"]
    assert len(scenes) == 5
    validate_scene_partition_v1(testing_session, chapter.id, scenes)
    covered = []
    for scene in scenes:
        start = next(p for p in paragraphs if p.id == scene["start_paragraph_id"])
        end = next(p for p in paragraphs if p.id == scene["end_paragraph_id"])
        covered.extend(range(start.paragraph_index, end.paragraph_index + 1))
    assert covered == list(range(1, 21))
    assert [s["scene_order"] for s in scenes] == [1, 2, 3, 4, 5]


def test_add_boundary_rejects_duplicate_boundary():
    scenes = [
        {
            "scene_order": 1,
            "start_paragraph_id": "P1",
            "end_paragraph_id": "P3",
            "included_in_journey": True,
        },
        {
            "scene_order": 2,
            "start_paragraph_id": "P4",
            "end_paragraph_id": "P6",
            "included_in_journey": True,
        },
    ]
    with pytest.raises(ValueError, match="SCENE_BOUNDARY_ALREADY_EXISTS"):
        add_boundary(
            scenes,
            after_paragraph_id="P3",
            paragraph_ids=["P1", "P2", "P3", "P4", "P5", "P6"],
        )
