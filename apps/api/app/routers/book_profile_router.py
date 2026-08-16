"""Book profile APIs — draft, confirm, reset (CHG-20260813-089).

The profile answers "what kind of book is this" **before** anything expensive reads it. It
sits ahead of both analysis pipelines rather than inside either one
(10_ADAPTIVE_PROFILE_LAYER §4.0), which is why it is addressed by book and not by run.

The draft endpoint does the free half only. Counting the whole text — chapter lengths,
dialogue ratio, where each name appears across the book — costs nothing and needs no
provider, so it always runs. The sampled model read that fills in audience and narrative
engine is a paid call and is supplied by the caller rather than triggered here; a GET that
silently spends money is not something a client should have to guess about.
"""

from __future__ import annotations

import logging

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.long_novel.contracts.profile import AXES
from app.narrative_core.long_novel.deltas import deltas_for
from app.narrative_core.long_novel.profile import (
    confirm as confirm_profile,
    merge_draft,
    presentation_options,
    select_sample_chapters,
)
from app.narrative_core.long_novel.profile_repository import BookProfileRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["book-profile"])


class ConfirmRequest(BaseModel):
    """The user's dropdown selections. Absent axes keep whatever was inferred."""

    axes: dict[str, str] = Field(default_factory=dict)


def _chapter_texts(db: Session, book_id: int) -> tuple[list[str], int]:
    """The book's chapters in reading order, from its most recent snapshot."""
    snapshot_id = db.execute(
        text(
            "SELECT id FROM book_snapshots WHERE book_id = :book_id "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"book_id": book_id},
    ).scalar()
    if snapshot_id is None:
        # The profile is a prerequisite for BOTH analysis entries now (§4.3), so its own
        # entry point must be self-sufficient. A chapter-only user has no snapshot yet —
        # historically only the whole-book prepare built one — and answering 409 here
        # would deadlock them: analysis needs the profile, the profile needs a snapshot,
        # the snapshot needs the whole-book flow they never use. Building it is free.
        from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl

        try:
            snapshot_id = BookSnapshotServiceImpl(db).create_or_reuse_snapshot(book_id).id
            db.commit()
        except Exception:  # noqa: BLE001 — no chapters, unreadable book, or a lost race
            logger.warning("profile_snapshot_autocreate_failed book_id=%s", book_id, exc_info=True)
            db.rollback()
            # React dev mode double-fires the draft request; two builders race and the
            # loser lands here with a unique-constraint error while the winner's snapshot
            # is already committed. Losing the race is not "the book has no snapshot" —
            # re-read before claiming so.
            snapshot_id = db.execute(
                text(
                    "SELECT id FROM book_snapshots WHERE book_id = :book_id "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"book_id": book_id},
            ).scalar()
            if snapshot_id is None:
                raise HTTPException(status_code=409, detail="BOOK_HAS_NO_SNAPSHOT")
    rows = db.execute(
        text(
            "SELECT content_text FROM book_snapshot_chapters "
            "WHERE snapshot_id = :snapshot_id ORDER BY chapter_order"
        ),
        {"snapshot_id": snapshot_id},
    ).all()
    return [row[0] or "" for row in rows], int(snapshot_id)


def _response(profile: dict[str, Any]) -> dict[str, Any]:
    """The profile plus everything the confirmation screen needs to render it.

    The dropdown options and the active deltas are computed here rather than in the client.
    The same rule duplicated in TypeScript would drift from this one — the L2–L4 prompts had
    two copies and did exactly that (INV-P4).
    """
    return {
        **profile,
        "options": presentation_options(),
        "active_deltas": [delta.key for delta in deltas_for(profile.get("axes", {}))],
    }


@router.get("/books/{book_id}/profile")
def get_book_profile(book_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """The stored profile, or 404 if none has been drafted."""
    profile = BookProfileRepository(db).get(book_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="NO_PROFILE")
    return _response(profile)


@router.post("/books/{book_id}/profile/draft")
def draft_book_profile(book_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Draft the profile from the counted half of the text. Free, no provider call.

    A confirmed profile is returned untouched rather than redrafted: re-inferring over a
    decision the user was asked to make would discard it silently.
    """
    repository = BookProfileRepository(db)
    existing = repository.get(book_id)
    if existing and existing["status"] == "confirmed":
        return _response(existing)

    chapter_texts, snapshot_id = _chapter_texts(db, book_id)
    if not chapter_texts:
        raise HTTPException(status_code=409, detail="SNAPSHOT_HAS_NO_CHAPTERS")

    # Candidate names come from the sampled read (L0-B), which is a paid call the caller
    # makes. Without them the name curve is empty and the viewpoint axis stays blank — which
    # is the honest state, not a guess.
    previous_names = list((existing or {}).get("candidate_names", []) or [])
    draft = merge_draft(chapter_texts, {"candidate_names": previous_names})
    saved = repository.save_draft(
        book_id,
        draft,
        snapshot_id=snapshot_id,
        sample_chapters=select_sample_chapters(len(chapter_texts)),
    )
    db.commit()
    return _response(saved)


@router.post("/books/{book_id}/profile/confirm")
def confirm_book_profile(
    book_id: int, request: ConfirmRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Store the user's selections. This is what becomes authoritative (INV-P2)."""
    repository = BookProfileRepository(db)
    draft = repository.get(book_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="NO_PROFILE")

    unknown = [axis for axis in request.axes if axis not in AXES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"UNKNOWN_AXIS:{','.join(unknown)}")

    try:
        confirmed = confirm_profile(draft, request.axes)
    except ValueError as exc:
        # An illegal or incomplete profile is refused rather than stored: one carrying a
        # value no delta recognises is worse than none, because downstream it looks decided.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved = repository.confirm(book_id, confirmed["axes"])
    db.commit()
    return _response(saved)


@router.post("/books/{book_id}/profile/reset")
def reset_book_profile(book_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    """Drop the profile so it can be drafted again — how a user changes their mind."""
    BookProfileRepository(db).clear(book_id)
    db.commit()
    return {"status": "cleared"}
