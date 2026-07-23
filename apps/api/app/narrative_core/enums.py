"""Frozen public enums for Narrative Intelligence Core (Phase 1P).

Agents must import these values; do not scatter string literals in services.
"""

from __future__ import annotations

from enum import StrEnum


class AnalysisScopeType(StrEnum):
    CHAPTER = "chapter"
    CHAPTER_RANGE = "chapter_range"
    BOOK = "book"


class SnapshotStatus(StrEnum):
    BUILDING = "building"
    COMPLETED = "completed"
    FAILED = "failed"
    # Invalid: completed snapshot whose referenced live book text drifted or
    # integrity validation failed. Not a retryable building state.
    INVALID = "invalid"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    """Narrative staged-run status constants (AnalysisRun.status string column).

    Not a DB enum — legacy scene-pipeline statuses continue to coexist as free
    strings (e.g. boundary_candidates_running). pause ≠ failed; interrupted ≠ failed.
    """

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisType(StrEnum):
    """Compatible + Phase 1 whole-book placeholders only.

    Do not expand with every future module here. Legacy 1.0.5 rows may have
    NULL analysis_type; treat NULL + task_type=scene_pipeline as chapter scene
    pipeline (see contract docs). Do not force backfill in Phase 1P.
    """

    SCENE_PIPELINE = "scene_pipeline"
    WHOLE_BOOK_NATIVE = "whole_book_native"
    WHOLE_BOOK_ENHANCED = "whole_book_enhanced"
