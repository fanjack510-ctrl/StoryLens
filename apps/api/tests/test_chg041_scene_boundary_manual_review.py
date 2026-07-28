"""CHG-041 manual scene boundary review tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
from unittest.mock import MagicMock, patch

from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, inspect, select
import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    Book,
    BoundaryRevision,
    Chapter,
    Paragraph,
    Scene,
)
from app.db.session import migrate_phase_scene_boundary_manual_review
from app.services import chapter_analysis_completion as cac
from app.services.scene_boundary_manual_review import (
    SceneBoundaryError,
    compute_chapter_text_hash_v1,
    compute_diff_summary_v1,
    compute_scene_boundary_hash_v1,
    compute_scene_journey_input_hash_v1,
    confirm_scene_revision_v1,
    create_or_get_scene_boundary_draft_v1,
    discard_scene_boundary_draft_v1,
    ensure_ai_model_revision_after_scenes_v1,
    ensure_legacy_confirmed_revision_v1,
    get_scene_boundaries_overview_v1,
    move_boundary,
    plan_scene_reuse,
    restore_ai_partition_into_draft_v1,
    revision_scenes,
    save_scene_boundary_draft_v1,
    set_included,
    validate_scene_partition_v1,
)


def _seed_chapter(session, *, paragraph_count: int = 20, scene_count: int = 4):
    book = Book(title="CHG041", source_file_name="t.txt", source_file_hash="a" * 64)
    session.add(book)
    session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=1, title="第一章", section_type="chapter")
    session.add(chapter)
    session.flush()
    paragraphs: list[Paragraph] = []
    for index in range(1, paragraph_count + 1):
        paragraph = Paragraph(
            id=f"B0001-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=f"段落{index}内容。" * 3,
            normalized_text=f"段落{index}内容。" * 3,
            char_start=index * 10,
            char_end=index * 10 + 20,
        )
        session.add(paragraph)
        paragraphs.append(paragraph)
    session.flush()
    per_scene = paragraph_count // scene_count
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="fake",
        model="fake",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="b" * 64,
        status="succeeded",
        execution_mode="local",
        cloud_consent=False,
        sends_content_to_cloud=False,
    )
    session.add(run)
    session.flush()
    scenes: list[Scene] = []
    start_idx = 0
    for ordinal in range(1, scene_count + 1):
        end_idx = start_idx + per_scene - 1 if ordinal < scene_count else paragraph_count - 1
        start_p = paragraphs[start_idx]
        end_p = paragraphs[end_idx]
        content = "\n".join(p.normalized_text for p in paragraphs[start_idx : end_idx + 1])
        scene = Scene(
            scene_key=f"B0001-C0001-S{ordinal:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            ordinal=ordinal,
            start_paragraph_id=start_p.id,
            end_paragraph_id=end_p.id,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            created_by_run_id=run.id,
            boundary_detected=True,
            boundary_confidence=0.9,
            boundary_reason_json="[]",
            included_in_journey=True,
        )
        session.add(scene)
        scenes.append(scene)
        start_idx = end_idx + 1
    session.commit()
    return book, chapter, paragraphs, run, scenes


def _partition_from_scenes(scenes: list[Scene]) -> list[dict]:
    return [
        {
            "scene_order": scene.ordinal,
            "start_paragraph_id": scene.start_paragraph_id,
            "end_paragraph_id": scene.end_paragraph_id,
            "included_in_journey": True,
        }
        for scene in scenes
    ]


def _attach_scene_analysis(session, run: AnalysisRun, scenes: list[Scene]) -> None:
    for scene in scenes:
        artifact = AnalysisArtifact(
            run_id=run.id,
            artifact_type="scene_analysis",
            subject_type="scene",
            subject_id=str(scene.id),
            schema_version="v1",
            prompt_version="v1",
            payload_json='{"scene_id": "x"}',
            confidence=0.9,
            validation_status="valid",
        )
        session.add(artifact)
        session.flush()
        session.add(
            AnalysisEvidence(
                artifact_id=artifact.id,
                field_path="summary",
                paragraph_id=scene.start_paragraph_id,
                paragraph_hash="c" * 64,
            )
        )
    session.commit()


def test_compute_hashes_deterministic(testing_session):
    _, chapter, _, _, scenes = _seed_chapter(testing_session)
    partition = _partition_from_scenes(scenes)
    chapter_hash = compute_chapter_text_hash_v1(testing_session, chapter.id)
    h1 = compute_scene_boundary_hash_v1(chapter.id, chapter_hash, partition)
    h2 = compute_scene_boundary_hash_v1(chapter.id, chapter_hash, partition)
    assert h1 == h2
    journey_hash = compute_scene_journey_input_hash_v1(
        chapter_text_hash=chapter_hash,
        scene_text_hash=scenes[0].content_hash,
        included_in_journey=True,
        journey_prompt_version="v1",
        journey_contract_version="1.0",
        provider_id="fake",
        model_id="fake",
    )
    assert len(journey_hash) == 64


def test_validate_partition_errors(testing_session):
    _, chapter, paragraphs, _, scenes = _seed_chapter(testing_session)
    partition = _partition_from_scenes(scenes)
    validate_scene_partition_v1(testing_session, chapter.id, partition)
    with pytest.raises(SceneBoundaryError) as exc:
        validate_scene_partition_v1(testing_session, chapter.id, [])
    assert exc.value.error_code == "SCENE_PARTITION_EMPTY"
    bad = [dict(partition[0])]
    bad[0]["end_paragraph_id"] = paragraphs[-1].id
    bad.append(
        {
            "scene_order": 2,
            "start_paragraph_id": paragraphs[5].id,
            "end_paragraph_id": paragraphs[-1].id,
            "included_in_journey": True,
        }
    )
    with pytest.raises(SceneBoundaryError) as exc2:
        validate_scene_partition_v1(testing_session, chapter.id, bad)
    assert exc2.value.error_code == "SCENE_PARTITION_OVERLAP"


def test_ensure_ai_model_revision_links_scenes(testing_session):
    _, chapter, _, run, scenes = _seed_chapter(testing_session)
    revision = ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    assert revision is not None
    assert revision.source == "model"
    assert revision.status == "confirmed"
    linked = revision_scenes(testing_session, revision.id)
    assert len(linked) == len(scenes)
    assert all(scene.boundary_revision_id == revision.id for scene in linked)


def test_draft_save_etag_and_confirm_supersedes(testing_session):
    _, chapter, _, run, scenes = _seed_chapter(testing_session)
    model_rev = ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    partition = _partition_from_scenes(revision_scenes(testing_session, model_rev.id))
    paragraph_ids = list(
        testing_session.scalars(
            select(Paragraph.id)
            .where(Paragraph.chapter_id == chapter.id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    moved = move_boundary(
        partition,
        boundary_index=0,
        direction="right",
        paragraph_ids=paragraph_ids,
    )
    etag = draft.revision_etag
    saved = save_scene_boundary_draft_v1(
        testing_session, draft.id, moved, expected_etag=etag
    )
    testing_session.commit()
    with pytest.raises(SceneBoundaryError) as exc:
        save_scene_boundary_draft_v1(
            testing_session, draft.id, moved, expected_etag=etag
        )
    assert exc.value.error_code == "SCENE_REVISION_CONCURRENT_MODIFICATION"
    confirmed = confirm_scene_revision_v1(
        testing_session, saved.id, expected_etag=saved.revision_etag
    )
    testing_session.commit()
    assert confirmed.status == "confirmed"
    testing_session.refresh(model_rev)
    assert model_rev.status == "superseded"
    assert len(revision_scenes(testing_session, confirmed.id)) == 4


def test_restore_ai_and_discard_draft(testing_session):
    _, chapter, _, run, _ = _seed_chapter(testing_session)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    partition = json.loads(draft.final_boundaries_json)["scenes"]
    edited = set_included(partition, scene_order=1, included=False)
    save_scene_boundary_draft_v1(
        testing_session, draft.id, edited, expected_etag=draft.revision_etag
    )
    testing_session.commit()
    restored = restore_ai_partition_into_draft_v1(testing_session, draft.id)
    testing_session.commit()
    restored_scenes = json.loads(restored.final_boundaries_json)["scenes"]
    assert all(item.get("included_in_journey", True) for item in restored_scenes)
    discard_scene_boundary_draft_v1(testing_session, draft.id)
    testing_session.commit()
    assert testing_session.get(BoundaryRevision, draft.id) is None


def test_overview_and_diff(testing_session):
    _, chapter, _, run, _ = _seed_chapter(testing_session)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    overview = get_scene_boundaries_overview_v1(testing_session, chapter.id)
    assert overview["model_revision"] is not None
    assert overview["confirmed_revision"] is not None
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    diff = compute_diff_summary_v1(testing_session, draft.id)
    assert diff["scene_count_delta"] == 0


def test_legacy_revision_idempotent(testing_session):
    _, chapter, _, run, _ = _seed_chapter(testing_session)
    ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    first = ensure_legacy_confirmed_revision_v1(testing_session, chapter.id)
    second = ensure_legacy_confirmed_revision_v1(testing_session, chapter.id)
    assert first is not None
    assert second.id == first.id


def test_continue_chapter_gates_auto_journey(testing_session):
    _, chapter, _, run, scenes = _seed_chapter(testing_session)
    _attach_scene_analysis(testing_session, run, scenes)
    gateway = MagicMock()
    factory = sessionmaker(bind=testing_session.bind, autoflush=False, expire_on_commit=False)

    with patch.object(cac, "is_scene_pipeline_complete", return_value=True):
        with patch.object(cac, "is_chapter_analysis_complete", return_value=False):
            asyncio.run(cac.continue_chapter_after_scenes(factory, gateway, run.id))
    with factory() as session:
        stored = session.get(AnalysisRun, run.id)
        marker = json.loads(stored.raw_output or "{}")
    assert marker.get("chapter_pipeline") == "awaiting_scene_boundary_confirmation"
    assert cac.latest_journey(testing_session, run.id) is None


def test_journey_binding_and_reuse_plan(testing_session):
    _, chapter, _, run, scenes = _seed_chapter(testing_session)
    _attach_scene_analysis(testing_session, run, scenes)
    revision = ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    journey = cac.ensure_auto_reader_journey_row(
        testing_session, run, scene_revision_id=revision.id
    )
    testing_session.commit()
    assert journey is not None
    assert journey.scene_revision_id == revision.id
    assert journey.scene_boundary_hash == revision.boundary_hash
    bound_ids = json.loads(journey.included_scene_ids_json)
    assert len(bound_ids) == 4
    plan = plan_scene_reuse(
        testing_session, journey, revision_scenes(testing_session, revision.id)
    )
    assert len(plan) == 4


def test_migration_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migrate.db'}")
    from app.db.models import Base

    Base.metadata.create_all(engine)
    migrate_phase_scene_boundary_manual_review(engine)
    migrate_phase_scene_boundary_manual_review(engine)
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("boundary_revisions")}
    assert "status" in cols
    assert "boundary_hash" in cols
    journey_cols = {c["name"] for c in inspector.get_columns("reader_journey_runs")}
    assert "scene_revision_id" in journey_cols
    assert "result_status" in journey_cols


def test_fake_manual_edit_scenario_coverage(testing_session):
    """20 paragraphs / 4 scenes: move, add, delete divider, exclude, save, refresh, confirm."""
    from app.services.scene_boundary_partition_ops import add_boundary, delete_boundary

    _, chapter, paragraphs, run, scenes = _seed_chapter(testing_session)
    _attach_scene_analysis(testing_session, run, scenes)
    model_rev = ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    paragraph_ids = [p.id for p in paragraphs]
    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()
    partition = json.loads(draft.final_boundaries_json)["scenes"]
    # 1) move first boundary 5/6 -> 6/7
    partition = move_boundary(partition, boundary_index=0, direction="right", paragraph_ids=paragraph_ids)
    assert partition[0]["end_paragraph_id"] == paragraph_ids[5]
    assert partition[1]["start_paragraph_id"] == paragraph_ids[6]
    # 2) add boundary at 12/13 (after P12)
    partition = add_boundary(partition, after_paragraph_id=paragraph_ids[11], paragraph_ids=paragraph_ids)
    assert len(partition) == 5
    # 3) delete divider that was at 15/16 — after edits, find boundary ending at P15
    end15 = paragraph_ids[14]
    boundary_idx = next(i for i, s in enumerate(partition[:-1]) if s["end_paragraph_id"] == end15)
    partition = delete_boundary(partition, boundary_index=boundary_idx, paragraph_ids=paragraph_ids)
    # 4) exclude last scene
    last_order = max(int(s["scene_order"]) for s in partition)
    partition = set_included(partition, scene_order=last_order, included=False)
    # 5) save draft
    saved = save_scene_boundary_draft_v1(testing_session, draft.id, partition, expected_etag=draft.revision_etag)
    testing_session.commit()
    etag = saved.revision_etag
    # 6-7) refresh: reload draft
    testing_session.expire_all()
    reloaded = testing_session.get(BoundaryRevision, draft.id)
    assert reloaded is not None and reloaded.status == "draft"
    assert reloaded.revision_etag == etag
    restored_scenes = json.loads(reloaded.final_boundaries_json)["scenes"]
    validate_scene_partition_v1(testing_session, chapter.id, restored_scenes)
    # coverage checks
    covered = []
    for scene in restored_scenes:
        start = next(p for p in paragraphs if p.id == scene["start_paragraph_id"])
        end = next(p for p in paragraphs if p.id == scene["end_paragraph_id"])
        covered.extend(range(start.paragraph_index, end.paragraph_index + 1))
    assert covered == list(range(1, 21))
    # 8) confirm
    confirmed = confirm_scene_revision_v1(testing_session, reloaded.id, expected_etag=etag)
    testing_session.commit()
    testing_session.refresh(model_rev)
    assert model_rev.status == "superseded"
    assert confirmed.status == "confirmed"
    # 9) fake journey bind
    journey = cac.ensure_auto_reader_journey_row(
        testing_session, run, scene_revision_id=confirmed.id
    )
    testing_session.commit()
    assert journey.scene_revision_id == confirmed.id
    included = json.loads(journey.included_scene_ids_json)
    assert len(included) == len([s for s in restored_scenes if s.get("included_in_journey", True)])
    # excluded => not scheduled
    assert journey.total_scene_count == len(included)
    # old journey superseded marker path: create prior current then confirm again path already superseded model
    assert model_rev.status == "superseded"


def test_ai_revision_immutable_requires_draft(testing_session):
    _, chapter, _, run, _ = _seed_chapter(testing_session)
    model_rev = ensure_ai_model_revision_after_scenes_v1(testing_session, run)
    testing_session.commit()
    with pytest.raises(SceneBoundaryError):
        save_scene_boundary_draft_v1(
            testing_session,
            model_rev.id,
            json.loads(model_rev.final_boundaries_json)["scenes"],
            expected_etag=model_rev.revision_etag,
        )
