"""Local tests for confirm-only final boundary proposals."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.db.models import (
    AnalysisRun,
    Book,
    BoundaryReviewDecision,
    BoundaryReviewSession,
    BoundaryRevision,
    Chapter,
    Paragraph,
    Scene,
)
from app.services.boundary_review_service import (
    confirm_review_from_final_proposal,
    create_review_session,
)
from app.services.final_boundary_proposal import (
    apply_final_proposal_decisions,
    build_final_boundary_proposal,
)


def _seed_chapter(session, paragraph_count: int = 6):
    book = Book(title="提案测试", source_file_name="p.txt", source_file_hash="a" * 64)
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id, chapter_index=1, title="第一章", section_type="chapter"
    )
    session.add(chapter)
    session.flush()
    paragraphs = []
    for index in range(1, paragraph_count + 1):
        p = Paragraph(
            id=f"B0001-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=f"这是用于场景划分测试的较长正文段落内容{index}。" * 8,
            normalized_text=f"这是用于场景划分测试的较长正文段落内容{index}。" * 8,
            char_start=index * 10,
            char_end=index * 10 + 4,
        )
        session.add(p)
        paragraphs.append(p)
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        input_hash="b" * 64,
        status="awaiting_boundary_review",
        execution_mode="local",
    )
    session.add(run)
    session.flush()
    review = BoundaryReviewSession(
        book_id=book.id,
        chapter_id=chapter.id,
        analysis_run_id=run.id,
        prompt_version="v1",
        provider="fake",
        model="fake",
        status="pending",
        candidate_count=0,
    )
    session.add(review)
    session.flush()
    return book, chapter, paragraphs, run, review


def _add_decision(session, review, paragraphs, *, left_index: int, **kwargs):
    left = paragraphs[left_index]
    right = paragraphs[left_index + 1]
    defaults = dict(
        review_session_id=review.id,
        transition_id=f"T{left_index+1:04d}",
        left_paragraph_id=left.id,
        right_paragraph_id=right.id,
        model_candidate=True,
        model_boundary_candidate=True,
        model_confidence=0.8,
        model_reason_code="goal",
        deterministic_reason="goal",
        deterministic_legal=True,
        first_pass_json="{}",
        review_priority="medium",
        user_decision="pending",
        final_boundary=False,
        semantic_conflict=False,
    )
    defaults.update(kwargs)
    row = BoundaryReviewDecision(**defaults)
    session.add(row)
    session.flush()
    return row


def test_dedupe_and_merge_same_left(testing_session):
    _, _, paragraphs, run, review = _seed_chapter(testing_session)
    _add_decision(testing_session, review, paragraphs, left_index=1, transition_id="T1")
    _add_decision(
        testing_session,
        review,
        paragraphs,
        left_index=1,
        transition_id="T1b",
        model_confidence=0.5,
    )
    _add_decision(testing_session, review, paragraphs, left_index=3, transition_id="T3")
    testing_session.commit()

    proposal = build_final_boundary_proposal(testing_session, review)
    assert proposal.validation_status == "valid"
    assert proposal.final_boundary_left_ids == [paragraphs[1].id, paragraphs[3].id]
    assert proposal.scene_count == 3


def test_rejected_gap_excluded_accepted_included(testing_session):
    _, _, paragraphs, run, review = _seed_chapter(testing_session)
    _add_decision(
        testing_session,
        review,
        paragraphs,
        left_index=1,
        user_decision="reject",
    )
    _add_decision(
        testing_session,
        review,
        paragraphs,
        left_index=3,
        user_decision="accept",
    )
    testing_session.commit()
    proposal = build_final_boundary_proposal(testing_session, review)
    assert paragraphs[1].id not in proposal.final_boundary_left_ids
    assert paragraphs[3].id in proposal.final_boundary_left_ids
    assert proposal.validation_status == "valid"


def test_conflict_without_legal_reason_excluded(testing_session):
    _, _, paragraphs, run, review = _seed_chapter(testing_session)
    _add_decision(
        testing_session,
        review,
        paragraphs,
        left_index=2,
        semantic_conflict=True,
        deterministic_legal=False,
        deterministic_reason=None,
        model_boundary_candidate=True,
    )
    _add_decision(testing_session, review, paragraphs, left_index=4)
    testing_session.commit()
    proposal = build_final_boundary_proposal(testing_session, review)
    assert paragraphs[2].id not in proposal.final_boundary_left_ids
    assert proposal.validation_status == "valid"


def test_last_paragraph_boundary_rejected(testing_session):
    _, _, paragraphs, run, review = _seed_chapter(testing_session)
    _add_decision(testing_session, review, paragraphs, left_index=1)
    # Boundary after last paragraph is illegal (no right neighbor for a cut).
    last = paragraphs[-1]
    testing_session.add(
        BoundaryReviewDecision(
            review_session_id=review.id,
            transition_id="LAST",
            left_paragraph_id=last.id,
            right_paragraph_id=last.id,
            model_candidate=True,
            model_boundary_candidate=True,
            model_confidence=0.9,
            first_pass_json="{}",
            review_priority="high",
            user_decision="pending",
            deterministic_legal=True,
            model_reason_code="goal",
            deterministic_reason="goal",
        )
    )
    testing_session.commit()
    proposal = build_final_boundary_proposal(testing_session, review)
    assert last.id not in proposal.final_boundary_left_ids
    assert proposal.validation_status == "valid"


def test_pending_does_not_block_confirm_idempotent(testing_session):
    _, _, paragraphs, run, review = _seed_chapter(testing_session)
    _add_decision(testing_session, review, paragraphs, left_index=2, user_decision="pending")
    testing_session.commit()
    proposal = build_final_boundary_proposal(testing_session, review)
    assert proposal.validation_status == "valid"

    revision, scenes, replay = confirm_review_from_final_proposal(
        testing_session,
        review,
        confirmed_by="tester",
        proposal_fingerprint=proposal.proposal_fingerprint,
    )
    assert replay is False
    assert review.status == "confirmed"
    assert run.status == "boundary_confirmed"
    assert len(scenes) == proposal.scene_count

    revision2, scenes2, replay2 = confirm_review_from_final_proposal(
        testing_session,
        review,
        confirmed_by="tester",
        proposal_fingerprint=proposal.proposal_fingerprint,
    )
    assert replay2 is True
    assert revision2.id == revision.id
    assert len(scenes2) == len(scenes)

    # 确认会把候选决定固化，确认后重新读取 proposal 得到的指纹可能不同。页面刷新后再次
    # 点击确认也必须回放既有修订，不能把一次已经成功的操作显示成
    # ``review is not confirmable``。
    refreshed = build_final_boundary_proposal(testing_session, review)
    revision3, scenes3, replay3 = confirm_review_from_final_proposal(
        testing_session,
        review,
        confirmed_by="tester",
        proposal_fingerprint=refreshed.proposal_fingerprint,
    )
    assert replay3 is True
    assert revision3.id == revision.id
    assert len(scenes3) == len(scenes)
    all_scenes = list(
        testing_session.scalars(select(Scene).where(Scene.boundary_revision_id == revision.id))
    )
    assert len(all_scenes) == len(scenes)


def test_fingerprint_mismatch_rejected(testing_session):
    _, _, paragraphs, run, review = _seed_chapter(testing_session)
    _add_decision(testing_session, review, paragraphs, left_index=1)
    testing_session.commit()
    with pytest.raises(ValueError, match="fingerprint"):
        confirm_review_from_final_proposal(
            testing_session,
            review,
            confirmed_by="tester",
            proposal_fingerprint="deadbeef" * 4,
        )
