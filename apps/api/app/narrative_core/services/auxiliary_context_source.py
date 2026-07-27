"""Auxiliary Context Source Protocol (Phase 2B Integration / CHG-040).

Enhanced mode may inject Scene/Journey/chapter-asset fixtures without bypassing
DB constraints or inventing illegal Scene ORM rows. Real Scene ORM E2E remains
a known limitation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

from app.narrative_core.private_engine_contract.context import WholeBookContextUnit
from app.narrative_core.services.whole_book_context_pipeline import EnhancedAuxAssetRef


@dataclass(frozen=True, slots=True)
class AuxiliaryContextFixture:
    """Generic Enhanced auxiliary fixture — not a real Scene ORM seed."""

    aux_refs: tuple[EnhancedAuxAssetRef, ...] = ()
    extra_units: tuple[WholeBookContextUnit, ...] = ()
    warnings: tuple[str, ...] = ()
    missing: bool = False
    stale: bool = False
    synthetic: bool = True
    non_production: bool = True


@runtime_checkable
class AuxiliaryContextSource(Protocol):
    def load_auxiliary(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
    ) -> AuxiliaryContextFixture: ...


@dataclass
class EmptyAuxiliaryContextSource:
    """Default: no aux assets — Enhanced degrades with warnings."""

    def load_auxiliary(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
    ) -> AuxiliaryContextFixture:
        _ = (book_id, book_snapshot_id)
        return AuxiliaryContextFixture(
            warnings=("enhanced_missing_aux_via_fixture",),
            missing=True,
            synthetic=True,
            non_production=True,
        )


@dataclass
class FixtureAuxiliaryContextSource:
    """Injectable fixture source for full/missing/stale Enhanced tests."""

    fixtures: dict[tuple[int, int], AuxiliaryContextFixture] = field(default_factory=dict)
    default: AuxiliaryContextFixture = field(
        default_factory=lambda: AuxiliaryContextFixture(
            warnings=("enhanced_missing_aux_via_fixture",),
            missing=True,
        )
    )

    def register(self, book_id: int, book_snapshot_id: int, fixture: AuxiliaryContextFixture) -> None:
        self.fixtures[(book_id, book_snapshot_id)] = fixture

    def load_auxiliary(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
    ) -> AuxiliaryContextFixture:
        return self.fixtures.get((book_id, book_snapshot_id), self.default)


def make_stale_aux_fixture() -> AuxiliaryContextFixture:
    return AuxiliaryContextFixture(
        aux_refs=(
            EnhancedAuxAssetRef(
                kind="scene",
                asset_id=None,
                review_status=None,
                book_snapshot_id=None,
                stale=True,
                excluded=True,
                reason="fixture_stale_not_orm",
            ),
        ),
        warnings=("enhanced_aux_stale_fixture",),
        stale=True,
        missing=False,
        synthetic=True,
        non_production=True,
    )


def make_full_aux_fixture(*, extra_units: Sequence[WholeBookContextUnit] = ()) -> AuxiliaryContextFixture:
    return AuxiliaryContextFixture(
        aux_refs=(
            EnhancedAuxAssetRef(
                kind="reader_journey",
                asset_id=1,
                review_status="candidate",
                book_snapshot_id=None,
                stale=False,
                excluded=False,
                reason="fixture_aux_not_evidence",
            ),
        ),
        extra_units=tuple(extra_units),
        warnings=("enhanced_aux_fixture_injected",),
        missing=False,
        stale=False,
        synthetic=True,
        non_production=True,
    )


__all__ = [
    "AuxiliaryContextFixture",
    "AuxiliaryContextSource",
    "EmptyAuxiliaryContextSource",
    "FixtureAuxiliaryContextSource",
    "make_full_aux_fixture",
    "make_stale_aux_fixture",
]
