"""CreateMockWholeBookRun request/result contracts (Phase 2A-P).

Creation order is frozen. Failures before create must leave no Run/Stage/Artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Sequence

from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.product_contract.enums import WholeBookRunViewStatus
from app.narrative_core.run_shell_contract.mock_lab import MOCK_ENGINE_ID, MOCK_LAB_SOURCE


class MockProfile(StrEnum):
    DETERMINISTIC_MINIMAL = "deterministic_minimal"
    DETERMINISTIC_FULL = "deterministic_full"
    FAULT_INJECTION = "fault_injection"


CREATE_MOCK_RUN_PRECHECKS: tuple[str, ...] = (
    "authorize_mock_lab",
    "book_exists",
    "snapshot_exists",
    "snapshot_belongs_to_book",
    "snapshot_completed",
    "preflight_not_stale",
    "mode_valid",
    "modules_valid",
    "dependencies_resolvable",
    "mock_engine_available",
    "idempotency_key",
    "concurrency_limit",
    "no_conflicting_active_run",
    "request_excludes_full_body",
    "do_not_create_snapshot",
)

CREATE_MOCK_RUN_SEQUENCE: tuple[str, ...] = (
    "authorize",
    "validate_snapshot",
    "validate_request",
    "resolve_modules",
    "build_stage_plan",
    "reserve_mock_execution_slot",
    "create_analysis_run",
    "create_analysis_run_stages",
    "register_execution_task",
    "return_run_view",
)

# Metadata keys persisted via existing AnalysisRun config/metadata JSON (no new columns).
MOCK_RUN_METADATA_SCHEMA = "mock_whole_book_run_metadata"
MOCK_RUN_METADATA_VERSION = "1.0.0"

FORBIDDEN_CREATE_BODY_KEYS: frozenset[str] = frozenset(
    {
        "full_text",
        "fulltext",
        "book_text",
        "novel_text",
        "novel_body",
        "chapters_text",
        "paragraph_texts",
        "raw_book_content",
        "content_text",
        "prompt",
        "system_prompt",
    }
)


@dataclass(frozen=True, slots=True)
class CreateMockWholeBookRunRequest:
    book_id: int
    book_snapshot_id: int
    analysis_mode: WholeBookAnalysisMode
    requested_modules: tuple[WholeBookModuleKey, ...]
    configuration_fingerprint: str
    idempotency_key: str
    mock_profile: MockProfile
    requested_by: str
    preflight_fingerprint: str
    extra_payload_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.book_id <= 0 or self.book_snapshot_id <= 0:
            raise ValueError("book_id and book_snapshot_id must be positive")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key required")
        if not self.configuration_fingerprint.strip():
            raise ValueError("configuration_fingerprint required")
        if not self.preflight_fingerprint.strip():
            raise ValueError("preflight_fingerprint required")
        if not self.requested_modules:
            raise ValueError("requested_modules required")
        overlap = FORBIDDEN_CREATE_BODY_KEYS.intersection(self.extra_payload_keys)
        if overlap:
            raise ValueError(f"request must not include full body keys: {sorted(overlap)}")


@dataclass(frozen=True, slots=True)
class CreateMockWholeBookRunResult:
    run_id: int
    book_id: int
    book_snapshot_id: int
    status: WholeBookRunViewStatus
    analysis_mode: WholeBookAnalysisMode
    requested_modules: tuple[WholeBookModuleKey, ...]
    resolved_modules: tuple[WholeBookModuleKey, ...]
    stage_plan: tuple[str, ...]
    mock: bool
    non_production: bool
    created: bool
    duplicate_of_run_id: int | None
    created_at: str

    def __post_init__(self) -> None:
        if not self.mock or not self.non_production:
            raise ValueError("mock run result must be mock and non_production")
        if self.created and self.duplicate_of_run_id is not None:
            raise ValueError("created run cannot also be a duplicate")
        if not self.created and self.duplicate_of_run_id is None:
            raise ValueError("idempotent hit requires duplicate_of_run_id")


@dataclass(frozen=True, slots=True)
class MockRunPersistenceMetadata:
    """Frozen metadata shape stored in existing AnalysisRun metadata/config JSON."""

    schema: str = MOCK_RUN_METADATA_SCHEMA
    version: str = MOCK_RUN_METADATA_VERSION
    subject_type: str = "book"
    book_id: int = 0
    book_snapshot_id: int = 0
    run_scope: str = "whole_book"
    analysis_mode: str = ""
    requested_modules: tuple[str, ...] = ()
    resolved_modules: tuple[str, ...] = ()
    engine_id: str = MOCK_ENGINE_ID
    engine_version: str = ""
    configuration_fingerprint: str = ""
    mock: bool = True
    non_production: bool = True
    source: str = MOCK_LAB_SOURCE

    def __post_init__(self) -> None:
        if self.subject_type != "book":
            raise ValueError("subject_type must be book")
        if self.run_scope != "whole_book":
            raise ValueError("run_scope must be whole_book")
        if not self.mock or not self.non_production:
            raise ValueError("mock metadata must be mock/non_production")
        if self.source != MOCK_LAB_SOURCE:
            raise ValueError("source must be mock_lab")
        if self.engine_id != MOCK_ENGINE_ID:
            raise ValueError("engine_id must be mock engine")


@dataclass(frozen=True, slots=True)
class CreateMockRunValidationContext:
    """Inputs for pre-create checks (Agent M implements enforcement)."""

    lab_allowed: bool
    book_exists: bool
    snapshot_exists: bool
    snapshot_belongs_to_book: bool
    snapshot_completed: bool
    preflight_fresh: bool
    mode_valid: bool
    modules_valid: bool
    dependencies_resolvable: bool
    mock_engine_available: bool
    concurrency_ok: bool
    no_active_conflict: bool
    rejected_precheck: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


def first_failed_create_precheck(ctx: CreateMockRunValidationContext) -> str | None:
    checks: Sequence[tuple[str, bool]] = (
        ("authorize_mock_lab", ctx.lab_allowed),
        ("book_exists", ctx.book_exists),
        ("snapshot_exists", ctx.snapshot_exists),
        ("snapshot_belongs_to_book", ctx.snapshot_belongs_to_book),
        ("snapshot_completed", ctx.snapshot_completed),
        ("preflight_not_stale", ctx.preflight_fresh),
        ("mode_valid", ctx.mode_valid),
        ("modules_valid", ctx.modules_valid),
        ("dependencies_resolvable", ctx.dependencies_resolvable),
        ("mock_engine_available", ctx.mock_engine_available),
        ("concurrency_limit", ctx.concurrency_ok),
        ("no_conflicting_active_run", ctx.no_active_conflict),
    )
    for name, ok in checks:
        if not ok:
            return name
    return ctx.rejected_precheck
