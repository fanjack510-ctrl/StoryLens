"""WB-1.7 backend slice — free product coordination service tests."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.orm import sessionmaker

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
