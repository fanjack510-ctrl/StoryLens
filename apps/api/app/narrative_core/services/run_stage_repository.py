"""SQLAlchemy repository for AnalysisRunStage rows (Agent B)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AnalysisRunStage, utc_now
from app.narrative_core.enums import StageStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.stage_transitions import (
    is_allowed_stage_transition,
    is_terminal_stage_status,
)

CHECKPOINT_SCHEMA = "narrative_run_stage_checkpoint"
CHECKPOINT_VERSION = "1"

_TERMINAL_FOR_COMPLETED_AT = frozenset(
    {
        StageStatus.COMPLETED,
        StageStatus.SKIPPED,
        StageStatus.CANCELLED,
    }
)

_ACCUMULATE_FIELDS = frozenset({"token_input", "token_output", "cost"})

# CHG-058: checkpoint namespaces that must merge rather than wholesale replace.
CHECKPOINT_MERGE_NAMESPACES = frozenset(
    {
        "provider_attempts",
        "pipeline_diagnostics",
        "persistence_summary",
        "result_projection",
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_checkpoint_dict(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    text = str(raw).strip() or "{}"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def merge_checkpoint_namespaces(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
    *,
    append_provider_attempt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge checkpoint payloads preserving provider_attempts append-only list.

    pipeline_diagnostics / persistence_summary / result_projection update their
    own keys without wiping sibling namespaces.
    """

    merged: dict[str, Any] = dict(existing or {})
    payload = dict(incoming or {})

    # Append-only provider attempts (explicit single attempt and/or list).
    attempts: list[Any] = list(merged.get("provider_attempts") or [])
    if append_provider_attempt is not None:
        attempts.append(dict(append_provider_attempt))
    incoming_attempts = payload.pop("provider_attempts", None)
    if isinstance(incoming_attempts, list):
        for item in incoming_attempts:
            if isinstance(item, Mapping):
                attempts.append(dict(item))
            else:
                attempts.append(item)
    elif isinstance(incoming_attempts, Mapping):
        attempts.append(dict(incoming_attempts))

    for key in ("pipeline_diagnostics", "persistence_summary", "result_projection"):
        if key not in payload:
            continue
        value = payload.pop(key)
        if isinstance(value, Mapping):
            base = dict(merged.get(key) or {}) if isinstance(merged.get(key), Mapping) else {}
            base.update(dict(value))
            merged[key] = base
        else:
            merged[key] = value

    # Remaining top-level keys overwrite (schema/version/stage_key/etc.).
    for key, value in payload.items():
        if key in CHECKPOINT_MERGE_NAMESPACES:
            continue
        merged[key] = value

    if attempts:
        merged["provider_attempts"] = attempts
    elif "provider_attempts" not in merged:
        # Keep empty list absent unless previously present.
        pass
    return merged


def validate_checkpoint_payload(payload: dict[str, Any] | str | None) -> str:
    """Ensure checkpoint_json includes schema/version and return canonical JSON text."""
    if payload is None:
        data: dict[str, Any] = {}
    elif isinstance(payload, str):
        raw = payload.strip() or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                f"checkpoint_json is not valid JSON: {exc}",
            ) from exc
        if not isinstance(parsed, dict):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                "checkpoint_json must be a JSON object",
            )
        data = parsed
    elif isinstance(payload, dict):
        data = dict(payload)
    else:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
            "checkpoint_json must be a dict or JSON string",
        )

    if "schema" in data or "checkpoint_schema" in data:
        schema = data.get("schema", data.get("checkpoint_schema"))
        if not isinstance(schema, str) or not schema.strip():
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                "checkpoint_json.schema is required",
            )
    else:
        schema = CHECKPOINT_SCHEMA

    if "version" in data or "checkpoint_version" in data:
        version = data.get("version", data.get("checkpoint_version"))
        if not isinstance(version, str) or not version.strip():
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                "checkpoint_json.version is required",
            )
    else:
        version = CHECKPOINT_VERSION

    data["schema"] = schema
    data["version"] = str(version)
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class RunStageRepository:
    """Persist AnalysisRunStage rows; enforces unique stage_key and transition matrix."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_run_stages(self, run_id: int) -> Sequence[AnalysisRunStage]:
        rows = self._session.scalars(
            select(AnalysisRunStage)
            .where(AnalysisRunStage.run_id == run_id)
            .order_by(AnalysisRunStage.stage_order.asc(), AnalysisRunStage.id.asc())
        ).all()
        return list(rows)

    def get_stage(self, run_id: int, stage_key: str) -> AnalysisRunStage | None:
        return self._session.scalar(
            select(AnalysisRunStage).where(
                AnalysisRunStage.run_id == run_id,
                AnalysisRunStage.stage_key == stage_key,
            )
        )

    def initialize_run_stages(
        self, run_id: int, stage_keys: Sequence[str]
    ) -> Sequence[AnalysisRunStage]:
        """Idempotent stage creation. stage_order is stable (0..n-1)."""
        keys = [str(k).strip() for k in stage_keys]
        if not keys:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                "stage_keys must not be empty",
            )
        if any(not k for k in keys):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                "stage_key must be non-empty",
            )
        if len(keys) != len(set(keys)):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.DUPLICATE_STAGE_KEY,
                "duplicate stage_key in initialize_run_stages input",
            )

        existing = list(self.get_run_stages(run_id))
        if existing:
            existing_keys = [row.stage_key for row in existing]
            if existing_keys == keys:
                return existing
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.DUPLICATE_STAGE_KEY,
                "run stages already initialized with a different stage_key sequence",
            )

        now = utc_now()
        created: list[AnalysisRunStage] = []
        for order, key in enumerate(keys):
            created.append(
                AnalysisRunStage(
                    run_id=run_id,
                    stage_key=key,
                    stage_order=order,
                    status=StageStatus.PENDING.value,
                    input_fingerprint="",
                    output_artifact_id=None,
                    checkpoint_json=validate_checkpoint_payload(
                        {"schema": CHECKPOINT_SCHEMA, "version": CHECKPOINT_VERSION}
                    ),
                    attempt_count=0,
                    token_input=0,
                    token_output=0,
                    cost=0.0,
                    started_at=None,
                    completed_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        try:
            self._session.add_all(created)
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.DUPLICATE_STAGE_KEY,
                f"duplicate stage_key for run_id={run_id}",
            ) from exc
        return list(self.get_run_stages(run_id))

    def transition_stage(
        self,
        run_id: int,
        stage_key: str,
        target_status: StageStatus | str,
        **fields: Any,
    ) -> AnalysisRunStage:
        """Apply a single allowed status transition inside the current session transaction."""
        target = StageStatus(target_status)
        stage = self.get_stage(run_id, stage_key)
        if stage is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                f"stage {stage_key!r} not found for run_id={run_id}",
            )

        current = StageStatus(stage.status)
        if current == StageStatus.COMPLETED and target != StageStatus.COMPLETED:
            # Error writes must never overwrite a completed stage.
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.COMPLETED_STAGE_CANNOT_RETRY
                if target == StageStatus.RUNNING
                else NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                f"completed stage cannot transition to {target.value}",
            )

        if not is_allowed_stage_transition(current, target):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                f"illegal transition {current.value} → {target.value} for stage {stage_key!r}",
            )

        accumulate = bool(fields.pop("accumulate", True))
        bump_attempt = bool(fields.pop("bump_attempt_count", False))
        checkpoint = fields.pop("checkpoint_json", fields.pop("checkpoint", None))
        replace_tokens = bool(fields.pop("replace_tokens", False))

        # Retry path: failed → running must increment attempt_count.
        if current == StageStatus.FAILED and target == StageStatus.RUNNING:
            bump_attempt = True

        if bump_attempt:
            stage.attempt_count = int(stage.attempt_count) + 1

        if target == StageStatus.RUNNING and stage.started_at is None:
            stage.started_at = _utcnow()
            if stage.attempt_count == 0:
                stage.attempt_count = 1

        if checkpoint is not None:
            stage.checkpoint_json = validate_checkpoint_payload(checkpoint)

        for key, value in fields.items():
            if key in _ACCUMULATE_FIELDS and accumulate and not replace_tokens:
                current_value = getattr(stage, key)
                if key == "cost":
                    setattr(stage, key, float(current_value or 0) + float(value or 0))
                else:
                    setattr(stage, key, int(current_value or 0) + int(value or 0))
            elif hasattr(stage, key):
                setattr(stage, key, value)

        stage.status = target.value
        stage.updated_at = _utcnow()

        if target in _TERMINAL_FOR_COMPLETED_AT:
            stage.completed_at = stage.completed_at or _utcnow()
        elif target in (StageStatus.RUNNING, StageStatus.PAUSED, StageStatus.INTERRUPTED):
            # Non-terminal / resumable states must not carry a terminal completed_at.
            stage.completed_at = None
        elif target == StageStatus.FAILED:
            # Failed is retryable — do not treat as permanent terminal completed_at.
            stage.completed_at = None

        # Never leave error fields on completed stages (completed cannot receive errors).
        if is_terminal_stage_status(target) and target == StageStatus.COMPLETED:
            if "error_code" not in fields:
                stage.error_code = None
            if "error_message" not in fields:
                stage.error_message = None

        self._session.flush()
        return stage

    def write_checkpoint(
        self,
        run_id: int,
        stage_key: str,
        checkpoint: dict[str, Any] | str,
        *,
        replace: bool = False,
        append_provider_attempt: Mapping[str, Any] | None = None,
        **accumulate_fields: Any,
    ) -> AnalysisRunStage:
        """Write a verifiable checkpoint without requiring a status change.

        By default merges into existing checkpoint_json namespaces so that
        ``provider_attempts`` appends and ``pipeline_diagnostics`` updates do
        not wipe each other (CHG-058). Pass ``replace=True`` for legacy full
        overwrite behavior.
        """
        stage = self.get_stage(run_id, stage_key)
        if stage is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_STAGE_TRANSITION,
                f"stage {stage_key!r} not found for run_id={run_id}",
            )
        if StageStatus(stage.status) == StageStatus.COMPLETED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.COMPLETED_STAGE_CANNOT_RETRY,
                "cannot overwrite checkpoint on completed stage",
            )
        if replace:
            stage.checkpoint_json = validate_checkpoint_payload(checkpoint)
        else:
            existing = _load_checkpoint_dict(stage.checkpoint_json)
            if isinstance(checkpoint, str):
                incoming = _load_checkpoint_dict(checkpoint)
            else:
                incoming = dict(checkpoint or {})
            merged = merge_checkpoint_namespaces(
                existing,
                incoming,
                append_provider_attempt=append_provider_attempt,
            )
            stage.checkpoint_json = validate_checkpoint_payload(merged)
        for key, value in accumulate_fields.items():
            if key in _ACCUMULATE_FIELDS:
                current_value = getattr(stage, key)
                if key == "cost":
                    setattr(stage, key, float(current_value or 0) + float(value or 0))
                else:
                    setattr(stage, key, int(current_value or 0) + int(value or 0))
        stage.updated_at = _utcnow()
        self._session.flush()
        return stage
