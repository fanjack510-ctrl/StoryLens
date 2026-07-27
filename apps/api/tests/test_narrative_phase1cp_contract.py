"""Phase 1C-P contract verification tests (local, not full suite)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.narrative_core.capability_legacy import (
    LEGACY_TO_CAPABILITY,
    LEGACY_VIP_FEATURE_KEYS,
    assert_legacy_mapping_conflict_free,
    map_legacy_feature_key,
)
from app.narrative_core.capability_registry import CAPABILITY_REGISTRY, get_capability_metadata
from app.narrative_core.contracts.capability import (
    CapabilityDecision,
    QuotaDecision,
    evaluate_from_metadata,
    is_pro_gated_capability,
    NARRATIVE_FOUNDATION_CAPABILITY_KEYS,
)
from app.narrative_core.contracts.engine import WholeBookAnalysisEngine, WholeBookEngineRegistry
from app.narrative_core.contracts.stage import WholeBookStageResult
from app.narrative_core.contracts.whole_book_dto import WholeBookAnalysisRequest, validate_request_shape
from app.narrative_core.enums import (
    CapabilityAvailability,
    CapabilityKey,
    CapabilityReasonCode,
    SnapshotStatus,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookStageKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.mock_whole_book_engine import (
    MOCK_ENGINE_ID,
    MockWholeBookAnalysisEngine,
)
from app.narrative_core.services.whole_book_engine_registry import InMemoryWholeBookEngineRegistry
from app.narrative_core.whole_book_stages import ORDERED_STAGE_KEYS, WHOLE_BOOK_STAGE_CATALOG

REPO_ROOT = Path(__file__).resolve().parents[3]
DESKTOP_KEYS_TS = REPO_ROOT / "apps" / "desktop" / "src" / "services" / "capability" / "keys.ts"
PRODUCT_EDITION_TS = REPO_ROOT / "apps" / "desktop" / "src" / "services" / "productEdition.ts"

WHOLE_BOOK_ERROR_CODES = {
    "WHOLE_BOOK_ENGINE_NOT_FOUND",
    "WHOLE_BOOK_ENGINE_UNAVAILABLE",
    "WHOLE_BOOK_MODE_NOT_SUPPORTED",
    "WHOLE_BOOK_MODULE_NOT_SUPPORTED",
    "WHOLE_BOOK_REQUEST_INVALID",
    "WHOLE_BOOK_SNAPSHOT_REQUIRED",
    "WHOLE_BOOK_RUN_SNAPSHOT_MISMATCH",
    "WHOLE_BOOK_STAGE_NOT_RESUMABLE",
    "WHOLE_BOOK_STAGE_CANCELLED",
    "WHOLE_BOOK_CAPABILITY_DENIED",
    "WHOLE_BOOK_QUOTA_EXCEEDED",
    "WHOLE_BOOK_BUDGET_DENIED",
}


def _sample_capability_decision(*, allowed: bool = True) -> CapabilityDecision:
    meta = get_capability_metadata(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    return CapabilityDecision(
        capability_key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
        allowed=allowed,
        reason_code=(
            CapabilityReasonCode.CAPABILITY_AVAILABLE
            if allowed
            else CapabilityReasonCode.CAPABILITY_NOT_SHIPPED
        ),
        availability=CapabilityAvailability.UNAVAILABLE,
        metadata=meta,
    )


def _sample_request(**overrides: object) -> WholeBookAnalysisRequest:
    base = {
        "run_id": 1,
        "book_id": 10,
        "book_snapshot_id": 100,
        "analysis_mode": WholeBookAnalysisMode.NATIVE,
        "capability_context": _sample_capability_decision(),
        "snapshot_status": SnapshotStatus.COMPLETED,
    }
    base.update(overrides)
    return WholeBookAnalysisRequest(**base)  # type: ignore[arg-type]


def test_protocol_imports() -> None:
    from app.narrative_core.contracts.capability import CapabilityService
    from app.narrative_core.contracts.engine import WholeBookAnalysisEngine, WholeBookEngineRegistry

    assert CapabilityService is not None
    assert WholeBookAnalysisEngine is not None
    assert WholeBookEngineRegistry is not None


def test_request_dto_requires_completed_snapshot() -> None:
    with pytest.raises(NarrativeCoreError) as exc:
        validate_request_shape(
            _sample_request(
                book_snapshot_id=0,
                capability_context=_sample_capability_decision(),
            )
        )
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED

    with pytest.raises(NarrativeCoreError) as exc2:
        validate_request_shape(
            _sample_request(snapshot_status=SnapshotStatus.BUILDING)
        )
    assert exc2.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED


def test_request_dto_denies_when_capability_not_allowed() -> None:
    with pytest.raises(NarrativeCoreError) as exc:
        validate_request_shape(
            _sample_request(capability_context=_sample_capability_decision(allowed=False))
        )
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED


def test_native_and_enhanced_modes_supported() -> None:
    engine = MockWholeBookAnalysisEngine()
    modes = {m.value for m in engine.supported_modes()}
    assert modes == {"whole_book_native", "whole_book_enhanced"}
    for mode in (WholeBookAnalysisMode.NATIVE, WholeBookAnalysisMode.ENHANCED):
        req = _sample_request(analysis_mode=mode)
        plan = engine.build_stage_plan(req)
        assert plan.mode == mode


def test_stage_catalog_order_unique_deps() -> None:
    keys = [stage.stage_key for stage in WHOLE_BOOK_STAGE_CATALOG]
    assert len(keys) == len(set(keys))
    assert keys == list(ORDERED_STAGE_KEYS)
    known = set(WholeBookStageKey)
    for stage in WHOLE_BOOK_STAGE_CATALOG:
        for dep in stage.depends_on:
            assert dep in known
        if stage.depends_on:
            assert keys.index(stage.stage_key) > max(keys.index(d) for d in stage.depends_on)


def test_stage_result_shape() -> None:
    result = WholeBookStageResult(
        stage_key=WholeBookStageKey.BUILD_FULLTEXT_INDEX,
        status=StageStatus.COMPLETED,
    )
    assert result.stage_key == WholeBookStageKey.BUILD_FULLTEXT_INDEX
    assert result.status == StageStatus.COMPLETED
    assert result.artifacts_written == 0


def test_engine_registry_register_mock_health_check() -> None:
    registry = InMemoryWholeBookEngineRegistry()
    engine = MockWholeBookAnalysisEngine()
    registry.register_engine(engine)
    assert registry.list_engines() == (MOCK_ENGINE_ID,)
    loaded = registry.get_engine(MOCK_ENGINE_ID)
    health = loaded.health_check()
    assert health["healthy"] is True
    assert health["mock"] is True


def test_capability_keys_unique_match_frontend() -> None:
    python_keys = sorted(k.value for k in CapabilityKey)
    assert len(python_keys) == len(set(python_keys))
    ts_text = DESKTOP_KEYS_TS.read_text(encoding="utf-8")
    match = re.search(
        r"export const CAPABILITY_KEYS = \[(.*?)\] as const",
        ts_text,
        re.DOTALL,
    )
    assert match is not None
    ts_keys = re.findall(r'"([^"]+)"', match.group(1))
    assert sorted(ts_keys) == python_keys


def test_shipped_false_evaluate_returns_not_shipped() -> None:
    meta = get_capability_metadata(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert meta.shipped is False
    decision = evaluate_from_metadata(meta, licensed=True)
    assert decision.allowed is False
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_NOT_SHIPPED


def test_capability_and_quota_decision_fields() -> None:
    meta = get_capability_metadata(CapabilityKey.NARRATIVE_ASSET_LIBRARY)
    cap = CapabilityDecision(
        capability_key=meta.key,
        allowed=False,
        reason_code=CapabilityReasonCode.CAPABILITY_NOT_SHIPPED,
        availability=CapabilityAvailability.UNAVAILABLE,
        metadata=meta,
    )
    quota = QuotaDecision(
        allowed=True,
        reason_code=CapabilityReasonCode.CAPABILITY_AVAILABLE,
    )
    assert cap.capability_key == CapabilityKey.NARRATIVE_ASSET_LIBRARY
    assert quota.allowed is True


def test_legacy_mapper_no_conflicts() -> None:
    assert_legacy_mapping_conflict_free()
    assert len(LEGACY_VIP_FEATURE_KEYS) == 7
    for legacy in LEGACY_VIP_FEATURE_KEYS:
        mapping = map_legacy_feature_key(legacy)
        assert mapping.capability_key is not None
        assert mapping.legacy_key == legacy
    # many-to-one allowed
    targets = [LEGACY_TO_CAPABILITY[k].value for k in LEGACY_VIP_FEATURE_KEYS]
    assert targets.count("whole_book_analysis") >= 3


def test_whole_book_error_codes_present() -> None:
    codes = {member.value for member in NarrativeCoreErrorCode}
    assert WHOLE_BOOK_ERROR_CODES <= codes


def test_narrative_foundation_not_pro_gated() -> None:
    assert CapabilityKey.NARRATIVE_ASSET_LIBRARY in NARRATIVE_FOUNDATION_CAPABILITY_KEYS
    assert is_pro_gated_capability(CapabilityKey.NARRATIVE_ASSET_LIBRARY) is False
    assert is_pro_gated_capability(CapabilityKey.WHOLE_BOOK_ANALYSIS) is True


def test_pro_capabilities_shipped_still_false() -> None:
    text = PRODUCT_EDITION_TS.read_text(encoding="utf-8")
    assert "PRO_CAPABILITIES_SHIPPED = false" in text


def test_mock_engine_execute_stage_no_model() -> None:
    engine = MockWholeBookAnalysisEngine()
    from app.narrative_core.contracts.stage import WholeBookStageContext

    ctx = WholeBookStageContext(
        run_id=1,
        book_id=10,
        book_snapshot_id=100,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        stage_key=WholeBookStageKey.BUILD_FULLTEXT_INDEX,
        capability_context=_sample_capability_decision(),
    )
    result = engine.execute_stage(ctx)
    assert result.status == StageStatus.COMPLETED
    assert result.metrics.get("mock") is True


def test_all_registry_keys_present() -> None:
    for key in CapabilityKey:
        assert key in CAPABILITY_REGISTRY
