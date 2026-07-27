"""Book snapshot Protocols (Agent A implements; Agent B consumes gateway only)."""

from __future__ import annotations

from typing import Any, Protocol


class BookSnapshotRepository(Protocol):
    def create_snapshot_record(self, book_id: int, content_hash: str, **fields: Any) -> Any:
        ...

    def add_snapshot_chapter(self, snapshot_id: int, **fields: Any) -> Any:
        ...

    def add_snapshot_paragraph(self, snapshot_id: int, snapshot_chapter_id: int, **fields: Any) -> Any:
        ...

    def get_snapshot(self, snapshot_id: int) -> Any | None:
        ...

    def find_completed_snapshot(self, book_id: int, content_hash: str) -> Any | None:
        ...

    def validate_completed_snapshot(self, snapshot_id: int) -> bool:
        ...

    def mark_snapshot_completed(self, snapshot_id: int) -> Any:
        ...

    def mark_snapshot_failed(
        self,
        snapshot_id: int,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> Any:
        ...


class BookSnapshotService(Protocol):
    def create_or_reuse_snapshot(self, book_id: int) -> Any:
        """Create BUILDING snapshot or reuse COMPLETED for same content_hash."""

    def validate_snapshot(self, snapshot_id: int) -> bool:
        ...

    def get_snapshot_paragraph_text(self, snapshot_paragraph_id: int) -> str:
        ...


class SnapshotValidationGateway(Protocol):
    """Minimal surface Agent B may call — do not reimplement snapshot logic in B."""

    def get_completed_snapshot(self, snapshot_id: int) -> Any:
        ...

    def validate_snapshot_for_book(self, snapshot_id: int, book_id: int) -> bool:
        ...
