"""Storage for the per-book profile.

The rules worth pinning are the ones about *whose* answer survives. A confirmed profile
represents a decision the user was explicitly asked to make; a later draft must not quietly
replace it, or the run that follows extracts under assumptions nobody agreed to.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Book
from app.narrative_core.long_novel.profile_repository import BookProfileRepository
from app.narrative_core.migrations.runner import apply_narrative_migrations

DRAFT = {
    "axes": {
        "monetization": {"value": "paid_subscription", "source": "L0-A"},
        "pov": {"value": "ensemble", "source": "L0-C"},
    },
    "disagreements": [{"axis": "pov", "counted": "ensemble", "read": "single_lead"}],
    "statistics": {"chapters": 806},
    "name_deciles": {"邓肯": [1, 2, 3]},
    "candidate_names": ["邓肯", "凡娜"],
    "opening_notes": {"conflict_paragraph": 3},
}


@pytest.fixture()
def session():
    path = os.path.join(tempfile.mkdtemp(), "profile.db")
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    apply_narrative_migrations(engine)
    made = sessionmaker(bind=engine)()
    made.add(Book(id=1, title="深海余烬", source_file_name="x.txt", source_file_hash="h"))
    made.commit()
    return made


def test_a_book_with_no_profile_reads_as_absent(session):
    assert BookProfileRepository(session).get(1) is None


def test_a_draft_round_trips_with_its_evidence(session):
    repo = BookProfileRepository(session)
    saved = repo.save_draft(1, DRAFT, snapshot_id=7, sample_chapters=[1, 2, 3, 90])
    assert saved["status"] == "draft"
    assert saved["axes"]["pov"]["value"] == "ensemble"
    assert saved["disagreements"][0]["read"] == "single_lead"
    assert saved["name_deciles"]["邓肯"] == [1, 2, 3]
    assert saved["sample_chapters"] == [1, 2, 3, 90]
    assert saved["snapshot_id"] == 7


def test_redrafting_replaces_a_draft_and_leaves_one_row(session):
    repo = BookProfileRepository(session)
    repo.save_draft(1, DRAFT)
    second = dict(DRAFT, candidate_names=["邓肯", "雪莉", "阿加莎"])
    repo.save_draft(1, second)
    assert repo.get(1)["candidate_names"] == ["邓肯", "雪莉", "阿加莎"]
    count = session.execute(
        __import__("sqlalchemy").text("SELECT COUNT(*) FROM book_profiles")
    ).scalar()
    assert count == 1


def test_confirming_marks_the_profile_authoritative(session):
    repo = BookProfileRepository(session)
    repo.save_draft(1, DRAFT)
    confirmed = repo.confirm(
        1, {"pov": {"value": "single_lead", "source": "user"}}
    )
    assert confirmed["status"] == "confirmed"
    assert confirmed["axes"]["pov"]["source"] == "user"
    assert confirmed["confirmed_at"]


def test_a_draft_never_overwrites_a_confirmed_profile(session):
    """The user was asked to decide. A later inference does not get to undo that."""
    repo = BookProfileRepository(session)
    repo.save_draft(1, DRAFT)
    repo.confirm(1, {"pov": {"value": "single_lead", "source": "user"}})

    repo.save_draft(1, dict(DRAFT, candidate_names=["完全不同的人"]))

    kept = repo.get(1)
    assert kept["status"] == "confirmed"
    assert kept["axes"]["pov"]["value"] == "single_lead"
    assert kept["candidate_names"] == ["邓肯", "凡娜"]


def test_clearing_lets_the_profile_be_drafted_again(session):
    repo = BookProfileRepository(session)
    repo.save_draft(1, DRAFT)
    repo.confirm(1, {"pov": {"value": "single_lead", "source": "user"}})
    repo.clear(1)
    assert repo.get(1) is None
    assert repo.save_draft(1, DRAFT)["status"] == "draft"


def test_confirming_without_a_draft_is_refused(session):
    with pytest.raises(LookupError):
        BookProfileRepository(session).confirm(1, {})
