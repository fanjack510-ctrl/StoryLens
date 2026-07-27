"""Fake Private Whole-Book Engine (Phase 2B Agent P).

Deterministic, synthetic, non-production only.
Does not read real novel full text or produce real analysis conclusions.
Production loaders must reject this engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from app.narrative_core.enums import WholeBookModuleKey
from app.narrative_core.private_engine_contract.checkpoint import build_fake_checkpoint
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.manifest import (
    PRIVATE_ENGINE_PROTOCOL_ID,
    PrivateWholeBookEngineManifest,
    configuration_fingerprint_parts,
    fake_private_manifest,
)
from app.narrative_core.private_engine_contract.protocol import (
    PrivateEngineCheckpoint,
    PrivateEngineExecutionRequest,
    PrivateEngineExecutionResult,
    PrivateEngineHealth,
    assert_request_has_no_forbidden_fields,
)
from app.narrative_core.services.private_engine_signature import is_fake_or_test_engine_id

FAKE_PRIVATE_ENGINE_ID = "fake.signed.private_engine"
FAKE_PRIVATE_ENGINE_VERSION = "0.0.1-fake"
_SYNTHETIC = frozenset({"synthetic", "fake", "non_production", "test"})


def _empty_module_output(module_key: WholeBookModuleKey) -> dict[str, Any]:
    return {
        "module_key": module_key.value,
        "fake": True,
        "synthetic": True,
        "non_production": True,
        "status": "empty_ok",
        "items": [],
        "note": "fake_fixed_empty_result",
    }


def _fixed_module_output(module_key: WholeBookModuleKey) -> dict[str, Any]:
    return {
        "module_key": module_key.value,
        "fake": True,
        "synthetic": True,
        "non_production": True,
        "status": "fixed_test_result",
        "items": [
            {
                "id": f"fake-{module_key.value}-1",
                "title": f"[FAKE] {module_key.value}",
                "summary": "synthetic non-production fixture",
            }
        ],
    }


@dataclass
class FakePrivateWholeBookEngine:
    """Fake/test private engine. engine_id must contain fake/test."""

    manifest: PrivateWholeBookEngineManifest | None = None
    use_fixed_results: bool = True
    cancelled_refs: set[str] = field(default_factory=set)
    checkpoints: dict[str, PrivateEngineCheckpoint] = field(default_factory=dict)
    private: bool = False  # Contract-legal: private=false OR test_private via markers
    test_private: bool = True
    non_production: bool = True

    def __post_init__(self) -> None:
        if self.manifest is None:
            self.manifest = fake_private_manifest(
                engine_id=FAKE_PRIVATE_ENGINE_ID,
                signed=True,
                non_production=True,
            )
        assert self.manifest is not None
        if not is_fake_or_test_engine_id(self.manifest.engine_id):
            raise ValueError("FakePrivateWholeBookEngine engine_id must contain fake/test")
        if not self.non_production or not self.manifest.non_production:
            raise ValueError("FakePrivateWholeBookEngine requires non_production=true")
        if not (self.private is False or self.test_private is True):
            raise ValueError("Fake engine must use private=false or test_private=true")

    @property
    def engine_id(self) -> str:
        assert self.manifest is not None
        return self.manifest.engine_id

    @property
    def engine_version(self) -> str:
        assert self.manifest is not None
        return self.manifest.engine_version

    def validate_execution_request(self, request: PrivateEngineExecutionRequest) -> None:
        assert_request_has_no_forbidden_fields(request)
        if not request.context_bundle_ref.strip():
            raise private_engine_error(PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID)
        if request.book_snapshot_id <= 0:
            raise private_engine_error(PrivateEngineErrorCode.CONTEXT_BUNDLE_SNAPSHOT_MISMATCH)
        if not request.configuration_fingerprint.strip():
            raise private_engine_error(PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE)
        # Never accept full unbounded body fields — guarded by DTO; extra safety:
        for banned in ("full_text", "novel_body", "api_key", "credential"):
            if banned in request.provider_policy or banned in request.budget_policy:
                raise private_engine_error(PrivateEngineErrorCode.PROVIDER_POLICY_INVALID)

    def health_check(self) -> PrivateEngineHealth:
        # Must not execute novel analysis.
        return PrivateEngineHealth(
            engine_id=self.engine_id,
            healthy=True,
            status="ok",
            protocol_version=PRIVATE_ENGINE_PROTOCOL_ID,
            details=("fake", "synthetic", "no_novel_analysis", "non_production"),
        )

    def cancel(self, cancellation_ref: str) -> bool:
        self.cancelled_refs.add(cancellation_ref)
        return True

    def execute(self, request: PrivateEngineExecutionRequest) -> PrivateEngineExecutionResult:
        self.validate_execution_request(request)
        if request.cancellation_ref and request.cancellation_ref in self.cancelled_refs:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
        return self._build_result(request, status="completed")

    def resume(
        self,
        request: PrivateEngineExecutionRequest,
        checkpoint: PrivateEngineCheckpoint,
    ) -> PrivateEngineExecutionResult:
        self.validate_execution_request(request)
        if request.cancellation_ref and request.cancellation_ref in self.cancelled_refs:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
        if checkpoint.book_snapshot_id != request.book_snapshot_id:
            raise private_engine_error(PrivateEngineErrorCode.CONTEXT_BUNDLE_SNAPSHOT_MISMATCH)
        if checkpoint.configuration_fingerprint != request.configuration_fingerprint:
            raise private_engine_error(PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE)
        if (
            checkpoint.prompt_pack_id is not None
            and request.prompt_pack_ref
            and checkpoint.prompt_pack_id not in request.prompt_pack_ref
            and request.prompt_pack_ref != checkpoint.prompt_pack_id
        ):
            # Soft ref check; Runtime Adapter performs full Prompt Pack version checks.
            pass
        return self._build_result(request, status="resumed", checkpoint=checkpoint)

    def _build_result(
        self,
        request: PrivateEngineExecutionRequest,
        *,
        status: str,
        checkpoint: PrivateEngineCheckpoint | None = None,
    ) -> PrivateEngineExecutionResult:
        assert self.manifest is not None
        modules: dict[str, Any] = {}
        builder = _fixed_module_output if self.use_fixed_results else _empty_module_output
        keys = request.resolved_module_keys or request.requested_module_keys
        for key in keys:
            modules[key.value] = builder(key)

        fp_parts = configuration_fingerprint_parts(
            self.manifest,
            prompt_pack_hash=request.prompt_pack_ref,
        )
        _ = fp_parts
        cp = checkpoint or build_fake_checkpoint(
            book_snapshot_id=request.book_snapshot_id,
            configuration_fingerprint=request.configuration_fingerprint,
            stage_key=str(getattr(request.stage_key, "value", request.stage_key)),
            attempt=request.attempt,
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            context_bundle_hash=request.context_bundle_ref,
            prompt_pack_id=request.prompt_pack_ref,
            prompt_pack_version="0.0.1-fake",
        )
        self.checkpoints[request.context_bundle_ref] = cp
        return PrivateEngineExecutionResult(
            schema="storylens.private_engine.result",
            version="1.0.0",
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            stage_key=str(getattr(request.stage_key, "value", request.stage_key)),
            attempt=request.attempt,
            status=status,
            module_outputs=modules,
            evidence_candidates=(),
            asset_candidates=(),
            relation_candidates=(),
            conflict_candidates=(),
            checkpoint=cp,
            usage={
                "synthetic": True,
                "fake": True,
                "non_production": True,
                "provider_calls": 0,
            },
            warnings=("synthetic_fake_engine",),
            validation_summary={"accepted": False, "reason": "fake_synthetic_not_canonical"},
            generated_at=datetime(2026, 7, 23, 12, 0, 0),
        )

    def production_allowed(self) -> bool:
        return False
