"""Live engine provenance classification (Phase 2B-R1 CHG-053)."""

from __future__ import annotations

from enum import StrEnum

from app.narrative_core.services.private_engine_signature import is_fake_or_test_engine_id


class LiveEngineKind(StrEnum):
    TEST_FAKE = "TEST_FAKE"
    CONTRACT_STUB = "CONTRACT_STUB"
    PRIVATE_REAL = "PRIVATE_REAL"


def classify_live_engine_kind(
    *,
    engine_id: str,
    private_modules_bound: bool,
    synthetic: bool,
) -> LiveEngineKind:
    if is_fake_or_test_engine_id(engine_id):
        return LiveEngineKind.TEST_FAKE
    if not private_modules_bound or synthetic:
        return LiveEngineKind.CONTRACT_STUB
    return LiveEngineKind.PRIVATE_REAL


def assert_live_private_real(
    *,
    engine_id: str,
    private_modules_bound: bool,
    synthetic: bool,
) -> None:
    kind = classify_live_engine_kind(
        engine_id=engine_id,
        private_modules_bound=private_modules_bound,
        synthetic=synthetic,
    )
    if kind == LiveEngineKind.PRIVATE_REAL:
        return
    if not private_modules_bound:
        raise RuntimeError("LIVE_PRIVATE_ENGINE_PACKAGE_MISSING")
    raise RuntimeError("LIVE_SYNTHETIC_ENGINE_FORBIDDEN")


__all__ = [
    "LiveEngineKind",
    "assert_live_private_real",
    "classify_live_engine_kind",
]
