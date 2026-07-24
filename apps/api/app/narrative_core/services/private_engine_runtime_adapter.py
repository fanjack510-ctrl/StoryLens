"""Private WholeBook Engine Runtime Adapter (Phase 2B Agent P).

Bridges Phase 1C WholeBook Engine Protocol surface concerns with
storylens.private_engine.v1 request/result DTOs.

Does not read ORM / License / Credential.
Does not write Narrative Assets or promote canonical.
Only executes FakePrivateWholeBookEngine in this phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.narrative_core.private_engine_contract.checkpoint import (
    CheckpointCompatibilityInput,
    assert_checkpoint_compatible,
)
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.manifest import (
    PRIVATE_ENGINE_PROTOCOL_ID,
    configuration_fingerprint_parts,
)
from app.narrative_core.private_engine_contract.prompt_pack import (
    PromptPackManifest,
    prompt_hash_fingerprint_part,
)
from app.narrative_core.private_engine_contract.protocol import (
    FORBIDDEN_REQUEST_FIELD_NAMES,
    PrivateEngineCheckpoint,
    PrivateEngineExecutionRequest,
    PrivateEngineExecutionResult,
    PrivateEngineHealth,
    assert_mapping_has_no_forbidden_keys,
    assert_request_has_no_forbidden_fields,
)
from app.narrative_core.services.fake_private_whole_book_engine import FakePrivateWholeBookEngine
from app.narrative_core.services.private_engine_manifest_loader import (
    DefaultPrivateWholeBookEngineLoader,
    PromptPackCompatibilityValidator,
    PromptPackManifestRepository,
)


def _guard_result_dto(result: PrivateEngineExecutionResult) -> PrivateEngineExecutionResult:
    """Public DTO guard — result must not carry secrets or become canonical."""

    assert_mapping_has_no_forbidden_keys(result.usage, label="usage")
    assert_mapping_has_no_forbidden_keys(result.validation_summary, label="validation_summary")
    for key in result.module_outputs:
        output = result.module_outputs[key]
        if isinstance(output, Mapping):
            assert_mapping_has_no_forbidden_keys(output, label=f"module_outputs.{key}")
    if result.validation_summary.get("canonical") is True:
        raise private_engine_error(
            PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID,
            detail_code="result_must_not_be_canonical",
        )
    return result


@dataclass
class PrivateWholeBookEngineRuntimeAdapter:
    """Connects public Protocol DTOs to Fake private engine runtime."""

    engine: FakePrivateWholeBookEngine
    loader: DefaultPrivateWholeBookEngineLoader | None = None
    prompt_pack_repository: PromptPackManifestRepository | None = None
    prompt_pack_validator: PromptPackCompatibilityValidator = field(
        default_factory=PromptPackCompatibilityValidator
    )
    prompt_pack: PromptPackManifest | None = None
    budget_guard: Any | None = None
    cancellation_tokens: dict[str, Any] = field(default_factory=dict)

    def validate_execution_request(self, request: PrivateEngineExecutionRequest) -> None:
        assert_request_has_no_forbidden_fields(request)
        if request.book_snapshot_id <= 0:
            raise private_engine_error(PrivateEngineErrorCode.CONTEXT_BUNDLE_SNAPSHOT_MISMATCH)
        if not request.context_bundle_ref.strip():
            raise private_engine_error(PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID)
        if not request.configuration_fingerprint.strip():
            raise private_engine_error(PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE)
        for banned in FORBIDDEN_REQUEST_FIELD_NAMES:
            if banned in request.provider_policy or banned in request.budget_policy:
                raise private_engine_error(PrivateEngineErrorCode.PROVIDER_POLICY_INVALID)
        self.engine.validate_execution_request(request)
        self._check_prompt_pack(request)
        self._propagate_cancel(request)
        self._check_budget(request)

    def translate_request(
        self,
        request: PrivateEngineExecutionRequest,
    ) -> PrivateEngineExecutionRequest:
        """Identity translate with fingerprint / prompt pack participation checks."""

        self.validate_execution_request(request)
        _ = self.build_configuration_fingerprint(request)
        return request

    def build_configuration_fingerprint(self, request: PrivateEngineExecutionRequest) -> str:
        manifest = self.engine.manifest
        assert manifest is not None
        prompt_hash = None
        pack = self._resolve_prompt_pack(request.prompt_pack_ref)
        if pack is not None:
            prompt_hash = pack.prompt_hash
        parts = list(
            configuration_fingerprint_parts(
                manifest,
                prompt_pack_hash=prompt_hash,
                quality_profile_key=str(request.provider_policy.get("quality_profile") or ""),
            )
        )
        if prompt_hash:
            parts.append(prompt_hash_fingerprint_part(prompt_hash))
        parts.append(f"snapshot={request.book_snapshot_id}")
        parts.append(f"context_ref={request.context_bundle_ref}")
        return "|".join(parts)

    def execute(self, request: PrivateEngineExecutionRequest) -> PrivateEngineExecutionResult:
        translated = self.translate_request(request)
        result = self.engine.execute(translated)
        return self.translate_result(result)

    def resume(
        self,
        request: PrivateEngineExecutionRequest,
        checkpoint: PrivateEngineCheckpoint,
    ) -> PrivateEngineExecutionResult:
        translated = self.translate_request(request)
        pack = self._resolve_prompt_pack(request.prompt_pack_ref)
        if pack is None:
            raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_NOT_FOUND)
        self.prompt_pack_validator.assert_compatible(
            pack,
            engine_version=self.engine.engine_version,
            module_keys=request.resolved_module_keys or request.requested_module_keys,
            for_resume=True,
            checkpoint_prompt_pack_id=checkpoint.prompt_pack_id,
            checkpoint_prompt_pack_version=checkpoint.prompt_pack_version,
        )
        assert_checkpoint_compatible(
            CheckpointCompatibilityInput(
                checkpoint=checkpoint,
                current_engine_id=self.engine.engine_id,
                current_engine_version=self.engine.engine_version,
                current_prompt_pack_id=pack.prompt_pack_id,
                current_prompt_pack_version=pack.prompt_pack_version,
                current_context_bundle_hash=request.context_bundle_ref,
                current_book_snapshot_id=request.book_snapshot_id,
                current_configuration_fingerprint=request.configuration_fingerprint,
            )
        )
        result = self.engine.resume(translated, checkpoint)
        return self.translate_result(result)

    def cancel(self, cancellation_ref: str) -> bool:
        token = self.cancellation_tokens.get(cancellation_ref)
        if token is not None and hasattr(token, "cancel"):
            token.cancel()
        return self.engine.cancel(cancellation_ref)

    def translate_result(self, result: PrivateEngineExecutionResult) -> PrivateEngineExecutionResult:
        guarded = _guard_result_dto(result)
        return PrivateEngineExecutionResult(
            schema=guarded.schema,
            version=guarded.version,
            engine_id=guarded.engine_id,
            engine_version=guarded.engine_version,
            stage_key=guarded.stage_key,
            attempt=guarded.attempt,
            status=guarded.status,
            module_outputs=dict(guarded.module_outputs),
            evidence_candidates=guarded.evidence_candidates,
            asset_candidates=(),
            relation_candidates=(),
            conflict_candidates=guarded.conflict_candidates,
            checkpoint=guarded.checkpoint,
            usage=dict(guarded.usage),
            warnings=tuple(list(guarded.warnings) + ["not_canonical", "no_asset_write"]),
            validation_summary={
                **dict(guarded.validation_summary),
                "accepted": False,
                "canonical": False,
                "asset_written": False,
            },
            generated_at=guarded.generated_at,
        )

    def health_check(self) -> PrivateEngineHealth:
        health = self.engine.health_check()
        if health.protocol_version != PRIVATE_ENGINE_PROTOCOL_ID:
            raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE)
        return health

    def register_cancellation_token(self, cancellation_ref: str, token: Any) -> None:
        self.cancellation_tokens[cancellation_ref] = token

    def _resolve_prompt_pack(self, prompt_pack_ref: str) -> PromptPackManifest | None:
        if self.prompt_pack is not None and (
            self.prompt_pack.prompt_pack_id == prompt_pack_ref
            or prompt_pack_ref in self.prompt_pack.prompt_pack_id
            or self.prompt_pack.prompt_pack_id in prompt_pack_ref
        ):
            return self.prompt_pack
        if self.prompt_pack_repository is not None:
            found = self.prompt_pack_repository.find_by_id(prompt_pack_ref)
            if found is not None:
                return found
            try:
                return self.prompt_pack_repository.load_manifest(prompt_pack_ref)
            except Exception:
                return None
        return self.prompt_pack

    def _check_prompt_pack(self, request: PrivateEngineExecutionRequest) -> None:
        pack = self._resolve_prompt_pack(request.prompt_pack_ref)
        if pack is None:
            if self.prompt_pack_repository is not None or self.prompt_pack is not None:
                raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_NOT_FOUND)
            return
        self.prompt_pack_validator.assert_compatible(
            pack,
            engine_version=self.engine.engine_version,
            module_keys=request.resolved_module_keys or request.requested_module_keys,
        )

    def _propagate_cancel(self, request: PrivateEngineExecutionRequest) -> None:
        ref = request.cancellation_ref
        if not ref:
            return
        if ref in self.engine.cancelled_refs:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
        token = self.cancellation_tokens.get(ref)
        if token is not None and hasattr(token, "is_cancelled") and token.is_cancelled():
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)

    def _check_budget(self, request: PrivateEngineExecutionRequest) -> None:
        if self.budget_guard is None:
            return
        stage = str(getattr(request.stage_key, "value", request.stage_key))
        estimated = int(request.budget_policy.get("estimated_tokens") or 0)
        if hasattr(self.budget_guard, "check_budget"):
            ok = self.budget_guard.check_budget(stage_key=stage, estimated_tokens=estimated)
            if not ok:
                raise private_engine_error(PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED)
