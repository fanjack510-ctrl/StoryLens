"""CHG-20260801-030 — whole-book prepare route alias HTTP contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app
from app.narrative_core.services.whole_book_fixture_pipeline_v1_service import (
    execute_fixture_minimal_pipeline_v1,
)
from tests.whole_book_minimal_test_helpers import make_engine, prepare_sample_s_run, seed_sample_s_book

client = TestClient(app)


@pytest.fixture()
def wb_client(tmp_path, monkeypatch):
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED", "false")
    engine = make_engine(tmp_path, "chg030-prepare-alias.db")
    factory = sessionmaker(bind=engine)

    def _override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_db
    yield factory
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def test_prepare_alias_and_free_match_for_completed_fixture(wb_client) -> None:
    factory = wb_client
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        execute_fixture_minimal_pipeline_v1(session, run_id)
        session.commit()

    r1 = client.get(f"/api/v1/books/{book_id}/whole-book/prepare")
    r2 = client.get(f"/api/v1/books/{book_id}/whole-book/free/prepare")
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    p1, p2 = r1.json(), r2.json()
    assert p1["latest_run"] is not None
    assert p1["latest_run"]["status"] == "completed"
    assert p1["latest_run"]["result_origin"] == "fixture"
    for key in (
        "book_id",
        "book_title",
        "chapter_count",
        "character_count",
        "mode",
        "latest_run",
        "recoverable_run",
        "real_provider_enabled",
        "fixture_preview_enabled",
        "run_creation_enabled",
    ):
        assert p1.get(key) == p2.get(key), key


def test_prepare_not_started_book_is_200(wb_client) -> None:
    factory = wb_client
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        session.commit()
        book_id = book.id

    for path in (
        f"/api/v1/books/{book_id}/whole-book/prepare",
        f"/api/v1/books/{book_id}/whole-book/free/prepare",
    ):
        r = client.get(path)
        assert r.status_code == 200, (path, r.text)
        body = r.json()
        assert body["latest_run"] is None
        assert body["book_id"] == book_id


def test_prepare_missing_book_same_404(wb_client) -> None:
    r1 = client.get("/api/v1/books/999999/whole-book/prepare")
    r2 = client.get("/api/v1/books/999999/whole-book/free/prepare")
    assert r1.status_code == 404
    assert r2.status_code == 404
    # App exception handler flattens detail to top-level error_code.
    assert r1.json()["error_code"] == r2.json()["error_code"] == "WHOLE_BOOK_BOOK_NOT_FOUND"
