"""Asset / Version / Evidence Protocol contracts (Agent E implements)."""

from __future__ import annotations

from typing import Any, Protocol


class NarrativeAssetService(Protocol):
    def create_candidate_asset(
        self,
        book_id: int,
        *,
        asset_type: str,
        title: str,
        summary: str = "",
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
        stable_label: str | None = None,
        **fields: Any,
    ) -> Any:
        """Create stable Asset + first candidate version. Does not auto-canonical."""

    def add_asset_version(
        self,
        asset_id: int,
        *,
        asset_type: str,
        title: str,
        review_status: str = "candidate",
        origin_type: str = "model",
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
        **fields: Any,
    ) -> Any:
        ...

    def get_canonical_asset_version(self, asset_id: int) -> Any | None:
        ...

    def confirm_asset_version(self, asset_version_id: int, *, make_canonical: bool = True) -> Any:
        """confirmed may become canonical; rejected must not; locked Asset blocks model switch."""

    def correct_asset(
        self,
        asset_id: int,
        *,
        based_on_version_id: int,
        title: str,
        summary: str = "",
        **fields: Any,
    ) -> Any:
        """User correction creates a new corrected version — does not overwrite prior rows."""

    def reject_asset_version(self, asset_version_id: int) -> Any:
        ...

    def lock_asset(self, asset_id: int) -> Any:
        ...

    def unlock_asset(self, asset_id: int) -> Any:
        ...

    def mark_asset_stale(self, asset_id: int, *, reason: str) -> Any:
        ...

    def supersede_asset(self, asset_id: int, *, superseded_by_asset_id: int) -> Any:
        """Supersede stable identity — not the same as retaining an old version."""

    def attach_asset_evidence(self, asset_version_id: int, **evidence_fields: Any) -> Any:
        ...

    def validate_asset_evidence(self, evidence_id: int) -> bool:
        """Must reuse Phase 1A SnapshotValidationGateway / snapshot paragraph APIs."""
