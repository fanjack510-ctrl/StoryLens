"""Phase 1C Agent H — Capability / License / Quota / Run Guard backend tests.

Local suite only — not full pytest. Run with:
  $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
  python -m pytest apps/api/tests/test_narrative_phase1c_capability_backend.py -q
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.narrative_core.capability_legacy import LEGACY_TO_CAPABILITY, map_legacy_feature_key
from app.narrative_core.capability_registry import CAPABILITY_REGISTRY, get_capability_metadata
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.contracts.capability import (
    QuotaPolicy,
    is_pro_gated_capability,
)
from app.narrative_core.enums import (
    CapabilityAvailability,
    CapabilityKey,
    CapabilityReasonCode,
    QuotaPolicyKind,
    SnapshotStatus,
    WholeBookAnalysisMode,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.capability_api_payloads import (
    CapabilityApiError,
    build_capabilities_list_response,
    build_capability_detail_response,
)
from app.narrative_core.services.capability_service import (
    DefaultCapabilityService,
    UNMIGRATED_CAN_USE_FEATURE_CALL_SITES,
    assert_foundation_not_pro_gated,
    make_shipped_test_metadata,
    resolve_capability_key,
)
from app.narrative_core.services.quota_service import (
    InMemoryQuotaService,
    extract_reservation_id,
)
from app.narrative_core.services.run_permission_guard import (
    preflight_whole_book_run,
    require_whole_book_run_permission,
    whole_book_runs_endpoint_disabled,
)
from app.services import entitlement

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


@pytest.fixture()
def quota() -> InMemoryQuotaService:
    return InMemoryQuotaService()


def _shipped_whole_book(**kwargs: Any) -> dict[CapabilityKey, Any]:
    meta = make_shipped_test_metadata(
        CapabilityKey.WHOLE_BOOK_ANALYSIS,
        requires_license=True,
        preview_visible=kwargs.pop("preview_visible", True),
        availability=kwargs.pop("availability", CapabilityAvailability.AVAILABLE),
        supported_modes=(
            WholeBookAnalysisMode.NATIVE,
            WholeBookAnalysisMode.ENHANCED,
        ),
        quota_policies=kwargs.pop("quota_policies", ()),
    )
    return {CapabilityKey.WHOLE_BOOK_ANALYSIS: meta}


# ---------------------------------------------------------------------------
# 1. Capability keys unique
# ---------------------------------------------------------------------------


def test_01_capability_keys_unique() -> None:
    keys = list(CAPABILITY_REGISTRY.keys())
    assert len(keys) == len(set(keys))
    assert set(keys) == set(CapabilityKey)


# ---------------------------------------------------------------------------
# 2–3. whole_book not shipped / preview
# ---------------------------------------------------------------------------


def test_02_whole_book_not_shipped(session: Session) -> None:
    svc = DefaultCapabilityService(session)
    decision = svc.evaluate_capability(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert decision.allowed is False
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_NOT_SHIPPED
    meta = get_capability_metadata(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert meta.shipped is False
    assert meta.requires_license is True


def test_03_preview_visible_not_usable(session: Session) -> None:
    """preview_visible ≠ usable; injected preview metadata still denied when unshipped."""

    preview_meta = make_shipped_test_metadata(
        CapabilityKey.WHOLE_BOOK_ANALYSIS,
        requires_license=True,
        preview_visible=True,
        availability=CapabilityAvailability.PREVIEW,
    )
    # Force shipped=false while preview_visible=true
    from dataclasses import replace

    unshipped_preview = replace(preview_meta, shipped=False)
    svc = DefaultCapabilityService(
        session,
        metadata_overrides={CapabilityKey.WHOLE_BOOK_ANALYSIS: unshipped_preview},
        license_state={"status": "ok", "features": list(CapabilityKey)},
    )
    decision = svc.evaluate_capability(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert decision.allowed is False
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_NOT_SHIPPED
    assert decision.preview_only is True


# ---------------------------------------------------------------------------
# 4–7. License states
# ---------------------------------------------------------------------------


def test_04_license_missing() -> None:
    svc = DefaultCapabilityService(
        metadata_overrides=_shipped_whole_book(),
        license_state={"status": "missing"},
    )
    decision = svc.evaluate_capability(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert decision.allowed is False
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_NOT_LICENSED


def test_05_license_invalid() -> None:
    svc = DefaultCapabilityService(
        metadata_overrides=_shipped_whole_book(),
        license_state={"status": "invalid"},
    )
    decision = svc.evaluate_capability(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert decision.allowed is False
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_LICENSE_INVALID


def test_06_license_expired() -> None:
    svc = DefaultCapabilityService(
        metadata_overrides=_shipped_whole_book(),
        license_state={"status": "expired"},
    )
    decision = svc.evaluate_capability(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert decision.allowed is False
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_LICENSE_EXPIRED


def test_07_valid_license() -> None:
    svc = DefaultCapabilityService(
        metadata_overrides=_shipped_whole_book(),
        license_state={
            "status": "ok",
            "features": [CapabilityKey.WHOLE_BOOK_ANALYSIS.value],
        },
        quota=InMemoryQuotaService(
            policy_overrides={
                CapabilityKey.WHOLE_BOOK_ANALYSIS.value: (
                    QuotaPolicy(kind=QuotaPolicyKind.NONE, policy_key="none"),
                )
            }
        ),
    )
    decision = svc.evaluate_capability(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert decision.allowed is True
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_AVAILABLE


# ---------------------------------------------------------------------------
# 8–10. Modes
# ---------------------------------------------------------------------------


def test_08_native_mode() -> None:
    svc = DefaultCapabilityService(
        metadata_overrides=_shipped_whole_book(),
        license_state={"status": "ok", "features": list(CapabilityKey)},
        quota=InMemoryQuotaService(
            policy_overrides={
                CapabilityKey.WHOLE_BOOK_ANALYSIS.value: (
                    QuotaPolicy(kind=QuotaPolicyKind.NONE),
                )
            }
        ),
    )
    decision = svc.evaluate_mode(
        CapabilityKey.WHOLE_BOOK_ANALYSIS, WholeBookAnalysisMode.NATIVE
    )
    assert decision.allowed is True
    assert WholeBookAnalysisMode.NATIVE in decision.supported_modes


def test_09_enhanced_mode() -> None:
    svc = DefaultCapabilityService(
        metadata_overrides=_shipped_whole_book(),
        license_state={"status": "ok", "features": list(CapabilityKey)},
        quota=InMemoryQuotaService(
            policy_overrides={
                CapabilityKey.WHOLE_BOOK_ANALYSIS.value: (
                    QuotaPolicy(kind=QuotaPolicyKind.NONE),
                )
            }
        ),
    )
    decision = svc.evaluate_mode(
        CapabilityKey.WHOLE_BOOK_ANALYSIS, WholeBookAnalysisMode.ENHANCED
    )
    assert decision.allowed is True


def test_10_unsupported_mode() -> None:
    svc = DefaultCapabilityService(
        metadata_overrides=_shipped_whole_book(),
        license_state={"status": "ok", "features": list(CapabilityKey)},
        quota=InMemoryQuotaService(
            policy_overrides={
                CapabilityKey.WHOLE_BOOK_ANALYSIS.value: (
                    QuotaPolicy(kind=QuotaPolicyKind.NONE),
                )
            }
        ),
    )
    decision = svc.evaluate_mode(CapabilityKey.WHOLE_BOOK_ANALYSIS, "not_a_mode")
    assert decision.allowed is False
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_MODE_NOT_SUPPORTED


# ---------------------------------------------------------------------------
# 11–13. Legacy + can_use_feature
# ---------------------------------------------------------------------------


def test_11_legacy_key_mapping() -> None:
    assert resolve_capability_key("batch_analysis") == CapabilityKey.WHOLE_BOOK_ANALYSIS
    assert LEGACY_TO_CAPABILITY["novel_comparison"] == CapabilityKey.CROSS_BOOK_SEARCH
    mapped = map_legacy_feature_key("advanced_report")
    assert mapped.capability_key == CapabilityKey.ADVANCED_EXPORT


def test_12_unknown_legacy_key(session: Session) -> None:
    gate = entitlement.can_use_feature(session, "totally_unknown_vip_feature")
    assert gate["enabled"] is False
    assert gate["reason"] == "FEATURE_UNKNOWN"


def test_13_can_use_feature_compat(session: Session) -> None:
    """Compat adapter keeps free→deny and does not silently authorize unknowns."""

    free = entitlement.can_use_feature(session, "story_lab")
    assert free["enabled"] is False
    assert free["reason"] == "PRO_LICENSE_REQUIRED"
    assert "capability_reason_code" in free
    assert UNMIGRATED_CAN_USE_FEATURE_CALL_SITES


# ---------------------------------------------------------------------------
# 14. narrative_asset_library does not gate foundation
# ---------------------------------------------------------------------------


def test_14_narrative_asset_library_not_blocking_foundation() -> None:
    assert_foundation_not_pro_gated()
    assert not is_pro_gated_capability(CapabilityKey.NARRATIVE_ASSET_LIBRARY)
    # Entity/asset/relation services must not import capability gating.
    import app.narrative_core.services.entity_service as entity_service
    import app.narrative_core.services.asset_service as asset_service
    import app.narrative_core.services.relation_service as relation_service
    import app.narrative_core.services.conflict_service as conflict_service

    for mod in (entity_service, asset_service, relation_service, conflict_service):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "can_use_feature" not in src
        assert "DefaultCapabilityService" not in src
        assert "require_capability" not in src


# ---------------------------------------------------------------------------
# 15–24. Quota skeleton
# ---------------------------------------------------------------------------


def test_15_quota_none(quota: InMemoryQuotaService) -> None:
    quota.set_policy_overrides(
        {
            "story_lab": (QuotaPolicy(kind=QuotaPolicyKind.NONE, policy_key="none"),),
        }
    )
    decision = quota.evaluate_quota("story_lab")
    assert decision.allowed is True
    assert decision.policy_kind == QuotaPolicyKind.NONE


def test_16_quota_per_book(quota: InMemoryQuotaService) -> None:
    quota.set_policy_overrides(
        {
            "whole_book_analysis": (
                QuotaPolicy(kind=QuotaPolicyKind.PER_BOOK, policy_key="pb", limit=1),
            )
        }
    )
    ctx = {"book_id": 1, "book_snapshot_id": 10}
    first = quota.reserve_usage("whole_book_analysis", context=ctx)
    assert first.allowed is True
    rid = extract_reservation_id(first)
    assert rid
    quota.commit_usage("whole_book_analysis", reservation_id=rid, context=ctx)
    second = quota.evaluate_quota("whole_book_analysis", context=ctx)
    assert second.allowed is False
    assert second.reason_code == CapabilityReasonCode.CAPABILITY_QUOTA_EXCEEDED


def test_17_quota_per_day(quota: InMemoryQuotaService) -> None:
    quota.set_policy_overrides(
        {
            "story_lab": (
                QuotaPolicy(kind=QuotaPolicyKind.PER_DAY, policy_key="day", limit=2),
            )
        }
    )
    d1 = quota.reserve_usage("story_lab", amount=1)
    assert d1.allowed is True
    assert d1.reset_at is not None
    quota.commit_usage(
        "story_lab", reservation_id=extract_reservation_id(d1) or "", context={}
    )
    d2 = quota.reserve_usage("story_lab", amount=1)
    assert d2.allowed is True
    quota.commit_usage(
        "story_lab", reservation_id=extract_reservation_id(d2) or "", context={}
    )
    d3 = quota.evaluate_quota("story_lab")
    assert d3.allowed is False
    assert d3.reset_at is not None


def test_18_quota_concurrent_runs(quota: InMemoryQuotaService) -> None:
    quota.set_policy_overrides(
        {
            "whole_book_analysis": (
                QuotaPolicy(
                    kind=QuotaPolicyKind.CONCURRENT_RUNS, policy_key="cc", limit=1
                ),
            )
        }
    )
    r1 = quota.reserve_usage("whole_book_analysis", context={"book_id": 1})
    assert r1.allowed is True
    r2 = quota.evaluate_quota("whole_book_analysis", context={"book_id": 2})
    assert r2.allowed is False


def test_19_quota_character_limit(quota: InMemoryQuotaService) -> None:
    quota.set_policy_overrides(
        {
            "whole_book_analysis": (
                QuotaPolicy(
                    kind=QuotaPolicyKind.CHARACTER_LIMIT, policy_key="chars", limit=100
                ),
            )
        }
    )
    ok = quota.evaluate_quota(
        "whole_book_analysis", context={"book_id": 1, "character_count": 50}
    )
    assert ok.allowed is True
    bad = quota.evaluate_quota(
        "whole_book_analysis", context={"book_id": 1, "character_count": 200}
    )
    assert bad.allowed is False


def test_20_quota_token_budget(quota: InMemoryQuotaService) -> None:
    quota.set_policy_overrides(
        {
            "whole_book_analysis": (
                QuotaPolicy(
                    kind=QuotaPolicyKind.TOKEN_BUDGET, policy_key="tok", limit=1000
                ),
            )
        }
    )
    assert quota.evaluate_quota(
        "whole_book_analysis", context={"token_count": 100}
    ).allowed
    assert not quota.evaluate_quota(
        "whole_book_analysis", context={"token_count": 5000}
    ).allowed


def test_21_quota_cost_budget(quota: InMemoryQuotaService) -> None:
    quota.set_policy_overrides(
        {
            "whole_book_analysis": (
                QuotaPolicy(
                    kind=QuotaPolicyKind.COST_BUDGET, policy_key="cost", limit=1.5
                ),
            )
        }
    )
    assert quota.evaluate_quota(
        "whole_book_analysis", context={"estimated_cost": 1.0}
    ).allowed
    assert not quota.evaluate_quota(
        "whole_book_analysis", context={"estimated_cost": 2.0}
    ).allowed


def test_22_reservation_commit(quota: InMemoryQuotaService) -> None:
    quota.set_policy_overrides(
        {
            "story_lab": (
                QuotaPolicy(kind=QuotaPolicyKind.PER_DAY, policy_key="day", limit=5),
            )
        }
    )
    reserved = quota.reserve_usage("story_lab", amount=2)
    rid = extract_reservation_id(reserved)
    assert rid
    assert reserved.reserved is not None and reserved.reserved >= 2
    quota.commit_usage("story_lab", reservation_id=rid)
    after = quota.evaluate_quota("story_lab", amount=0)
    assert after.used is not None and after.used >= 2
    assert (after.reserved or 0) == 0


def test_23_reservation_release(quota: InMemoryQuotaService) -> None:
    quota.set_policy_overrides(
        {
            "story_lab": (
                QuotaPolicy(kind=QuotaPolicyKind.PER_DAY, policy_key="day", limit=5),
            )
        }
    )
    reserved = quota.reserve_usage("story_lab", amount=3)
    rid = extract_reservation_id(reserved)
    assert rid
    quota.release_usage("story_lab", reservation_id=rid)
    after = quota.evaluate_quota("story_lab", amount=0)
    assert (after.reserved or 0) == 0
    assert (after.used or 0) == 0


def test_24_duplicate_release_idempotent(quota: InMemoryQuotaService) -> None:
    quota.set_policy_overrides(
        {
            "story_lab": (
                QuotaPolicy(kind=QuotaPolicyKind.PER_DAY, policy_key="day", limit=5),
            )
        }
    )
    reserved = quota.reserve_usage("story_lab", amount=1)
    rid = extract_reservation_id(reserved)
    assert rid
    quota.release_usage("story_lab", reservation_id=rid)
    quota.release_usage("story_lab", reservation_id=rid)  # idempotent
    quota.release_usage("story_lab", reservation_id="missing-id")  # idempotent
    after = quota.evaluate_quota("story_lab", amount=0)
    assert (after.reserved or 0) == 0


# ---------------------------------------------------------------------------
# 25–27. Capability API (payload builders — FastAPI-free for local SSL-broken envs)
# ---------------------------------------------------------------------------


def test_25_get_capabilities() -> None:
    body = build_capabilities_list_response(DefaultCapabilityService())
    assert body["run_creation_enabled"] is False
    assert body["whole_book_runs_endpoint_disabled"] is True
    keys = {item["key"] for item in body["items"]}
    assert keys == {k.value for k in CapabilityKey}
    whole = next(item for item in body["items"] if item["key"] == "whole_book_analysis")
    assert whole["shipped"] is False
    assert whole["preview_visible"] is False
    assert whole["entry_visible"] is False
    assert whole["enabled"] is False
    assert whole["availability"] == "unavailable"
    assert whole["decision"]["reason_code"] == "CAPABILITY_NOT_SHIPPED"
    assert whole["decision"]["allowed"] is False
    native = next(item for item in body["items"] if item["key"] == "whole_book_native")
    assert native["display_name"] == "原生全书分析"
    assert native["entry_visible"] is False
    assert native["reason_code"] == "whole_book_not_released"
    serialized = str(body)
    assert "signed_license" not in serialized
    assert "private_key" not in serialized.lower()


def test_26_get_capability() -> None:
    body = build_capability_detail_response(
        DefaultCapabilityService(), "whole_book_analysis"
    )
    assert body["allowed"] is False
    assert body["reason_code"] == "CAPABILITY_NOT_SHIPPED"
    assert body["metadata"]["supported_modes"] == [
        "whole_book_native",
        "whole_book_enhanced",
    ]
    lib = build_capability_detail_response(
        DefaultCapabilityService(), "narrative_asset_library"
    )
    assert lib["foundation_note"]


def test_27_unknown_api_key() -> None:
    with pytest.raises(CapabilityApiError) as exc:
        build_capability_detail_response(
            DefaultCapabilityService(), "not_a_real_capability"
        )
    assert exc.value.status_code == 404
    assert exc.value.error_code == "CAPABILITY_UNKNOWN"


# ---------------------------------------------------------------------------
# 28–30. Run permission guard
# ---------------------------------------------------------------------------


def test_28_run_guard_default_deny() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert whole_book_runs_endpoint_disabled() is True
    svc = DefaultCapabilityService(
        metadata_overrides=_shipped_whole_book(),
        license_state={"status": "ok", "features": list(CapabilityKey)},
        quota=InMemoryQuotaService(
            policy_overrides={
                CapabilityKey.WHOLE_BOOK_ANALYSIS.value: (
                    QuotaPolicy(kind=QuotaPolicyKind.NONE),
                )
            }
        ),
    )
    result = require_whole_book_run_permission(
        svc,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        book_id=1,
        book_snapshot_id=1,
        snapshot_status=SnapshotStatus.COMPLETED,
    )
    assert result.allowed is False
    assert result.reason_code == "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED"
    assert result.run_creation_enabled is False


def test_29_guard_failure_does_not_create_run() -> None:
    created: list[str] = []

    def run_factory(**_: Any) -> None:
        created.append("run")

    def snapshot_factory(**_: Any) -> None:
        created.append("snapshot")

    svc = DefaultCapabilityService()
    result = require_whole_book_run_permission(
        svc,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        book_id=1,
        book_snapshot_id=1,
        run_factory=run_factory,
        snapshot_factory=snapshot_factory,
    )
    assert result.allowed is False
    assert created == []


def test_30_guard_failure_does_not_call_engine() -> None:
    engine_calls: list[str] = []

    def engine_invoker(**_: Any) -> None:
        engine_calls.append("engine")

    svc = DefaultCapabilityService()
    result = require_whole_book_run_permission(
        svc,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        book_id=1,
        book_snapshot_id=1,
        engine_invoker=engine_invoker,
    )
    assert result.allowed is False
    assert engine_calls == []

    # Even with test override, unshipped capability still denies without engine.
    result2 = require_whole_book_run_permission(
        svc,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        book_id=1,
        book_snapshot_id=1,
        snapshot_status=SnapshotStatus.COMPLETED,
        context={"allow_endpoint_for_test": True},
        engine_invoker=engine_invoker,
    )
    assert result2.allowed is False
    assert engine_calls == []

    preflight = preflight_whole_book_run(
        svc,
        book_id=1,
        book_snapshot_id=1,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        context={"allow_endpoint_for_test": True},
    )
    assert preflight.notes is not None
    assert preflight.notes.get("run_creation_enabled") is False


# ---------------------------------------------------------------------------
# Extra: require_capability + unknown evaluate
# ---------------------------------------------------------------------------


def test_require_capability_raises() -> None:
    svc = DefaultCapabilityService()
    with pytest.raises(NarrativeCoreError) as exc:
        svc.require_capability(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED


def test_unknown_capability_evaluate() -> None:
    svc = DefaultCapabilityService()
    decision = svc.evaluate_capability("nope_capability")
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_UNKNOWN
    assert decision.allowed is False


def test_quota_backend_is_non_production(quota: InMemoryQuotaService) -> None:
    assert quota.backend == "memory_non_production"


def test_modes_are_also_capability_keys_but_entries_disabled() -> None:
    """WB-0.3: whole_book_native/enhanced are independent capability ids.

    Analysis modes share the same string values but product entries stay off.
    """
    for mode in WholeBookAnalysisMode:
        key = CapabilityKey(mode.value)
        meta = get_capability_metadata(key)
        assert meta.enabled is False
        assert meta.entry_visible is False
        assert meta.product_reason_code == "whole_book_not_released"


def test_pro_capabilities_shipped_remains_false() -> None:
    text = (
        REPO_ROOT / "apps" / "desktop" / "src" / "services" / "productEdition.ts"
    ).read_text(encoding="utf-8")
    assert "PRO_CAPABILITIES_SHIPPED = false" in text


def test_endpoint_disabled_constant() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
