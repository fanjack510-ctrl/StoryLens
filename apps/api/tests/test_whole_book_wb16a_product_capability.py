"""WB-1.6A — Free/Pro product capability contract tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_product_capability_v1 import (
    AccessTier,
    CapabilityAccessStatus,
    PRODUCT_CAPABILITY_REGISTRY,
    list_product_capabilities,
    require_capability_access,
    resolve_capability_access,
)

client = TestClient(app)


def test_free_capability_registry_counts() -> None:
    free_available = [
        c for c in PRODUCT_CAPABILITY_REGISTRY.values() if c.required_tier == AccessTier.free
    ]
    pro_planned = [
        c for c in PRODUCT_CAPABILITY_REGISTRY.values() if c.required_tier == AccessTier.pro
    ]
    assert len(free_available) == 4
    assert len(pro_planned) == 8


def test_free_user_granted_for_available_modules() -> None:
    overview = resolve_capability_access("whole_book.overview", AccessTier.free)
    chars = resolve_capability_access("whole_book.characters_events", AccessTier.free)
    assert overview["access_status"] == CapabilityAccessStatus.granted.value
    assert chars["access_status"] == CapabilityAccessStatus.granted.value
    assert overview["reason_code"] is None


def test_planned_free_and_pro_return_planned() -> None:
    structure = resolve_capability_access("whole_book.structure", AccessTier.free)
    pro = resolve_capability_access("whole_book.storylines", AccessTier.free)
    assert structure["access_status"] == CapabilityAccessStatus.planned.value
    assert structure["reason_code"] == "capability_planned"
    assert pro["access_status"] == CapabilityAccessStatus.planned.value


def test_unknown_capability_rejected() -> None:
    resolved = resolve_capability_access("whole_book.unknown", AccessTier.free)
    assert resolved["reason_code"] == "capability_unknown"
    with pytest.raises(WholeBookFoundationError) as exc:
        require_capability_access("whole_book.unknown", AccessTier.free)
    assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_CAPABILITY_DISABLED.value


def test_list_product_capabilities_api() -> None:
    resp = client.get("/api/v1/whole-book/product-capabilities?tier=free")
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_tier"] == "free"
    assert len(body["capabilities"]) == 12


def test_capability_access_api() -> None:
    resp = client.get("/api/v1/whole-book/product-capabilities/whole_book.overview/access?tier=free")
    assert resp.status_code == 200
    assert resp.json()["access_status"] == "granted"


def test_gate_helper_blocks_planned() -> None:
    with pytest.raises(WholeBookFoundationError):
        require_capability_access("whole_book.structure", AccessTier.free)


def test_defaults_to_free_tier() -> None:
    caps = list_product_capabilities()
    assert all(item["required_tier"] in {"free", "pro"} for item in caps)
