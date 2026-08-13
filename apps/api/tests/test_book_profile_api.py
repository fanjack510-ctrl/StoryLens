"""Book profile API — draft, confirm, reset.

These assert the boundary rules, which are the ones a client can violate: an axis value the
engine cannot dispatch on must be refused rather than stored, and a confirmed profile must
survive a later draft. A stored profile carrying an unrecognised value is worse than none,
because everything downstream treats it as decided.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Book, BookSnapshot, BookSnapshotChapter, Chapter
from app.db.session import get_db
from app.main import create_app
from app.narrative_core.migrations.runner import apply_narrative_migrations

CHAPTER = "「有人说话。」邓肯走进房间。\n凡娜看着窗外。\n雪莉低声开口。\n" + "。" * 3000

# The app wraps every HTTPException as {error_code, message, details}, not FastAPI's default
# {detail}. These assert the shape a client actually receives.


@pytest.fixture()
def client():
    path = os.path.join(tempfile.mkdtemp(), "profile_api.db")
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    apply_narrative_migrations(engine)
    Session = sessionmaker(bind=engine)

    # Seeded through the ORM so each model's Python-side defaults apply. Hand-written
    # INSERTs miss them and break again every time a column is added — which is exactly
    # what happened here on snapshot_version.
    seed = Session()
    seed.add(Book(id=1, title="深海余烬", source_file_name="x.txt", source_file_hash="h"))
    seed.flush()
    seed.add(BookSnapshot(id=1, book_id=1, content_hash="snap-hash"))
    for order in range(1, 41):
        seed.add(Chapter(id=order, book_id=1, chapter_index=order, title=f"第{order}章"))
    seed.flush()
    for order in range(1, 41):
        seed.add(
            BookSnapshotChapter(
                snapshot_id=1,
                source_chapter_id=order,
                chapter_order=order,
                title=f"第{order}章",
                content_hash=f"h{order}",
                content_text=CHAPTER,
            )
        )
    seed.commit()
    seed.close()

    app = create_app()
    app.dependency_overrides[get_db] = lambda: Session()
    return TestClient(app)


def test_a_book_with_no_profile_reads_as_absent(client):
    assert client.get("/api/v1/books/1/profile").status_code == 404


def test_drafting_counts_the_text_and_returns_the_dropdowns(client):
    body = client.post("/api/v1/books/1/profile/draft").json()
    assert body["status"] == "draft"
    assert body["statistics"]["chapters"] == 40
    # Chapter length is objective, so this axis is settled without a provider call.
    assert body["axes"]["monetization"]["value"] == "paid_subscription"
    # The dropdowns come from the backend, so the vocabulary lives in one place.
    axes = {row["axis"] for row in body["options"]}
    assert axes == {"monetization", "audience", "engine", "pov", "length"}


def test_drafting_needs_no_provider_and_leaves_unreadable_axes_blank(client):
    """Audience cannot be counted, so it stays empty until the sampled read supplies it."""
    body = client.post("/api/v1/books/1/profile/draft").json()
    assert body["axes"]["audience"]["value"] == ""


def test_an_illegal_axis_value_is_refused(client):
    client.post("/api/v1/books/1/profile/draft")
    refused = client.post(
        "/api/v1/books/1/profile/confirm", json={"axes": {"engine": "都市异能"}}
    )
    assert refused.status_code == 400
    assert "illegal value" in refused.json()["message"]
    assert client.get("/api/v1/books/1/profile").json()["status"] == "draft"


def test_an_unknown_axis_is_refused(client):
    client.post("/api/v1/books/1/profile/draft")
    refused = client.post(
        "/api/v1/books/1/profile/confirm", json={"axes": {"platform": "qidian"}}
    )
    assert refused.status_code == 400
    assert "UNKNOWN_AXIS" in refused.json()["message"]


def test_an_incomplete_profile_is_refused(client):
    """Audience has no counted fallback, so confirming without it must not pass as decided."""
    client.post("/api/v1/books/1/profile/draft")
    refused = client.post("/api/v1/books/1/profile/confirm", json={"axes": {}})
    assert refused.status_code == 400
    assert "incomplete" in refused.json()["message"]


def test_confirming_marks_the_user_as_the_source_and_reports_active_deltas(client):
    client.post("/api/v1/books/1/profile/draft")
    body = client.post(
        "/api/v1/books/1/profile/confirm",
        json={"axes": {"audience": "neutral", "engine": "mystery", "pov": "ensemble"}},
    ).json()
    assert body["status"] == "confirmed"
    assert body["axes"]["pov"]["source"] == "user"
    # The ensemble profile switches on the viewpoint field; the client is told, not asked.
    assert body["active_deltas"] == ["pov_entity"]


def test_a_single_lead_profile_activates_no_delta(client):
    client.post("/api/v1/books/1/profile/draft")
    body = client.post(
        "/api/v1/books/1/profile/confirm",
        json={"axes": {"audience": "neutral", "engine": "mystery", "pov": "single_lead"}},
    ).json()
    assert body["active_deltas"] == []


def test_a_confirmed_profile_survives_a_later_draft(client):
    client.post("/api/v1/books/1/profile/draft")
    client.post(
        "/api/v1/books/1/profile/confirm",
        json={"axes": {"audience": "female_romance", "engine": "romance", "pov": "dual_lead"}},
    )
    again = client.post("/api/v1/books/1/profile/draft").json()
    assert again["status"] == "confirmed"
    assert again["axes"]["engine"]["value"] == "romance"


def test_reset_lets_the_profile_be_drafted_again(client):
    client.post("/api/v1/books/1/profile/draft")
    client.post(
        "/api/v1/books/1/profile/confirm",
        json={"axes": {"audience": "neutral", "engine": "mystery", "pov": "ensemble"}},
    )
    assert client.post("/api/v1/books/1/profile/reset").json()["status"] == "cleared"
    assert client.get("/api/v1/books/1/profile").status_code == 404


def test_a_book_without_a_snapshot_says_so(client):
    assert client.post("/api/v1/books/99/profile/draft").status_code == 409
