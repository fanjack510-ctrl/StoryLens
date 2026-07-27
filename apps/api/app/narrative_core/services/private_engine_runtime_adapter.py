"""Private WholeBook Engine Runtime Adapter (Phase 2B Agent P / 2B-R Agent S).

Bridges Phase 1C WholeBook Engine Protocol surface concerns with
storylens.private_engine.v1 request/result DTOs.

Does not read ORM / License / Credential.
Does not write Narrative Assets or promote canonical.
Executes FakePrivateWholeBookEngine by default; Lab/dev may adapt private
package entry when installed (shell-only until Agent T modules land).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
    try_import_private_engine_entry,
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


def _coerce_private_entry_result(
    raw: Mapping[str, Any],
    *,
    engine_id: str,
    engine_version: str,
) -> PrivateEngineExecutionResult:
    generated = raw.get("generated_at")
    if isinstance(generated, str):
        try:
            generated_at = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        except ValueError:
            generated_at = datetime(2026, 7, 23, 0, 0, 0)
    elif isinstance(generated, datetime):
        generated_at = generated
    else:
        generated_at = datetime(2026, 7, 23, 0, 0, 0)
    return PrivateEngineExecutionResult(
        schema=str(raw.get("schema") or "storylens.private_engine.result.v1"),
        version=str(raw.get("version") or "0.1.0-dev"),
        engine_id=str(raw.get("engine_id") or engine_id),
        engine_version=str(raw.get("engine_version") or engine_version),
        stage_key=str(raw.get("stage_key") or ""),
        attempt=int(raw.get("attempt") or 0),
        status=str(raw.get("status") or "modules_not_implemented"),
        module_outputs=dict(raw.get("module_outputs") or {}),
        evidence_candidates=tuple(raw.get("evidence_candidates") or ()),
        asset_candidates=tuple(raw.get("asset_candidates") or ()),
        relation_candidates=tuple(raw.get("relation_candidates") or ()),
        conflict_candidates=tuple(raw.get("conflict_candidates") or ()),
        checkpoint=raw.get("checkpoint"),
        usage=dict(raw.get("usage") or {}),
        warnings=tuple(raw.get("warnings") or ()),
        validation_summary=dict(raw.get("validation_summary") or {}),
        generated_at=generated_at,
    )


@dataclass
class PrivateWholeBookEngineRuntimeAdapter:
    """Connects public Protocol DTOs to Fake or private-package engine runtime."""

    engine: FakePrivateWholeBookEngine | Any
    loader: DefaultPrivateWholeBookEngineLoader | None = None
    prompt_pack_repository: PromptPackManifestRepository | None = None
    prompt_pack_validator: PromptPackCompatibilityValidator = field(
        default_factory=PromptPackCompatibilityValidator
    )
    prompt_pack: PromptPackManifest | None = None
    budget_guard: Any | None = None
    cancellation_tokens: dict[str, Any] = field(default_factory=dict)
    private_package_entry: Any | None = None

    @classmethod
    def for_lab_private_package(
        cls,
        *,
        fallback_engine: FakePrivateWholeBookEngine | None = None,
        **kwargs: Any,
    ) -> "PrivateWholeBookEngineRuntimeAdapter":
        """Build adapter preferring installed private package entry (Lab/dev)."""
        entry = try_import_private_engine_entry()
        engine = entry if entry is not None else (fallback_engine or FakePrivateWholeBookEngine())
        return cls(engine=engine, private_package_entry=entry, **kwargs)

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
        if hasattr(self.engine, "validate_execution_request"):
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
        engine_id = str(getattr(self.engine, "engine_id", "unknown"))
        engine_version = str(getattr(self.engine, "engine_version", "0"))
        prompt_hash = None
        pack = self._resolve_prompt_pack(request.prompt_pack_ref)
        if pack is not None:
            prompt_hash = pack.prompt_hash
        manifest = getattr(self.engine, "manifest", None)
        if manifest is not None:
            parts = list(
                configuration_fingerprint_parts(
                    manifest,
                    prompt_pack_hash=prompt_hash,
                    quality_profile_key=str(request.provider_policy.get("quality_profile") or ""),
                )
            )
        else:
            parts = [
                f"engine={engine_id}@{engine_version}",
                f"quality={request.provider_policy.get('quality_profile') or ''}",
            ]
        if prompt_hash:
            parts.append(prompt_hash_fingerprint_part(prompt_hash))
        parts.append(f"snapshot={request.book_snapshot_id}")
        parts.append(f"context_ref={request.context_bundle_ref}")
        return "|".join(parts)

    def execute(self, request: PrivateEngineExecutionRequest) -> PrivateEngineExecutionResult:
        translated = self.translate_request(request)
        raw = self.engine.execute(translated)
        if isinstance(raw, PrivateEngineExecutionResult):
            return self.translate_result(raw)
        if isinstance(raw, Mapping):
            coerced = _coerce_private_entry_result(
                raw,
                engine_id=str(getattr(self.engine, "engine_id", "private")),
                engine_version=str(getattr(self.engine, "engine_version", "0")),
            )
            return self.translate_result(coerced)
        raise private_engine_error(
            PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID,
            detail_code="engine_result_type_invalid",
        )

    def resume(
        self,
        request: PrivateEngineExecutionRequest,
        checkpoint: PrivateEngineCheckpoint,
    ) -> PrivateEngineExecutionResult:
        translated = self.translate_request(request)
        pack = self._resolve_prompt_pack(request.prompt_pack_ref)
        if pack is None:
            raise private_engine_error(PrivateEngineErrorCode.PROMPT_PACK_NOT_FOUND)
        engine_version = str(getattr(self.engine, "engine_version", ""))
        self.prompt_pack_validator.assert_compatible(
            pack,
            engine_version=engine_version,
            module_keys=request.resolved_module_keys or request.requested_module_keys,
            for_resume=True,
            checkpoint_prompt_pack_id=checkpoint.prompt_pack_id,
            checkpoint_prompt_pack_version=checkpoint.prompt_pack_version,
        )
        assert_checkpoint_compatible(
            CheckpointCompatibilityInput(
                checkpoint=checkpoint,
                current_engine_id=str(getattr(self.engine, "engine_id", "")),
                current_engine_version=engine_version,
                current_prompt_pack_id=pack.prompt_pack_id,
                current_prompt_pack_version=pack.prompt_pack_version,
                current_context_bundle_hash=request.context_bundle_ref,
                current_book_snapshot_id=request.book_snapshot_id,
                current_configuration_fingerprint=request.configuration_fingerprint,
            )
        )
        raw = self.engine.resume(translated, checkpoint)
        if isinstance(raw, PrivateEngineExecutionResult):
            return self.translate_result(raw)
        if isinstance(raw, Mapping):
            coerced = _coerce_private_entry_result(
                raw,
                engine_id=str(getattr(self.engine, "engine_id", "private")),
                engine_version=engine_version,
            )
            return self.translate_result(coerced)
        raise private_engine_error(
            PrivateEngineErrorCode.MODULE_OUTPUT_SCHEMA_INVALID,
            detail_code="engine_result_type_invalid",
        )

    def cancel(self, cancellation_ref: str) -> bool:
        token = self.cancellation_tokens.get(cancellation_ref)
        if token is not None and hasattr(token, "cancel"):
            token.cancel()
        return bool(self.engine.cancel(cancellation_ref))

    def translate_result(self, result: PrivateEngineExecutionResult) -> PrivateEngineExecutionResult:
        """Guard secrets/canonical flags while preserving candidate payloads for persistence.

        CHG-052: must not unconditionally clear asset_candidates / relation_candidates.
        Canonical / auto-write still forbidden — ModuleCandidateBuilder + Phase1B sink only.
        """

        guarded = _guard_result_dto(result)
        outputs = dict(guarded.module_outputs)
        assets = tuple(guarded.asset_candidates or ())
        relations = tuple(guarded.relation_candidates or ())
        if not assets and isinstance(outputs.get("asset_candidates"), (list, tuple)):
            assets = tuple(outputs.get("asset_candidates") or ())
        if not relations and isinstance(outputs.get("relation_candidates"), (list, tuple)):
            relations = tuple(outputs.get("relation_candidates") or ())
        warnings = list(guarded.warnings or ())
        if "not_canonical" not in warnings:
            warnings.append("not_canonical")
        summary = dict(guarded.validation_summary or {})
        summary["canonical"] = False
        # Do not force accepted=False here — DefaultModuleOutputValidator is authoritative.
        summary.setdefault("asset_written", False)
        return PrivateEngineExecutionResult(
            schema=guarded.schema,
            version=guarded.version,
            engine_id=guarded.engine_id,
            engine_version=guarded.engine_version,
            stage_key=guarded.stage_key,
            attempt=guarded.attempt,
            status=guarded.status,
            module_outputs=outputs,
            evidence_candidates=guarded.evidence_candidates,
            asset_candidates=assets,
            relation_candidates=relations,
            conflict_candidates=guarded.conflict_candidates,
            checkpoint=guarded.checkpoint,
            usage=dict(guarded.usage),
            warnings=tuple(warnings),
            validation_summary=summary,
            generated_at=guarded.generated_at,
        )

    def health_check(self) -> PrivateEngineHealth:
        health = self.engine.health_check()
        if isinstance(health, PrivateEngineHealth):
            if health.protocol_version != PRIVATE_ENGINE_PROTOCOL_ID:
                raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE)
            return health
        if isinstance(health, Mapping):
            return PrivateEngineHealth(
                engine_id=str(health.get("engine_id") or getattr(self.engine, "engine_id", "")),
                healthy=bool(health.get("healthy", True)),
                status=str(health.get("status") or "ok"),
                protocol_version=str(health.get("protocol_version") or PRIVATE_ENGINE_PROTOCOL_ID),
                details=tuple(health.get("details") or ()),
            )
        raise private_engine_error(PrivateEngineErrorCode.PRIVATE_ENGINE_PROTOCOL_INCOMPATIBLE)

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
            engine_version=str(getattr(self.engine, "engine_version", "")),
            module_keys=request.resolved_module_keys or request.requested_module_keys,
        )

    def _propagate_cancel(self, request: PrivateEngineExecutionRequest) -> None:
        ref = request.cancellation_ref
        if not ref:
            return
        cancelled_refs = getattr(self.engine, "cancelled_refs", None)
        if cancelled_refs is not None and ref in cancelled_refs:
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
