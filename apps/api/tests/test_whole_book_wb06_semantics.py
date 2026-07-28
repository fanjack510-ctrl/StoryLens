"""WB-0.6 — product semantics regression."""

from __future__ import annotations

from app.narrative_core.capability_registry import get_capability_metadata
from app.narrative_core.enums import CapabilityKey
from app.narrative_core.services.capability_api_payloads import build_capabilities_list_response
from app.narrative_core.services.capability_service import DefaultCapabilityService


def test_three_capabilities_display_names() -> None:
    native = get_capability_metadata(CapabilityKey.WHOLE_BOOK_NATIVE)
    enhanced = get_capability_metadata(CapabilityKey.WHOLE_BOOK_ENHANCED)
    insights = get_capability_metadata(CapabilityKey.CHAPTER_AGGREGATE_INSIGHTS)
    assert native.display_name == "原生全书分析"
    assert enhanced.display_name == "精细增强分析"
    assert insights.display_name == "章节精细分析覆盖"
    assert "全书洞察" not in native.display_name
    assert insights.display_name != "全书分析"


def test_entries_not_visible() -> None:
    for key in (
        CapabilityKey.WHOLE_BOOK_NATIVE,
        CapabilityKey.WHOLE_BOOK_ENHANCED,
        CapabilityKey.CHAPTER_AGGREGATE_INSIGHTS,
    ):
        meta = get_capability_metadata(key)
        assert meta.entry_visible is False
        assert meta.enabled is False


def test_capabilities_list_payload_hides_entries() -> None:
    payload = build_capabilities_list_response(DefaultCapabilityService())
    items = payload.get("items") or payload.get("capabilities") or []
    for item in items:
        if item["key"] in {
            CapabilityKey.WHOLE_BOOK_NATIVE.value,
            CapabilityKey.WHOLE_BOOK_ENHANCED.value,
            CapabilityKey.CHAPTER_AGGREGATE_INSIGHTS.value,
        }:
            assert item["entry_visible"] is False
