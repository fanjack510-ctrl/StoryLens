"""Frozen error codes for Narrative Intelligence Core (Phase 1P)."""

from __future__ import annotations

from enum import StrEnum


class NarrativeCoreErrorCode(StrEnum):
    MIGRATION_CHECKSUM_MISMATCH = "MIGRATION_CHECKSUM_MISMATCH"
    MIGRATION_BASELINE_INVALID = "MIGRATION_BASELINE_INVALID"
    SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"
    SNAPSHOT_NOT_COMPLETED = "SNAPSHOT_NOT_COMPLETED"
    SNAPSHOT_BOOK_MISMATCH = "SNAPSHOT_BOOK_MISMATCH"
    SNAPSHOT_INTEGRITY_FAILED = "SNAPSHOT_INTEGRITY_FAILED"
    INVALID_RUN_SCOPE = "INVALID_RUN_SCOPE"
    BOOK_SCOPE_REQUIRES_SNAPSHOT = "BOOK_SCOPE_REQUIRES_SNAPSHOT"
    RANGE_SCOPE_REQUIRES_BOUNDS = "RANGE_SCOPE_REQUIRES_BOUNDS"
    RANGE_SCOPE_INVALID_ORDER = "RANGE_SCOPE_INVALID_ORDER"
    DUPLICATE_STAGE_KEY = "DUPLICATE_STAGE_KEY"
    INVALID_STAGE_TRANSITION = "INVALID_STAGE_TRANSITION"
    COMPLETED_STAGE_CANNOT_RETRY = "COMPLETED_STAGE_CANNOT_RETRY"


class NarrativeCoreError(Exception):
    """Typed error carrying a frozen NarrativeCoreErrorCode."""

    def __init__(self, code: NarrativeCoreErrorCode, message: str = "") -> None:
        self.code = code
        super().__init__(message or code.value)
