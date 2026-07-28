"""Whole-book contract v1 enums (frozen string values)."""

from __future__ import annotations

from enum import Enum


class WholeBookMode(str, Enum):
    whole_book_native = "whole_book_native"
    whole_book_enhanced = "whole_book_enhanced"


class ResultOrigin(str, Enum):
    formal = "formal"
    fixture = "fixture"


class SnapshotStatus(str, Enum):
    building = "building"
    completed = "completed"
    invalid = "invalid"


class WholeBookRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    recoverable = "recoverable"
    failed = "failed"
    completed = "completed"
    cancelled = "cancelled"


class WholeBookStageStatus(str, Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"
    cancelled = "cancelled"


class WholeBookUnitStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class EntityType(str, Enum):
    character = "character"
    location = "location"
    organization = "organization"
    object = "object"
    concept = "concept"


class ArtifactState(str, Enum):
    candidate = "candidate"
    confirmed = "confirmed"
    rejected = "rejected"
    superseded = "superseded"


class EvidenceState(str, Enum):
    valid = "valid"
    stale = "stale"
    unresolved = "unresolved"


class ConflictStatus(str, Enum):
    open = "open"
    resolved_keep_confirmed = "resolved_keep_confirmed"
    resolved_accept_proposal = "resolved_accept_proposal"
    resolved_merge = "resolved_merge"
    dismissed = "dismissed"


class OverviewClaimAvailability(str, Enum):
    available = "available"
    unavailable = "unavailable"
    insufficient_evidence = "insufficient_evidence"


class NarrativeRefKind(str, Enum):
    entity = "entity"
    asset = "asset"


class EngineProposalDecision(str, Enum):
    replace_candidate = "replace_candidate"
    create_conflict = "create_conflict"
    ignore_identical = "ignore_identical"
    reject_invalid = "reject_invalid"


ENUM_NAMES_V1: tuple[str, ...] = (
    "WholeBookMode",
    "ResultOrigin",
    "SnapshotStatus",
    "WholeBookRunStatus",
    "WholeBookStageStatus",
    "WholeBookUnitStatus",
    "EntityType",
    "ArtifactState",
    "EvidenceState",
    "ConflictStatus",
    "OverviewClaimAvailability",
    "NarrativeRefKind",
)
