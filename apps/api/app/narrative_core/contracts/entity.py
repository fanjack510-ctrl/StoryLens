"""Entity / Alias Protocol contracts (Agent D implements)."""

from __future__ import annotations

from typing import Any, Protocol


class NarrativeEntityService(Protocol):
    def create_entity(
        self,
        book_id: int,
        *,
        entity_type: str,
        canonical_name: str,
        created_by: str | None = None,
    ) -> Any:
        """Create stable Entity identity. review/candidate does not live here."""

    def add_alias_candidate(
        self,
        entity_id: int,
        *,
        alias_text: str,
        alias_type: str = "display",
        source_run_id: int | None = None,
        source_snapshot_id: int | None = None,
    ) -> Any:
        """Model-discovered names become Alias candidates; never overwrite canonical_name."""

    def confirm_alias(self, alias_id: int) -> Any:
        ...

    def reject_alias(self, alias_id: int) -> Any:
        ...

    def lock_entity(self, entity_id: int) -> Any:
        ...

    def unlock_entity(self, entity_id: int) -> Any:
        ...

    def find_entity_by_alias(self, book_id: int, alias_text: str) -> Any | None:
        ...

    def merge_entities(self, survivor_id: int, absorbed_id: int) -> Any:
        """Frozen semantic only in Phase 1B-P — complex merge deferred to Agent D/Integration."""
