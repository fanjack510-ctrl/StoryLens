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

    def get_entity(self, entity_id: int) -> Any:
        ...

    def list_entities(
        self,
        book_id: int,
        *,
        entity_type: str | None = None,
        lifecycle_status: str | None = None,
        include_inactive: bool = False,
    ) -> list[Any]:
        ...

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

    def list_entity_aliases(self, entity_id: int) -> list[Any]:
        ...

    def confirm_alias(self, alias_id: int) -> Any:
        ...

    def reject_alias(self, alias_id: int) -> Any:
        ...

    def lock_entity(self, entity_id: int) -> Any:
        ...

    def unlock_entity(self, entity_id: int) -> Any:
        ...

    def archive_entity(self, entity_id: int) -> Any:
        ...

    def supersede_entity(
        self, entity_id: int, *, superseded_by_entity_id: int | None = None
    ) -> Any:
        ...

    def find_entity_by_alias(self, book_id: int, alias_text: str) -> Any | None:
        ...

    def merge_entities(
        self,
        source_entity_id: int,
        target_entity_id: int,
        *,
        actor: str = "user",
    ) -> Any:
        """Merge source identity into target; source becomes superseded."""
