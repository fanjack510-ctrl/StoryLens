from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.routers import material_lab_router
from app.services import entitlement


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(
        entitlement,
        "can_use_feature",
        lambda _db, feature: {
            "enabled": False,
            "reason": "CAPABILITY_NOT_LICENSED",
            "feature_key": feature,
        },
    )
    monkeypatch.setattr(
        entitlement,
        "commerce_config",
        lambda: {
            "afdian_product_url": "https://afdian.com/item/storylens-test",
            "product_label": "StoryLens Pro 1.x",
        },
    )
    app = FastAPI()
    app.include_router(material_lab_router.router)
    app.dependency_overrides[get_db] = lambda: object()
    return TestClient(app)


def test_extract_from_completed_book_requires_pro(monkeypatch) -> None:
    response = _client(monkeypatch).post(
        "/api/v1/material-lab/library/sources/8/extract",
        json={"genre_slug": "xuanyi"},
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error_code"] == "PRO_FEATURE_REQUIRED"
    assert detail["details"]["feature_key"] == "knowledge_extraction"
    assert detail["details"]["afdian_product_url"].startswith("https://afdian.com/")


def test_book_skill_generation_requires_pro(monkeypatch) -> None:
    response = _client(monkeypatch).post("/api/v1/material-lab/library/skills/8")
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error_code"] == "PRO_FEATURE_REQUIRED"
    assert detail["details"]["feature_key"] == "book_skill_generation"
