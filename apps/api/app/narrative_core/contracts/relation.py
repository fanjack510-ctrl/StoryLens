"""Relation / Version / Evidence Protocol contracts (Agent F implements)."""

from __future__ import annotations

from typing import Any, Protocol


class NarrativeRelationService(Protocol):
    def create_candidate_relation(
        self,
        book_id: int,
        *,
        source_asset_id: int,
        target_asset_id: int,
        relation_type: str,
        summary: str = "",
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
        identity_fingerprint: str | None = None,
        **fields: Any,
    ) -> Any:
        """Create stable Relation + first candidate version. Endpoints are Asset ids."""

    def get_relation(self, relation_id: int) -> Any:
        ...

    def get_relation_versions(self, relation_id: int) -> list[Any]:
        ...

    def list_relations(
        self,
        book_id: int,
        *,
        lifecycle_status: str | None = None,
        source_asset_id: int | None = None,
        target_asset_id: int | None = None,
    ) -> list[Any]:
        ...

    def add_relation_version(
        self,
        relation_id: int,
        *,
        relation_type: str,
        review_status: str = "candidate",
        origin_type: str = "model",
        run_id: int | None = None,
        book_snapshot_id: int | None = None,
        **fields: Any,
    ) -> Any:
        ...

    def get_canonical_relation_version(self, relation_id: int) -> Any | None:
        ...

    def confirm_relation_version(
        self, relation_version_id: int, *, make_canonical: bool = True
    ) -> Any:
        ...

    def correct_relation(
        self,
        relation_id: int,
        *,
        based_on_version_id: int,
        summary: str = "",
        **fields: Any,
    ) -> Any:
        ...

    def reject_relation_version(self, relation_version_id: int) -> Any:
        ...

    def lock_relation(self, relation_id: int) -> Any:
        ...

    def unlock_relation(self, relation_id: int) -> Any:
        ...

    def mark_relation_stale(self, relation_id: int, *, reason: str) -> Any:
        ...

    def clear_relation_stale(self, relation_id: int) -> Any:
        ...

    def supersede_relation(
        self, relation_id: int, *, superseded_by_relation_id: int
    ) -> Any:
        ...

    def attach_relation_evidence(
        self, relation_version_id: int, **evidence_fields: Any
    ) -> Any:
        ...

    def validate_relation_evidence(self, evidence_id: int) -> bool:
        """Must reuse Phase 1A Snapshot capabilities — no second text-reader."""

    def list_relation_version_evidence(
        self, relation_version_id: int
    ) -> list[Any]:
        ...
