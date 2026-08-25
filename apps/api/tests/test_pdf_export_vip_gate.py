"""PDF 导出的 VIP 门 + 爱发电月卡有效期 (CHG-20260815-091).

The HTML export stays free; the PDF endpoint requires the advanced_export capability,
which a monthly card (a signed license carrying valid_until) satisfies until it lapses.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import AnalysisRun, Base, Book, Chapter, LocalLicense, ReaderJourneyRun
from app.db.session import get_db
from app.api.v1 import reader_journey as chapter_router_module
from app.narrative_core.whole_book_v2 import router as v2_router_module
from app.routers import short_form_router as short_form_router_module
from app.services import entitlement
from app.services.license_crypto import (
    LicenseError,
    build_unsigned_payload,
    encode_license,
    parse_and_verify,
    public_key_b64url,
)


@pytest.fixture()
def keypair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    priv = Ed25519PrivateKey.generate()
    key_id = "test-pdfgate-001"
    config = {
        "keys": [
            {
                "key_id": key_id,
                "signature_version": 1,
                "algorithm": "ed25519",
                "environment": "test",
                "public_key_b64url": public_key_b64url(priv.public_key()),
                "status": "active",
            }
        ],
        "commerce": {
            "afdian_product_url": "https://afdian.com/item/test-monthly",
            "product_code": "storylens_pro",
        },
    }
    path = tmp_path / "license_public_keys.test.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: False)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: path)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    return priv, key_id


@pytest.fixture()
def session() -> Session:
    # TestClient serves requests on a worker thread; StaticPool keeps every connection on
    # the one in-memory database the tables were created in.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    from app.narrative_core.migrations.runner import apply_narrative_migrations

    apply_narrative_migrations(engine)
    return sessionmaker(bind=engine)()


@pytest.fixture()
def client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(v2_router_module.router)
    # 单章那份报告走同一道门、同一条打印路径（router.render_report_pdf），所以它必须和
    # 全书一起被这套测试盯着——否则「全书收费、单章白送」这种事没人会发现。
    app.include_router(chapter_router_module.router)
    app.include_router(short_form_router_module.router)
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app)


def _journey_run(session: Session, run_id: int = 7) -> ReaderJourneyRun:
    # 外键是真的：一份旅程必须挂在一本书的一章上，所以先把它的上游摆好。
    session.add(Book(id=1, title="测试书", source_file_name="t.txt", source_file_hash="h"))
    session.add(Chapter(id=1, book_id=1, chapter_index=1, title="第1章"))
    session.add(
        AnalysisRun(
            id=1,
            provider="deepseek",
            model="deepseek-v4-flash",
            prompt_version="1.0",
            schema_version="1.0",
            input_hash="h",
        )
    )
    session.flush()
    row = ReaderJourneyRun(
        id=run_id,
        analysis_run_id=1,
        book_id=1,
        chapter_id=1,
        provider_name="deepseek",
        model_name="deepseek-v4-flash",
        client_request_id=f"test-{run_id}",
    )
    session.add(row)
    session.commit()
    return row


def _short_form_result(session: Session, *, book_id: int = 2, reading_id: int = 11) -> None:
    session.add(
        Book(id=book_id, title="短篇测试", source_file_name="short.txt", source_file_hash="short-h")
    )
    session.flush()
    session.execute(
        text(
            "INSERT INTO short_form_results (id, book_id, result_json)"
            " VALUES (:reading_id, :book_id, '{}')"
        ),
        {"reading_id": reading_id, "book_id": book_id},
    )
    session.commit()


def _code(priv, key_id: str, *, valid_days: int | None = None) -> str:
    valid_until = None
    if valid_days is not None:
        valid_until = (
            (datetime.now(timezone.utc) + timedelta(days=valid_days))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    payload = build_unsigned_payload(major_version=1, key_id=key_id, valid_until=valid_until)
    return encode_license(payload, priv)


def test_free_edition_gets_403_with_afdian_url(client: TestClient, keypair) -> None:
    r = client.post("/api/v1/whole-book-runs/1/v2/export-pdf", json={"html": "<p>x</p>"})
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["error_code"] == "PDF_REQUIRES_VIP"
    assert detail["details"]["feature_key"] == "advanced_export"
    assert detail["details"]["afdian_product_url"] == "https://afdian.com/item/test-monthly"


def test_activated_license_passes_gate(
    client: TestClient, session: Session, keypair, monkeypatch: pytest.MonkeyPatch
) -> None:
    priv, key_id = keypair
    result = entitlement.activate_license_code(session, _code(priv, key_id, valid_days=31))
    assert result["ok"] is True
    assert result["entitlement"]["license_kind"] == "monthly"
    assert result["entitlement"]["valid_until"] is not None
    # No headless browser in CI: reaching the 501 proves the licence gate opened.
    monkeypatch.setattr(v2_router_module, "_find_pdf_browser", lambda: None)
    r = client.post("/api/v1/whole-book-runs/1/v2/export-pdf", json={"html": "<p>x</p>"})
    assert r.status_code == 501
    assert r.json()["detail"]["error_code"] == "PDF_BROWSER_NOT_FOUND"


def test_expired_monthly_card_cannot_activate(session: Session, keypair) -> None:
    priv, key_id = keypair
    with pytest.raises(LicenseError) as err:
        entitlement.activate_license_code(session, _code(priv, key_id, valid_days=-1))
    assert err.value.code == "LICENSE_EXPIRED"


def test_monthly_card_lapses_in_place(
    client: TestClient, session: Session, keypair, monkeypatch: pytest.MonkeyPatch
) -> None:
    priv, key_id = keypair
    entitlement.activate_license_code(session, _code(priv, key_id, valid_days=31))
    assert entitlement.entitlement_snapshot(session)["pro_active"] is True
    # 32 days later the same row reads as expired everywhere at once.
    later = datetime.now(timezone.utc) + timedelta(days=32)
    monkeypatch.setattr(entitlement, "_now", lambda: later)
    snap = entitlement.entitlement_snapshot(session)
    assert snap["edition"] == "free"
    row = session.scalar(select(LocalLicense))
    assert row is not None and row.license_status == "expired"
    r = client.post("/api/v1/whole-book-runs/1/v2/export-pdf", json={"html": "<p>x</p>"})
    assert r.status_code == 403
    assert r.json()["detail"]["error_code"] == "PDF_REQUIRES_VIP"


def test_perpetual_license_still_activates_and_never_lapses(
    session: Session, keypair, monkeypatch: pytest.MonkeyPatch
) -> None:
    priv, key_id = keypair
    result = entitlement.activate_license_code(session, _code(priv, key_id))
    assert result["entitlement"]["license_kind"] == "perpetual"
    later = datetime.now(timezone.utc) + timedelta(days=3650)
    monkeypatch.setattr(entitlement, "_now", lambda: later)
    assert entitlement.entitlement_snapshot(session)["pro_active"] is True


def test_valid_until_survives_verify_roundtrip(keypair) -> None:
    priv, key_id = keypair
    code = _code(priv, key_id, valid_days=31)
    verified = parse_and_verify(
        code,
        public_keys_by_id={key_id: public_key_b64url(priv.public_key())},
        expected_major_version=1,
    )
    assert "valid_until" in verified.payload


def test_chapter_pdf_is_gated_the_same_way(client: TestClient, session: Session, keypair) -> None:
    """单章 PDF 和全书 PDF 是同一件商品，不能有一个门开着。"""
    _journey_run(session)
    r = client.post("/api/v1/reader-journey-runs/7/export-pdf", json={"html": "<p>x</p>"})
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["error_code"] == "PDF_REQUIRES_VIP"
    assert detail["details"]["afdian_product_url"] == "https://afdian.com/item/test-monthly"


def test_chapter_pdf_opens_for_pro(
    client: TestClient, session: Session, keypair, monkeypatch: pytest.MonkeyPatch
) -> None:
    priv, key_id = keypair
    _journey_run(session)
    entitlement.activate_license_code(session, _code(priv, key_id, valid_days=31))
    # CI 上没有无头浏览器：走到 501 就证明门开了，且用的是同一条打印路径。
    monkeypatch.setattr(v2_router_module, "_find_pdf_browser", lambda: None)
    r = client.post("/api/v1/reader-journey-runs/7/export-pdf", json={"html": "<p>x</p>"})
    assert r.status_code == 501
    assert r.json()["detail"]["error_code"] == "PDF_BROWSER_NOT_FOUND"


def test_chapter_pdf_says_which_run_is_missing_before_talking_about_money(
    client: TestClient, keypair
) -> None:
    """不存在的旅程要报 404。先弹「请购买 VIP」再发现根本没这份分析，是最气人的顺序。"""
    r = client.post("/api/v1/reader-journey-runs/999/export-pdf", json={"html": "<p>x</p>"})
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "READER_JOURNEY_RUN_NOT_FOUND"


def test_short_form_pdf_is_gated_the_same_way(
    client: TestClient, session: Session, keypair
) -> None:
    """短篇拆稿、单章和全书的 PDF 都使用 advanced_export。"""
    _short_form_result(session)
    r = client.post(
        "/api/v1/books/2/short-form/readings/11/export-pdf",
        json={"html": "<p>x</p>"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["error_code"] == "PDF_REQUIRES_VIP"


def test_short_form_pdf_checks_the_reading_before_the_pro_gate(
    client: TestClient, session: Session, keypair
) -> None:
    _short_form_result(session)
    r = client.post(
        "/api/v1/books/999/short-form/readings/11/export-pdf",
        json={"html": "<p>x</p>"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "SHORT_FORM_RESULT_NOT_FOUND"


def test_short_form_pdf_opens_for_pro(
    client: TestClient,
    session: Session,
    keypair,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    priv, key_id = keypair
    _short_form_result(session)
    entitlement.activate_license_code(session, _code(priv, key_id, valid_days=31))
    monkeypatch.setattr(v2_router_module, "_find_pdf_browser", lambda: None)
    r = client.post(
        "/api/v1/books/2/short-form/readings/11/export-pdf",
        json={"html": "<p>x</p>"},
    )
    assert r.status_code == 501
    assert r.json()["detail"]["error_code"] == "PDF_BROWSER_NOT_FOUND"
