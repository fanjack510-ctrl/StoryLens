"""WholeBookModuleRunner Protocol + Fake runner (Phase 2B-P).

Runner forbids ORM / License / Credential access; only Provider Gateway.
No confirm / lock / canonical. Supports cancel / budget; binds prompt pack version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol, runtime_checkable

from app.narrative_core.enums import WholeBookModuleKey
from app.narrative_core.private_engine_contract.checkpoint import (
    PrivateEngineCheckpoint,
    build_fake_checkpoint,
)
from app.narrative_core.private_engine_contract.evidence import (
    EvidenceCandidate,
    fake_evidence_candidates,
)
from app.narrative_core.private_engine_contract.module_spec import get_module_spec
from app.narrative_core.private_engine_contract.prompt_pack import FakePromptPackManifest
from app.narrative_core.private_engine_contract.provider_gateway import (
    FakeProviderGateway,
    WholeBookProviderGateway,
)
from app.narrative_core.private_engine_contract.protocol import (
    PRIVATE_ENGINE_PROTOCOL_ID,
    PrivateEngineExecutionRequest,
    PrivateEngineExecutionResult,
)
from app.narrative_core.private_engine_contract.validation import (
    ModuleOutputValidationReport,
    FakeModuleOutputValidator,
)

MODULE_RUNNER_PROTOCOL_METHODS: tuple[str, ...] = (
    "validate_request",
    "prepare_context",
    "execute",
    "validate_output",
    "collect_evidence",
    "build_candidates",
    "build_checkpoint",
    "resume",
    "health_check",
)

RUNNER_FORBIDDEN_CAPABILITIES: frozenset[str] = frozenset(
    {
        "orm_access",
        "license_parse",
        "credential_read",
        "auto_confirm",
        "auto_lock",
        "canonical_overwrite",
        "direct_provider_http",
    }
)


@dataclass(frozen=True, slots=True)
class ModuleRunnerHealth:
    module_key: str
    healthy: bool
    prompt_pack_version: str | None
    details: tuple[str, ...] = ()


@runtime_checkable
class WholeBookModuleRunner(Protocol):
    def validate_request(self, request: PrivateEngineExecutionRequest) -> None: ...

    def prepare_context(self, request: PrivateEngineExecutionRequest) -> Mapping[str, Any]: ...

    def execute(self, request: PrivateEngineExecutionRequest) -> PrivateEngineExecutionResult: ...

    def validate_output(
        self, result: PrivateEngineExecutionResult
    ) -> ModuleOutputValidationReport: ...

    def collect_evidence(
        self, request: PrivateEngineExecutionRequest
    ) -> tuple[EvidenceCandidate, ...]: ...

    def build_candidates(self, result: PrivateEngineExecutionResult) -> Mapping[str, Any]: ...

    def build_checkpoint(
        self, request: PrivateEngineExecutionRequest
    ) -> PrivateEngineCheckpoint: ...

    def resume(self, request: PrivateEngineExecutionRequest) -> PrivateEngineExecutionResult: ...

    def health_check(self, module_key: WholeBookModuleKey | str) -> ModuleRunnerHealth: ...


@dataclass
class FakeModuleRunner:
    """Fake runner: structured DTO only, no ORM/License/Credential."""

    provider: WholeBookProviderGateway = field(default_factory=FakeProviderGateway)
    prompt_pack: FakePromptPackManifest | None = None
    validator: FakeModuleOutputValidator = field(default_factory=FakeModuleOutputValidator)
    cancelled: set[str] = field(default_factory=set)
    budget_remaining: bool = True

    def __post_init__(self) -> None:
        # Enforce forbidden capabilities stay false conceptually.
        self._orm_access = False
        self._license_parse = False
        self._credential_read = False

    def validate_request(self, request: PrivateEngineExecutionRequest) -> None:
        if request.mock is False and request.prompt_pack_ref == "":
            raise ValueError("prompt_pack_ref required")
        for module in request.resolved_module_keys:
            if module in (
                WholeBookModuleKey.BOOK_OVERVIEW,
                WholeBookModuleKey.STRUCTURE_STAGES,
                WholeBookModuleKey.CHAPTER_FUNCTIONS,
                WholeBookModuleKey.STORYLINES,
            ):
                get_module_spec(module)

    def prepare_context(self, request: PrivateEngineExecutionRequest) -> Mapping[str, Any]:
        return {
            "context_bundle_ref": request.context_bundle_ref,
            "prompt_pack_ref": request.prompt_pack_ref,
            "orm_access": False,
            "credential_read": False,
        }

    def execute(self, request: PrivateEngineExecutionRequest) -> PrivateEngineExecutionResult:
        if request.cancellation_ref and request.cancellation_ref in self.cancelled:
            status = "cancelled"
        elif not self.budget_remaining:
            status = "budget_exceeded"
        else:
            status = "completed_fake"
        pack_version = None
        if self.prompt_pack is not None:
            pack_version = self.prompt_pack.manifest.prompt_pack_version
        checkpoint = self.build_checkpoint(request)
        return PrivateEngineExecutionResult(
            schema="storylens.private_engine.result",
            version="1.0.0",
            engine_id="fake.signed.private_engine",
            engine_version="0.0.1-fake",
            stage_key=str(request.stage_key.value if hasattr(request.stage_key, "value") else request.stage_key),
            attempt=request.attempt,
            status=status,
            module_outputs={"fake": True, "prompt_pack_version": pack_version},
            evidence_candidates=self.collect_evidence(request),
            asset_candidates=(),
            relation_candidates=(),
            conflict_candidates=(),
            checkpoint=checkpoint,
            usage={"synthetic": True},
            warnings=("fake_runner",),
            validation_summary={"accepted": False},
            generated_at=datetime(2026, 7, 23, 0, 0, 0),
        )

    def validate_output(
        self, result: PrivateEngineExecutionResult
    ) -> ModuleOutputValidationReport:
        return self.validator.validate(result.module_outputs)

    def collect_evidence(
        self, request: PrivateEngineExecutionRequest
    ) -> tuple[EvidenceCandidate, ...]:
        return fake_evidence_candidates(
            book_id=request.book_id,
            book_snapshot_id=request.book_snapshot_id,
        )

    def build_candidates(self, result: PrivateEngineExecutionResult) -> Mapping[str, Any]:
        # Never confirm/lock/canonical.
        return {
            "asset_candidates": result.asset_candidates,
            "relation_candidates": result.relation_candidates,
            "auto_confirm": False,
            "auto_lock": False,
            "canonical_overwrite": False,
        }

    def build_checkpoint(
        self, request: PrivateEngineExecutionRequest
    ) -> PrivateEngineCheckpoint:
        pack_id = None
        pack_version = None
        if self.prompt_pack is not None:
            pack_id = self.prompt_pack.manifest.prompt_pack_id
            pack_version = self.prompt_pack.manifest.prompt_pack_version
        return build_fake_checkpoint(
            book_snapshot_id=request.book_snapshot_id,
            configuration_fingerprint=request.configuration_fingerprint,
            stage_key=str(
                request.stage_key.value if hasattr(request.stage_key, "value") else request.stage_key
            ),
            attempt=request.attempt,
            prompt_pack_id=pack_id,
            prompt_pack_version=pack_version,
        )

    def resume(self, request: PrivateEngineExecutionRequest) -> PrivateEngineExecutionResult:
        return self.execute(request)

    def health_check(self, module_key: WholeBookModuleKey | str) -> ModuleRunnerHealth:
        key = module_key.value if isinstance(module_key, WholeBookModuleKey) else str(module_key)
        pack_version = (
            self.prompt_pack.manifest.prompt_pack_version if self.prompt_pack else None
        )
        return ModuleRunnerHealth(
            module_key=key,
            healthy=True,
            prompt_pack_version=pack_version,
            details=("fake", "provider_gateway_only", PRIVATE_ENGINE_PROTOCOL_ID),
        )

    def cancel(self, cancellation_ref: str) -> None:
        self.cancelled.add(cancellation_ref)
