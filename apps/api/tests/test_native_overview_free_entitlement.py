"""CHG-20260726-004 — Native Overview Free entitlement (no Pro license).

Does not call real Providers. Feature flag remains the ship gate.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.narrative_core.capability_registry import get_capability_metadata
from app.narrative_core.contracts.whole_book_overview_errors import WholeBookOverviewErrorCode
from app.narrative_core.enums import CapabilityKey, WholeBookAnalysisMode
from app.narrative_core.services.capability_service import DefaultCapabilityService
from app.narrative_core.services.native_overview_seed import seed_short_book_v1
from app.services import entitlement

pytest_plugins = ["test_native_overview_walking_skeleton"]

from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    FIXTURE_ENGINE_VERSION,
)

CREATE_BODY = {
    "mode": "whole_book_native",
    "module_key": "book_overview",
    "provider_id": FIXTURE_ENGINE_ID,
    "model_id": FIXTURE_ENGINE_VERSION,
    "client_request_id": "free-entitlement",
    "consent": {
        "estimated_tokens": 0,
        "estimated_cost": 0.0,
        "currency": "CNY",
        "confirmed": True,
    },
}


def _seed_free_book(api_env) -> int:
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        return int(book.id)


def test_free_preflight_allows_native_overview(api_env):
    book_id = _seed_free_book(api_env)
    resp = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs/preflight",
        json={"module_key": "book_overview", "mode": "whole_book_native"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["license_allowed"] is True
    assert body["run_creation_enabled"] is True
    codes = [
        (e.get("code") if isinstance(e, dict) else e) for e in body.get("blocking_errors") or []
    ]
    assert "PRO_LICENSE_REQUIRED" not in codes


def test_free_create_get_overview_no_pro_license(api_env):
    book_id = _seed_free_book(api_env)
    client: TestClient = api_env["client"]
    created = client.post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "free-entitlement-create"},
    )
    assert created.status_code == 201, created.text
    run_id = int(created.json()["run_id"])
    assert created.json().get("error_code") != "PRO_LICENSE_REQUIRED"

    got = client.get(f"/api/v1/whole-book-runs/{run_id}")
    assert got.status_code == 200
    overview = client.get(f"/api/v1/whole-book-runs/{run_id}/overview")
    assert overview.status_code == 200


def test_future_pro_capability_still_requires_license(api_env):
    """Chapter aggregation insights remain Pro-gated."""
    factory = api_env["factory"]
    with factory() as session:
        snap = entitlement.entitlement_snapshot(session)
        assert snap.get("pro_active") is False
        meta = get_capability_metadata(CapabilityKey.PRO_WHOLE_BOOK_INSIGHTS)
        assert meta.requires_license is True
        decision = DefaultCapabilityService(session).evaluate_capability(
            CapabilityKey.PRO_WHOLE_BOOK_INSIGHTS
        )
        assert decision.allowed is False


def test_whole_book_analysis_enhanced_mode_still_license_gated(api_env):
    """Enhanced mode remains Pro; native Free does not open Enhanced."""
    factory = api_env["factory"]
    with factory() as session:
        svc = DefaultCapabilityService(session)
        decision = svc.evaluate_mode(
            CapabilityKey.WHOLE_BOOK_ANALYSIS,
            WholeBookAnalysisMode.ENHANCED,
        )
        assert decision.allowed is False


def test_pro_license_error_code_still_defined():
    assert WholeBookOverviewErrorCode.PRO_LICENSE_REQUIRED.value == "PRO_LICENSE_REQUIRED"
