from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Collection
from app.db.session import get_db
from app.routers import common_patterns_router


def _client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Collection(id=4, name="扫榜第一批", note=""))
    session.commit()
    app = FastAPI()
    app.include_router(common_patterns_router.router)
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app), session


def test_common_patterns_pdf_is_pro_gated() -> None:
    client, session = _client()
    try:
        response = client.post(
            "/api/v1/collections/4/common-patterns/export-pdf",
            json={"html": "<html><title>测试榜单</title><p>结构化结果</p></html>"},
        )
        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["error_code"] == "PDF_REQUIRES_VIP"
        assert detail["details"]["feature_key"] == "advanced_export"
    finally:
        session.close()


def test_common_patterns_pdf_checks_collection_before_upsell() -> None:
    client, session = _client()
    try:
        response = client.post(
            "/api/v1/collections/999/common-patterns/export-pdf",
            json={"html": "<p>不存在的榜单</p>"},
        )
        assert response.status_code == 404
    finally:
        session.close()


def test_common_patterns_pdf_rejects_empty_report() -> None:
    client, session = _client()
    try:
        response = client.post(
            "/api/v1/collections/4/common-patterns/export-pdf",
            json={"html": ""},
        )
        assert response.status_code == 422
    finally:
        session.close()
