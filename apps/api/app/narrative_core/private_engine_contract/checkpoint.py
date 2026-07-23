"""Private Engine Checkpoint compatibility contract (Phase 2B-P)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.manifest import PRIVATE_ENGINE_PROTOCOL_ID
from app.narrative_core.private_engine_contract.protocol import PrivateEngineCheckpoint

# Re-export canonical checkpoint DTO.
__all__ = [
    "CHECKPOINT_REJECT_REASONS",
    "CheckpointCompatibilityInput",
    "PrivateEngineCheckpoint",
    "assert_checkpoint_compatible",
    "build_fake_checkpoint",
]

CHECKPOINT_REJECT_REASONS: frozenset[str] = frozenset(
    {
        "engine_version_incompatible",
        "prompt_pack_incompatible",
        "context_bundle_changed",
        "snapshot_changed",
        "configuration_changed",
        "integrity_failed",
        "module_migration_missing",
    }
)


@dataclass(frozen=True, slots=True)
class CheckpointCompatibilityInput:
    checkpoint: PrivateEngineCheckpoint
    current_engine_id: str
    current_engine_version: str
    current_prompt_pack_id: str | None
    current_prompt_pack_version: str | None
    current_context_bundle_hash: str | None
    current_book_snapshot_id: int
    current_configuration_fingerprint: str
    module_spec_changed: bool = False
    module_migration_available: bool = False
    integrity_ok: bool = True


def assert_checkpoint_compatible(inp: CheckpointCompatibilityInput) -> None:
    """Reject incompatible checkpoints — never silently continue with new prompt."""

    cp = inp.checkpoint
    if cp.engine_id != inp.current_engine_id or cp.engine_version != inp.current_engine_version:
        raise private_engine_error(PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE)
    if (
        cp.prompt_pack_id is not None
        and inp.current_prompt_pack_id is not None
        and (
            cp.prompt_pack_id != inp.current_prompt_pack_id
            or cp.prompt_pack_version != inp.current_prompt_pack_version
        )
    ):
        raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE)
    if (
        cp.context_bundle_hash is not None
        and inp.current_context_bundle_hash is not None
        and cp.context_bundle_hash != inp.current_context_bundle_hash
    ):
        raise private_engine_error(PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE)
    if cp.book_snapshot_id != inp.current_book_snapshot_id:
        raise private_engine_error(PrivateEngineErrorCode.CONTEXT_BUNDLE_SNAPSHOT_MISMATCH)
    if cp.configuration_fingerprint != inp.current_configuration_fingerprint:
        raise private_engine_error(PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE)
    if not inp.integrity_ok:
        raise private_engine_error(PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE)
    if inp.module_spec_changed and not inp.module_migration_available:
        raise private_engine_error(PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE)


def build_fake_checkpoint(
    *,
    book_snapshot_id: int,
    configuration_fingerprint: str,
    stage_key: str | None = "analyze_structure",
    attempt: int = 0,
    prompt_pack_id: str | None = "fake.prompt_pack.first_four",
    prompt_pack_version: str | None = "0.0.1-fake",
    engine_id: str = "fake.signed.private_engine",
    engine_version: str = "0.0.1-fake",
    context_bundle_hash: str | None = "fake-bundle-hash",
    usage: Mapping[str, Any] | None = None,
) -> PrivateEngineCheckpoint:
    return PrivateEngineCheckpoint(
        protocol_version=PRIVATE_ENGINE_PROTOCOL_ID,
        engine_id=engine_id,
        engine_version=engine_version,
        module_key="book_overview",
        module_version="1.0.0",
        stage_key=stage_key,
        attempt=attempt,
        prompt_pack_id=prompt_pack_id,
        prompt_pack_version=prompt_pack_version,
        provider_policy_key="fake",
        quality_profile="balanced",
        context_bundle_hash=context_bundle_hash,
        configuration_fingerprint=configuration_fingerprint,
        book_snapshot_id=book_snapshot_id,
        completed_units=(),
        pending_units=("unit:1",),
        output_fingerprints=(),
        usage=dict(usage or {"synthetic": True}),
        integrity_hash="fake-integrity-hash",
    )
