"""v4.0 的模型提议是一个独立状态，不是用户草稿 (CHG-20260815-099).

v3.5 published its model revision *after* the scenes existed, so "confirmed" was an honest
description of it. v4.0 stops at the review gate on purpose — the cuts are a proposal — and
the first attempt marked that revision ``draft``. Two things then went wrong on screen:
the header read 「AI 场景数：0 · 新增 6」, crediting the reader with six scenes the model had
found, and the fork behind 「调整场景边界」 looked past the proposal for a confirmed revision
that did not exist.

``proposed`` is the state that says "the AI has answered, nobody has decided". The three
places that have to recognise it are pinned below.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import Paragraph
from app.services.scene_boundary_manual_review import (
    confirm_scene_revision_v1,
    create_or_get_scene_boundary_draft_v1,
    ensure_model_revision_from_boundaries_v1,
    get_scene_boundaries_overview_v1,
)
from tests.test_chg041_scene_boundary_manual_review import _seed_chapter


def _propose(session, chapter, run, *, cut_indexes):
    paragraph_ids = list(
        session.scalars(
            select(Paragraph.id)
            .where(Paragraph.chapter_id == chapter.id)
            .order_by(Paragraph.paragraph_index)
        )
    )
    revision = ensure_model_revision_from_boundaries_v1(
        session,
        run,
        boundary_paragraph_ids=[paragraph_ids[i] for i in cut_indexes],
    )
    session.commit()
    return revision


def test_proposal_is_published_as_the_ai_baseline(testing_session):
    _, chapter, _, run, _ = _seed_chapter(testing_session)
    revision = _propose(testing_session, chapter, run, cut_indexes=[4, 9, 14])

    assert revision is not None
    assert revision.source == "model"
    # Not "draft": a draft means a human is mid-edit, and nobody has touched this.
    assert revision.status == "proposed"

    overview = get_scene_boundaries_overview_v1(testing_session, chapter.id)
    assert overview["model_revision"] is not None
    assert len(overview["model_revision"]["scenes"]) == 4  # three cuts → four scenes
    # The reader has made no edits, so there is no draft — which is what the header used to
    # get wrong, reporting the AI's six scenes as six the reader had added.
    assert overview["draft_revision"] is None


def test_editing_before_the_first_confirm_forks_from_the_proposal(testing_session):
    """「调整场景边界」 pressed before 「确认」 must start from the AI's cuts.

    Without the fallback the fork looked for a confirmed revision, found none, and fell
    through to the legacy single-scene partition — silently discarding the segmentation the
    reader was there to adjust.
    """
    _, chapter, _, run, _ = _seed_chapter(testing_session)
    proposal = _propose(testing_session, chapter, run, cut_indexes=[4, 9, 14])

    draft = create_or_get_scene_boundary_draft_v1(testing_session, chapter.id)
    testing_session.commit()

    assert draft.id != proposal.id
    assert draft.status == "draft"
    assert draft.source == "user"
    assert draft.based_on_revision_id == proposal.id
    assert draft.boundary_hash == proposal.boundary_hash  # same cuts, not a fresh guess


def test_adopting_the_proposal_unchanged_needs_no_draft(testing_session):
    """Confirming the AI's own answer is the ordinary path and must not require a fork."""
    _, chapter, _, run, _ = _seed_chapter(testing_session)
    proposal = _propose(testing_session, chapter, run, cut_indexes=[4, 9, 14])

    confirmed, already = confirm_scene_revision_v1(
        testing_session, proposal.id, expected_etag=proposal.revision_etag
    )
    testing_session.commit()

    assert already is False
    assert confirmed.id == proposal.id
    assert confirmed.status == "confirmed"
    overview = get_scene_boundaries_overview_v1(testing_session, chapter.id)
    assert overview["awaiting_confirmation"] is False
    assert len(overview["confirmed_revision"]["scenes"]) == 4


def test_a_stale_etag_still_loses(testing_session):
    # Accepting "proposed" must not weaken the concurrency check the draft path has.
    _, chapter, _, run, _ = _seed_chapter(testing_session)
    proposal = _propose(testing_session, chapter, run, cut_indexes=[4, 9])
    with pytest.raises(Exception):
        confirm_scene_revision_v1(testing_session, proposal.id, expected_etag="not-the-etag")
