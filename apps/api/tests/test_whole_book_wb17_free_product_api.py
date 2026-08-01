"""WB-1.7 backend slice — free product coordination service tests."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_free_product_v1_service import (
    create_free_whole_book_analysis_v1,
    free_product_enabled,
    prepare_free_whole_book_analysis_v1,
)
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book


def test_free_product_flag_default_false(monkeypatch) -> None:
    monkeypatch.delenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", raising=False)
    assert free_product_enabled() is False


def test_prepare_requires_feature_flag(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", raising=False)
    engine = make_engine(tmp_path, "wb17-flag.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        with pytest.raises(WholeBookFoundationError) as exc:
            prepare_free_whole_book_analysis_v1(session, book.id)
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_FREE_PRODUCT_DISABLED.value
    engine.dispose()


def test_create_free_blocks_real_provider_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED", "false")
    engine = make_engine(tmp_path, "wb17-create.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        with pytest.raises(WholeBookFoundationError) as exc:
            create_free_whole_book_analysis_v1(
                session,
                book.id,
                estimate_id=1,
                consent_id=1,
                client_request_id="req-1",
            )
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED.value
    engine.dispose()


def test_prepare_returns_product_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED", "false")
    engine = make_engine(tmp_path, "wb17-prepare-shape.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        payload = prepare_free_whole_book_analysis_v1(session, book.id)
        assert payload["book_id"] == book.id
        assert payload["book_title"] == "Sample S"
        assert payload["chapter_count"] >= 1
        assert payload["mode_label"] == "原生全书分析"
        assert payload["product_enabled"] is True
        assert payload["fixture_preview_enabled"] is True
        assert payload["real_provider_enabled"] is False
        assert payload["latest_run"] is None
        assert "estimate_id" in payload["estimate"]
        assert "estimated_windows" in payload["estimate"]
        session.commit()
    engine.dispose()


def test_prepare_missing_book_is_not_found(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    engine = make_engine(tmp_path, "wb17-missing-book.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        with pytest.raises(WholeBookFoundationError) as exc:
            prepare_free_whole_book_analysis_v1(session, 999999)
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_NOT_FOUND.value
    engine.dispose()


def test_product_prepare_routes_registered() -> None:
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/api/v1/books/{book_id}/whole-book/prepare" in paths
    assert "/api/v1/books/{book_id}/whole-book/free/prepare" in paths
    assert "/api/v1/books/{book_id}/whole-book/runs/fixture" in paths
    assert "/api/v1/books/{book_id}/whole-book/free/create-fixture" in paths
