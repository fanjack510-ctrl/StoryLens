"""Whole-book Module Runner foundations (Phase 2B Agent R / CHG-039).

Includes:
- WholeBookModuleSpecRegistry
- BaseWholeBookModuleRunner
- Four Fake runners (synthetic only)
- ModuleProviderExecutionAdapter
- ModuleCheckpointBuilder / Validator

No ORM, License, Credential, formal prompts, or real novel inference.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from typing import Any, Mapping, MutableMapping, Sequence

from app.narrative_core.enums import (
    EvidenceRole,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WholeBookStageKey,
)
from app.narrative_core.private_engine_contract.checkpoint import (
    CheckpointCompatibilityInput,
    assert_checkpoint_compatible,
)
from app.narrative_core.private_engine_contract.context import (
    ContextBundle,
    FakeContextPipeline,
    fake_context_bundle,
)
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineError,
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.evidence import EvidenceCandidate
from app.narrative_core.private_engine_contract.language import (
    OutputLocale,
    SourceLanguage,
    assert_language_locale_separated,
)
from app.narrative_core.private_engine_contract.manifest import PRIVATE_ENGINE_PROTOCOL_ID
from app.narrative_core.private_engine_contract.module_runner import (
    MODULE_RUNNER_PROTOCOL_METHODS,
    ModuleRunnerHealth,
    RUNNER_FORBIDDEN_CAPABILITIES,
)
from app.narrative_core.private_engine_contract.module_spec import (
    ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC,
    FIRST_FOUR_MODULE_KEYS,
    FIRST_FOUR_MODULE_SPECS,
    MODULE_PRODUCER_STAGES,
    PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC,
    WholeBookModuleExecutionSpec,
    get_module_spec,
    validate_first_four_consistent_with_legacy_maps,
    validate_module_registry_unique,
    validate_stage_keys_legal,
)
from app.narrative_core.private_engine_contract.protocol import (
    PrivateEngineCheckpoint,
    PrivateEngineExecutionRequest,
    PrivateEngineExecutionResult,
    assert_mapping_has_no_forbidden_keys,
    assert_request_has_no_forbidden_fields,
)
from app.narrative_core.private_engine_contract.provider_gateway import (
    FakeProviderGateway,
    ProviderInferenceRequest,
    ProviderInferenceResponse,
    WholeBookProviderGateway,
)
from app.narrative_core.private_engine_contract.validation import ModuleOutputValidationReport
from app.narrative_core.product_contract.keys import PRODUCT_MODULE_STAGE_DEPENDENCIES
from app.narrative_core.product_contract.module_results import (
    BookOverviewResultDto,
    ChapterFunctionsResultDto,
    EvidenceRefLite,
    StorylinesResultDto,
    StructureStageItemDto,
    StructureStagesResultDto,
    TurningPointDto,
)
from app.narrative_core.services.fake_prompt_pack import (
    FakePromptPackServiceManifest,
    build_fake_prompt_pack,
)
from app.narrative_core.services.whole_book_candidate_builder import (
    ModuleCandidateBuilder,
    compute_output_fingerprint,
)
from app.narrative_core.services.whole_book_module_output_validator import (
    DefaultModuleOutputValidator,
    ModuleOutputValidationInput,
    ReferenceResolver,
)
from app.narrative_core.services.whole_book_stage_plan import ENGINE_MODULE_PLANNING_STAGES

# ---------------------------------------------------------------------------
# Module Spec Registry
# ---------------------------------------------------------------------------


@dataclass
class WholeBookModuleSpecRegistry:
    """Runtime registry for Module Execution Specs.

    Does not access ORM or Provider. Does not maintain a fourth frontend mapping.
    """

    _specs: dict[WholeBookModuleKey, WholeBookModuleExecutionSpec] = field(default_factory=dict)

    def register(self, spec: WholeBookModuleExecutionSpec) -> None:
        if not spec.module_version or not str(spec.module_version).strip():
            raise ValueError("module_version is required")
        if spec.module_key in self._specs:
            raise ValueError(f"duplicate module key: {spec.module_key.value}")
        self._validate_spec(spec)
        self._specs[spec.module_key] = spec

    def get(self, module_key: WholeBookModuleKey | str) -> WholeBookModuleExecutionSpec:
        key = module_key if isinstance(module_key, WholeBookModuleKey) else WholeBookModuleKey(module_key)
        if key not in self._specs:
            raise KeyError(f"module not registered: {key}")
        return self._specs[key]

    def list(self) -> tuple[WholeBookModuleExecutionSpec, ...]:
        return tuple(self._specs[k] for k in sorted(self._specs, key=lambda m: m.value))

    def validate(self) -> None:
        specs = self.list()
        validate_module_registry_unique(specs)
        validate_stage_keys_legal(specs)
        for spec in specs:
            self._validate_spec(spec)
        # When first-four are present, keep legacy compatibility.
        if FIRST_FOUR_MODULE_KEYS.issubset(self.supported_modules()):
            validate_first_four_consistent_with_legacy_maps()

    def planning_stages(self) -> dict[WholeBookModuleKey, tuple[WholeBookStageKey, ...]]:
        return {k: v.required_stage_keys for k, v in self._specs.items()}

    def producer_stages(self) -> dict[WholeBookModuleKey, tuple[WholeBookStageKey, ...]]:
        return {k: v.producer_stage_keys for k, v in self._specs.items()}

    def result_dependencies(self) -> dict[WholeBookModuleKey, tuple[WholeBookStageKey, ...]]:
        return {k: v.product_result_stage_dependencies for k, v in self._specs.items()}

    def supported_modules(self) -> frozenset[WholeBookModuleKey]:
        return frozenset(self._specs)

    def export_legacy_compatibility_views(self) -> Mapping[str, Any]:
        """Temporary adapters — derived from registry, not a fourth independent map."""

        planning = self.planning_stages()
        producer = self.producer_stages()
        product = self.result_dependencies()
        return {
            "ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC": planning,
            "MODULE_PRODUCER_STAGES": producer,
            "PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC": product,
            # Re-export frozen contract constants for callers that still import old names.
            "ENGINE_MODULE_PLANNING_STAGES": {
                k: ENGINE_MODULE_PLANNING_STAGES[k] for k in planning if k in ENGINE_MODULE_PLANNING_STAGES
            },
            "PRODUCT_MODULE_STAGE_DEPENDENCIES": {
                k: PRODUCT_MODULE_STAGE_DEPENDENCIES[k]
                for k in product
                if k in PRODUCT_MODULE_STAGE_DEPENDENCIES
            },
            "contract_derived": {
                "ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC": ENGINE_MODULE_PLANNING_STAGES_FROM_SPEC,
                "MODULE_PRODUCER_STAGES": MODULE_PRODUCER_STAGES,
                "PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC": PRODUCT_MODULE_STAGE_DEPENDENCIES_FROM_SPEC,
            },
        }

    def _validate_spec(self, spec: WholeBookModuleExecutionSpec) -> None:
        legal = frozenset(WholeBookStageKey)
        planning = frozenset(spec.required_stage_keys)
        if not planning:
            raise ValueError(f"{spec.module_key}: planning closure empty")
        for stage in (*spec.required_stage_keys, *spec.producer_stage_keys, *spec.product_result_stage_dependencies):
            if stage not in legal:
                raise ValueError(f"{spec.module_key}: illegal stage {stage}")
        for stage in spec.producer_stage_keys:
            if stage not in planning:
                raise ValueError(
                    f"{spec.module_key}: producer stage {stage} not in planning closure"
                )
        for stage in spec.product_result_stage_dependencies:
            # Result deps must be legal stages; closure membership is vs engine planning
            # seeds for the module (may be a subset of full book plan). Soft rule:
            # deps that are also in required_stage_keys or are known stage keys are OK
            # when consistent with legacy maps (validated separately for first-four).
            if stage not in legal:
                raise ValueError(f"{spec.module_key}: illegal result dependency {stage}")
        # For first-four freeze: result deps must appear in legacy planning closure.
        if spec.module_key in ENGINE_MODULE_PLANNING_STAGES:
            legacy_plan = frozenset(ENGINE_MODULE_PLANNING_STAGES[spec.module_key])
            # Product deps are view gates and may include earlier stages; require they
            # are legal catalog keys only (already checked). Producer ⊆ planning above.


def build_default_module_spec_registry() -> WholeBookModuleSpecRegistry:
    registry = WholeBookModuleSpecRegistry()
    for spec in FIRST_FOUR_MODULE_SPECS:
        registry.register(spec)
    registry.validate()
    return registry


DEFAULT_MODULE_SPEC_REGISTRY = build_default_module_spec_registry()


# ---------------------------------------------------------------------------
# Checkpoint builder / validator
# ---------------------------------------------------------------------------


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class ModuleCheckpointBuilder:
    engine_id: str = "fake.signed.private_engine"
    engine_version: str = "0.0.1-fake"

    def build(
        self,
        *,
        request: PrivateEngineExecutionRequest,
        module_key: str,
        module_version: str,
        prompt_pack_id: str | None,
        prompt_pack_version: str | None,
        context_bundle_hash: str | None,
        completed_units: Sequence[str] = (),
        pending_units: Sequence[str] = (),
        output_fingerprints: Sequence[str] = (),
        usage: Mapping[str, Any] | None = None,
        provider_policy_key: str | None = "fake",
        quality_profile: str | None = "balanced",
    ) -> PrivateEngineCheckpoint:
        stage_key = (
            request.stage_key.value
            if isinstance(request.stage_key, WholeBookStageKey)
            else str(request.stage_key)
        )
        integrity = _stable_hash(
            {
                "protocol": PRIVATE_ENGINE_PROTOCOL_ID,
                "engine_id": self.engine_id,
                "engine_version": self.engine_version,
                "module_key": module_key,
                "module_version": module_version,
                "stage_key": stage_key,
                "attempt": request.attempt,
                "prompt_pack_id": prompt_pack_id,
                "prompt_pack_version": prompt_pack_version,
                "context_bundle_hash": context_bundle_hash,
                "configuration_fingerprint": request.configuration_fingerprint,
                "book_snapshot_id": request.book_snapshot_id,
                "completed_units": list(completed_units),
                "pending_units": list(pending_units),
                "output_fingerprints": list(output_fingerprints),
            }
        )
        return PrivateEngineCheckpoint(
            protocol_version=PRIVATE_ENGINE_PROTOCOL_ID,
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            module_key=module_key,
            module_version=module_version,
            stage_key=stage_key,
            attempt=request.attempt,
            prompt_pack_id=prompt_pack_id,
            prompt_pack_version=prompt_pack_version,
            provider_policy_key=provider_policy_key,
            quality_profile=quality_profile,
            context_bundle_hash=context_bundle_hash,
            configuration_fingerprint=request.configuration_fingerprint,
            book_snapshot_id=request.book_snapshot_id,
            completed_units=tuple(completed_units),
            pending_units=tuple(pending_units),
            output_fingerprints=tuple(output_fingerprints),
            usage=dict(usage or {"synthetic": True}),
            integrity_hash=integrity,
        )


@dataclass
class ModuleCheckpointValidator:
    def validate_resume(
        self,
        *,
        checkpoint: PrivateEngineCheckpoint,
        current_engine_id: str,
        current_engine_version: str,
        current_prompt_pack_id: str | None,
        current_prompt_pack_version: str | None,
        current_context_bundle_hash: str | None,
        current_book_snapshot_id: int,
        current_configuration_fingerprint: str,
        module_spec_changed: bool = False,
        module_migration_available: bool = False,
    ) -> None:
        # Protocol / integrity first.
        if checkpoint.protocol_version != PRIVATE_ENGINE_PROTOCOL_ID:
            raise private_engine_error(PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE)
        expected = ModuleCheckpointBuilder(
            engine_id=checkpoint.engine_id,
            engine_version=checkpoint.engine_version,
        )
        # Recompute integrity over checkpoint fields (usage excluded from integrity).
        recomputed = _stable_hash(
            {
                "protocol": checkpoint.protocol_version,
                "engine_id": checkpoint.engine_id,
                "engine_version": checkpoint.engine_version,
                "module_key": checkpoint.module_key,
                "module_version": checkpoint.module_version,
                "stage_key": checkpoint.stage_key,
                "attempt": checkpoint.attempt,
                "prompt_pack_id": checkpoint.prompt_pack_id,
                "prompt_pack_version": checkpoint.prompt_pack_version,
                "context_bundle_hash": checkpoint.context_bundle_hash,
                "configuration_fingerprint": checkpoint.configuration_fingerprint,
                "book_snapshot_id": checkpoint.book_snapshot_id,
                "completed_units": list(checkpoint.completed_units),
                "pending_units": list(checkpoint.pending_units),
                "output_fingerprints": list(checkpoint.output_fingerprints),
            }
        )
        integrity_ok = (not checkpoint.integrity_hash) or checkpoint.integrity_hash == recomputed
        assert_checkpoint_compatible(
            CheckpointCompatibilityInput(
                checkpoint=checkpoint,
                current_engine_id=current_engine_id,
                current_engine_version=current_engine_version,
                current_prompt_pack_id=current_prompt_pack_id,
                current_prompt_pack_version=current_prompt_pack_version,
                current_context_bundle_hash=current_context_bundle_hash,
                current_book_snapshot_id=current_book_snapshot_id,
                current_configuration_fingerprint=current_configuration_fingerprint,
                module_spec_changed=module_spec_changed,
                module_migration_available=module_migration_available,
                integrity_ok=integrity_ok,
            )
        )
        _ = expected


# ---------------------------------------------------------------------------
# Provider execution adapter (Runner side)
# ---------------------------------------------------------------------------


@dataclass
class ModuleProviderExecutionAdapter:
    """Calls WholeBookProviderGateway Protocol only — no concrete Provider SDK."""

    gateway: WholeBookProviderGateway
    cancelled: set[str] = field(default_factory=set)
    budget_remaining: bool = True

    def execute(
        self,
        *,
        request_id: str,
        module_key: WholeBookModuleKey | str,
        instruction_ref: str,
        input_bundle_ref: str,
        response_schema_ref: str,
        prompt_pack_ref: str,
        provider_policy: Mapping[str, Any],
        cancellation_ref: str | None,
        token_budget: int | None = 1024,
        cost_budget: float | None = None,
    ) -> ProviderInferenceResponse:
        assert_mapping_has_no_forbidden_keys(provider_policy, label="provider_policy")
        if not response_schema_ref.strip():
            raise ValueError("response_schema_ref is required")
        if instruction_ref == input_bundle_ref:
            raise ValueError("instruction_ref and input_bundle_ref must stay isolated")
        if cancellation_ref and cancellation_ref in self.cancelled:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
        if not self.budget_remaining:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED)

        key = module_key.value if isinstance(module_key, WholeBookModuleKey) else str(module_key)
        inference = ProviderInferenceRequest(
            request_id=request_id,
            provider_kind=str(provider_policy.get("provider_kind", "fake")),
            model_route=str(provider_policy.get("model_route", "fake-route")),
            task_type=f"module:{key}",
            system_instruction_ref=instruction_ref,
            prompt_pack_ref=prompt_pack_ref,
            input_bundle_ref=input_bundle_ref,
            response_schema_ref=response_schema_ref,
            temperature_policy={"source_data_untrusted": True},
            token_budget=token_budget,
            cost_budget=cost_budget,
            timeout_policy={"timeout_ms": 1000},
            retry_policy={"max_retries": 0},
            cancellation_ref=cancellation_ref,
            data_handling_policy={"source_data_untrusted": True},
            metadata={
                "source_data_untrusted": True,
                "module_key": key,
                "synthetic": True,
            },
        )
        # Credential must never appear on request attributes.
        for banned in ("api_key", "credential", "credentials", "authorization"):
            if hasattr(inference, banned):
                raise ValueError(f"credential field leaked: {banned}")

        self.gateway.validate_policy(provider_policy)
        estimate = self.gateway.estimate(inference)
        if not estimate.within_budget:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED)
        response = self.gateway.execute(inference)
        if response.status != "success" or response.structured_output is None:
            # Do not fabricate success results on provider failure.
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_RESPONSE_INVALID)
        return response

    def cancel(self, cancellation_ref: str) -> bool:
        self.cancelled.add(cancellation_ref)
        return self.gateway.cancel(cancellation_ref)


# ---------------------------------------------------------------------------
# Synthetic DTO helpers (explicit fixtures only — no text inference)
# ---------------------------------------------------------------------------

GENERAL_CHAPTER_FUNCTION_LABELS: frozenset[str] = frozenset(
    {
        "setup",
        "escalation",
        "climax",
        "resolution",
        "transition",
        "side_story",
        "flashback",
        "empty",
        "non_mainline",
        "unknown",
        "primary",
        "secondary",
    }
)

GENERAL_STORYLINE_TYPES: frozenset[str] = frozenset(
    {"main", "side", "relationship", "quest", "unknown"}
)

GENERAL_STORYLINE_STATUSES: frozenset[str] = frozenset(
    {"active", "paused", "resumed", "terminated", "incomplete", "unknown"}
)


def _dto_to_mapping(dto: Any) -> dict[str, Any]:
    if is_dataclass(dto) and not isinstance(dto, type):
        return asdict(dto)
    if isinstance(dto, Mapping):
        return dict(dto)
    raise TypeError("expected dataclass DTO or mapping")


def empty_book_overview_dto() -> BookOverviewResultDto:
    return BookOverviewResultDto(
        logline="",
        premise="",
        central_question="",
        primary_conflict="",
        protagonist_asset_id=None,
        major_storyline_ids=(),
        structure_summary="",
        ending_state="",
        evidence_refs=(),
        confidence=None,
    )


def empty_structure_stages_dto() -> StructureStagesResultDto:
    return StructureStagesResultDto(
        stages=(),
        turning_points=(),
        act_or_phase_labels=(),
        chapter_ranges=(),
        narrative_function="",
        evidence_refs=(),
        confidence=None,
    )


def empty_chapter_functions_dto(*, chapter_id: int = 0, chapter_order: int = 0) -> ChapterFunctionsResultDto:
    return ChapterFunctionsResultDto(
        chapter_id=chapter_id,
        chapter_order=chapter_order,
        function_labels=(),
        primary_storyline_ids=(),
        character_focus_ids=(),
        hook_ids=(),
        payoff_ids=(),
        change_summary="",
        evidence_refs=(),
    )


def empty_storylines_dto() -> StorylinesResultDto:
    return StorylinesResultDto(
        storyline_asset_id=0,
        title="",
        summary="",
        storyline_type="unknown",
        chapter_range=(None, None),
        key_event_ids=(),
        involved_entity_ids=(),
        relation_ids=(),
        status="unknown",
        evidence_refs=(),
    )


# ---------------------------------------------------------------------------
# Base Runner
# ---------------------------------------------------------------------------


@dataclass
class BaseWholeBookModuleRunner:
    """Protocol-only base. Subclasses supply synthetic/fake module payloads."""

    module_key: WholeBookModuleKey
    registry: WholeBookModuleSpecRegistry = field(default_factory=build_default_module_spec_registry)
    prompt_pack: FakePromptPackServiceManifest | None = None
    provider_adapter: ModuleProviderExecutionAdapter | None = None
    output_validator: DefaultModuleOutputValidator = field(default_factory=DefaultModuleOutputValidator)
    candidate_builder: ModuleCandidateBuilder = field(default_factory=ModuleCandidateBuilder)
    checkpoint_builder: ModuleCheckpointBuilder = field(default_factory=ModuleCheckpointBuilder)
    checkpoint_validator: ModuleCheckpointValidator = field(default_factory=ModuleCheckpointValidator)
    context_pipeline: FakeContextPipeline = field(default_factory=FakeContextPipeline)
    emitted_output_fingerprints: set[str] = field(default_factory=set)
    cancelled: set[str] = field(default_factory=set)
    budget_remaining: bool = True
    # Explicit synthetic fixtures keyed by fixture_id (never inferred from novel text).
    synthetic_fixtures: dict[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.prompt_pack is None:
            self.prompt_pack = build_fake_prompt_pack()
        if self.provider_adapter is None:
            self.provider_adapter = ModuleProviderExecutionAdapter(gateway=FakeProviderGateway())
        # Forbidden capabilities — conceptual flags for audits/tests.
        self._orm_access = False
        self._license_parse = False
        self._credential_read = False
        self._auto_confirm = False
        self._auto_lock = False
        self._canonical_overwrite = False

    @property
    def spec(self) -> WholeBookModuleExecutionSpec:
        return self.registry.get(self.module_key)

    def validate_request(self, request: PrivateEngineExecutionRequest) -> None:
        assert_request_has_no_forbidden_fields(request)
        if not request.prompt_pack_ref or not str(request.prompt_pack_ref).strip():
            raise ValueError("prompt_pack_ref / Prompt Pack Version is required")
        assert_language_locale_separated(request.source_language, request.output_locale)
        SourceLanguage(request.source_language)
        OutputLocale(request.output_locale)
        if self.module_key not in request.resolved_module_keys and self.module_key not in request.requested_module_keys:
            # Allow health/unit tests that pass a single-module request via resolved keys empty.
            if request.resolved_module_keys or request.requested_module_keys:
                raise ValueError(f"module {self.module_key.value} not in request module keys")
        self.registry.get(self.module_key)
        if request.cancellation_ref and request.cancellation_ref in self.cancelled:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_CANCELLED)
        if not self.budget_remaining:
            raise private_engine_error(PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED)

    def prepare_context(self, request: PrivateEngineExecutionRequest) -> Mapping[str, Any]:
        self.validate_request(request)
        bundle = self._resolve_context_bundle(request)
        self.context_pipeline.validate_context_bundle(bundle)
        return {
            "context_bundle_ref": request.context_bundle_ref,
            "context_bundle_hash": bundle.bundle_hash,
            "book_id": bundle.book_id,
            "book_snapshot_id": bundle.book_snapshot_id,
            "prompt_pack_ref": request.prompt_pack_ref,
            "prompt_pack_version": self.prompt_pack.manifest.prompt_pack_version if self.prompt_pack else None,
            "orm_access": False,
            "license_parse": False,
            "credential_read": False,
            "source_language": request.source_language,
            "output_locale": request.output_locale,
            "synthetic": True,
            "fake": True,
            "non_production": True,
        }

    def execute(self, request: PrivateEngineExecutionRequest) -> PrivateEngineExecutionResult:
        ctx = self.prepare_context(request)
        if request.cancellation_ref and request.cancellation_ref in self.cancelled:
            status = "cancelled"
            module_outputs: dict[str, Any] = {
                "fake": True,
                "synthetic": True,
                "non_production": True,
                "empty_dto": True,
                **_dto_to_mapping(self._empty_dto()),
            }
            evidence: tuple[EvidenceCandidate, ...] = ()
        elif not self.budget_remaining:
            status = "budget_exceeded"
            module_outputs = {
                "fake": True,
                "synthetic": True,
                "non_production": True,
                "empty_dto": True,
                **_dto_to_mapping(self._empty_dto()),
            }
            evidence = ()
        else:
            status = "completed_fake"
            module_outputs = dict(self._build_synthetic_module_outputs(request, ctx))
            evidence = self.collect_evidence(request)
            # Optional provider adapter touch (Fake gateway only).
            if self.provider_adapter is not None and module_outputs.get("skip_provider") is not True:
                try:
                    self.provider_adapter.budget_remaining = self.budget_remaining
                    self.provider_adapter.cancelled = set(self.cancelled)
                    pack = self.prompt_pack
                    assert pack is not None
                    self.provider_adapter.execute(
                        request_id=f"fake-{request.run_id}-{self.module_key.value}",
                        module_key=self.module_key,
                        instruction_ref=pack.instruction_refs.get(self.module_key),
                        input_bundle_ref=request.context_bundle_ref,
                        response_schema_ref=pack.response_schema_refs.get(self.module_key),
                        prompt_pack_ref=request.prompt_pack_ref,
                        provider_policy=request.provider_policy or {"provider_kind": "fake"},
                        cancellation_ref=request.cancellation_ref,
                    )
                except PrivateEngineError as exc:
                    if exc.code == PrivateEngineErrorCode.PROVIDER_BUDGET_EXCEEDED:
                        status = "budget_exceeded"
                        module_outputs = {
                            "fake": True,
                            "synthetic": True,
                            "non_production": True,
                            "empty_dto": True,
                            **_dto_to_mapping(self._empty_dto()),
                        }
                        evidence = ()
                    elif exc.code == PrivateEngineErrorCode.PROVIDER_CANCELLED:
                        status = "cancelled"
                        module_outputs = {
                            "fake": True,
                            "synthetic": True,
                            "non_production": True,
                            "empty_dto": True,
                            **_dto_to_mapping(self._empty_dto()),
                        }
                        evidence = ()
                    else:
                        # Provider failure must not fabricate accepted results.
                        status = "provider_failed"
                        module_outputs = {
                            "fake": True,
                            "synthetic": True,
                            "non_production": True,
                            "schema_error": True,
                            "empty_dto": True,
                            **_dto_to_mapping(self._empty_dto()),
                        }
                        evidence = ()

        module_outputs.setdefault("fake", True)
        module_outputs.setdefault("synthetic", True)
        module_outputs.setdefault("non_production", True)
        module_outputs["module_key"] = self.module_key.value
        module_outputs["module_version"] = self.spec.module_version
        module_outputs["prompt_pack_version"] = (
            self.prompt_pack.manifest.prompt_pack_version if self.prompt_pack else None
        )
        module_outputs["source_language"] = request.source_language
        module_outputs["output_locale"] = request.output_locale

        checkpoint = self.build_checkpoint(request)
        result = PrivateEngineExecutionResult(
            schema="storylens.private_engine.result",
            version="1.0.0",
            engine_id="fake.signed.private_engine",
            engine_version="0.0.1-fake",
            stage_key=str(
                request.stage_key.value
                if isinstance(request.stage_key, WholeBookStageKey)
                else request.stage_key
            ),
            attempt=request.attempt,
            status=status,
            module_outputs=module_outputs,
            evidence_candidates=evidence,
            asset_candidates=tuple(module_outputs.get("asset_candidates", ()) or ()),
            relation_candidates=tuple(module_outputs.get("relation_candidates", ()) or ()),
            conflict_candidates=tuple(module_outputs.get("conflict_candidates", ()) or ()),
            checkpoint=checkpoint,
            usage={"synthetic": True, "fake": True},
            warnings=("fake_runner", "non_production", "not_real_analysis"),
            validation_summary={"accepted": False, "fake": True},
            generated_at=datetime(2026, 7, 24, 0, 0, 0),
        )
        return result

    def validate_output(self, result: PrivateEngineExecutionResult) -> ModuleOutputValidationReport:
        book_id = int(result.module_outputs.get("book_id", 1) or 1)
        book_snapshot_id = int(result.module_outputs.get("book_snapshot_id", 1) or 1)
        resolver = ReferenceResolver(
            asset_ids=frozenset(int(x) for x in result.module_outputs.get("resolver_asset_ids", ()) or ()),
            entity_ids=frozenset(int(x) for x in result.module_outputs.get("resolver_entity_ids", ()) or ()),
            storyline_ids=frozenset(
                int(x) for x in result.module_outputs.get("resolver_storyline_ids", ()) or ()
            ),
            chapter_ids=frozenset(int(x) for x in result.module_outputs.get("resolver_chapter_ids", ()) or ()),
            output_refs=frozenset(str(x) for x in result.module_outputs.get("resolver_output_refs", ()) or ()),
        )
        return self.output_validator.validate(
            ModuleOutputValidationInput(
                module_key=self.module_key,
                module_outputs=result.module_outputs,
                evidence_candidates=tuple(
                    e for e in result.evidence_candidates if isinstance(e, EvidenceCandidate)
                ),
                book_id=book_id,
                book_snapshot_id=book_snapshot_id,
                expected_book_id=book_id,
                expected_book_snapshot_id=book_snapshot_id,
                resolver=resolver,
                require_evidence_for_acceptance=False,
            )
        )

    def collect_evidence(
        self, request: PrivateEngineExecutionRequest
    ) -> tuple[EvidenceCandidate, ...]:
        # Synthetic evidence only — never extracted by reading novel body for inference.
        fixture = self._fixture_from_request(request)
        if fixture.get("evidence_insufficient") is True:
            return ()
        explicit = fixture.get("evidence_candidates")
        if isinstance(explicit, (list, tuple)) and explicit:
            out: list[EvidenceCandidate] = []
            for item in explicit:
                if isinstance(item, EvidenceCandidate):
                    out.append(item)
                elif isinstance(item, Mapping):
                    out.append(
                        EvidenceCandidate(
                            candidate_id=str(item.get("candidate_id", "ev-synth")),
                            book_snapshot_id=int(item.get("book_snapshot_id", request.book_snapshot_id)),
                            snapshot_chapter_id=item.get("snapshot_chapter_id"),
                            snapshot_paragraph_id=item.get("snapshot_paragraph_id"),
                            stable_paragraph_id=item.get("stable_paragraph_id"),
                            paragraph_content_hash=str(item.get("paragraph_content_hash", "synth-hash")),
                            start_offset=item.get("start_offset"),
                            end_offset=item.get("end_offset"),
                            evidence_role=EvidenceRole(item.get("evidence_role", EvidenceRole.SUPPORT)),
                            target_module_key=self.module_key,
                            target_output_ref=str(item.get("target_output_ref", f"{self.module_key.value}.claim")),
                            extraction_method="synthetic_fixture",
                            confidence=item.get("confidence"),
                            source_context_unit_id=item.get("source_context_unit_id"),
                            book_id=int(item.get("book_id", request.book_id)),
                            preview=str(item.get("preview", "synthetic"))[:160],
                            from_derived_summary=bool(item.get("from_derived_summary", False)),
                        )
                    )
            return tuple(out)
        return (
            EvidenceCandidate(
                candidate_id=f"ev-synth-{self.module_key.value}",
                book_snapshot_id=request.book_snapshot_id,
                snapshot_chapter_id=1,
                snapshot_paragraph_id=1,
                stable_paragraph_id="p1",
                paragraph_content_hash="synth-para-hash-1",
                start_offset=0,
                end_offset=8,
                evidence_role=EvidenceRole.SUPPORT,
                target_module_key=self.module_key,
                target_output_ref=f"{self.module_key.value}.synthetic",
                extraction_method="synthetic_fixture",
                confidence=0.1,
                source_context_unit_id="chapter:1",
                book_id=request.book_id,
                preview="synthetic",
                from_derived_summary=False,
            ),
        )

    def build_candidates(self, result: PrivateEngineExecutionResult) -> Mapping[str, Any]:
        report = self.validate_output(result)
        built = self.candidate_builder.build(
            result=result,
            validation=report,
            run_id=1,
            run_stage_id=None,
            book_snapshot_id=int(result.module_outputs.get("book_snapshot_id", 1) or 1),
            module_key=self.module_key.value,
            module_version=self.spec.module_version,
            configuration_fingerprint=str(
                result.module_outputs.get("configuration_fingerprint", "fake-config-fp")
            ),
            prompt_pack_id=self.prompt_pack.manifest.prompt_pack_id if self.prompt_pack else None,
            prompt_pack_version=(
                self.prompt_pack.manifest.prompt_pack_version if self.prompt_pack else None
            ),
            mock=True,
        )
        return {
            "rejected": built.rejected,
            "output_fingerprint": built.output_fingerprint,
            "asset_commands": built.asset_commands,
            "relation_commands": built.relation_commands,
            "evidence_commands": built.evidence_commands,
            "conflict_commands": built.conflict_commands,
            "stage_artifact": built.stage_artifact,
            "auto_confirm": False,
            "auto_lock": False,
            "canonical_overwrite": False,
            "orm_written": False,
            "synthetic": True,
            "fake": True,
            "validation_accepted": report.accepted,
        }

    def build_checkpoint(self, request: PrivateEngineExecutionRequest) -> PrivateEngineCheckpoint:
        pack = self.prompt_pack
        bundle = self._resolve_context_bundle(request)
        return self.checkpoint_builder.build(
            request=request,
            module_key=self.module_key.value,
            module_version=self.spec.module_version,
            prompt_pack_id=pack.manifest.prompt_pack_id if pack else None,
            prompt_pack_version=pack.manifest.prompt_pack_version if pack else None,
            context_bundle_hash=bundle.bundle_hash,
            completed_units=tuple(self._fixture_from_request(request).get("completed_units", ()) or ()),
            pending_units=tuple(
                self._fixture_from_request(request).get("pending_units", ("unit:pending",)) or ("unit:pending",)
            ),
            output_fingerprints=tuple(sorted(self.emitted_output_fingerprints)),
            usage={"synthetic": True},
        )

    def resume(self, request: PrivateEngineExecutionRequest) -> PrivateEngineExecutionResult:
        if not request.checkpoint_ref:
            raise ValueError("checkpoint_ref required for resume")
        # Compatibility validation against current pack/context/snapshot.
        prior = self.build_checkpoint(request)
        pack = self.prompt_pack
        bundle = self._resolve_context_bundle(request)
        # Allow tests to inject an explicit checkpoint via synthetic fixture.
        fixture = self._fixture_from_request(request)
        checkpoint = fixture.get("checkpoint") or prior
        if not isinstance(checkpoint, PrivateEngineCheckpoint):
            checkpoint = prior
        self.checkpoint_validator.validate_resume(
            checkpoint=checkpoint,
            current_engine_id=self.checkpoint_builder.engine_id,
            current_engine_version=self.checkpoint_builder.engine_version,
            current_prompt_pack_id=pack.manifest.prompt_pack_id if pack else None,
            current_prompt_pack_version=pack.manifest.prompt_pack_version if pack else None,
            current_context_bundle_hash=bundle.bundle_hash,
            current_book_snapshot_id=request.book_snapshot_id,
            current_configuration_fingerprint=request.configuration_fingerprint,
            module_spec_changed=bool(fixture.get("module_spec_changed", False)),
            module_migration_available=bool(fixture.get("module_migration_available", False)),
        )
        result = self.execute(request)
        # Resume must not duplicate previously emitted output fingerprints
        # (identity/hash stability — not semantic stability).
        fp = compute_output_fingerprint(
            {
                "module_outputs": {
                    k: v
                    for k, v in result.module_outputs.items()
                    if k
                    not in {
                        "prompt_pack_version",
                        "configuration_fingerprint",
                    }
                },
                "module_key": self.module_key.value,
            }
        )
        if fp in self.emitted_output_fingerprints:
            return PrivateEngineExecutionResult(
                schema=result.schema,
                version=result.version,
                engine_id=result.engine_id,
                engine_version=result.engine_version,
                stage_key=result.stage_key,
                attempt=result.attempt,
                status="resumed_deduplicated",
                module_outputs={
                    **dict(result.module_outputs),
                    "duplicate": True,
                    "resume_deduped": True,
                },
                evidence_candidates=(),
                asset_candidates=(),
                relation_candidates=(),
                conflict_candidates=(),
                checkpoint=result.checkpoint,
                usage=result.usage,
                warnings=result.warnings + ("resume_deduplicated",),
                validation_summary={"accepted": False, "duplicate": True},
                generated_at=result.generated_at,
            )
        self.emitted_output_fingerprints.add(fp)
        return result

    def health_check(self, module_key: WholeBookModuleKey | str) -> ModuleRunnerHealth:
        key = module_key.value if isinstance(module_key, WholeBookModuleKey) else str(module_key)
        pack_version = self.prompt_pack.manifest.prompt_pack_version if self.prompt_pack else None
        return ModuleRunnerHealth(
            module_key=key,
            healthy=True,
            prompt_pack_version=pack_version,
            details=(
                "fake",
                "synthetic",
                "non_production",
                "provider_gateway_only",
                PRIVATE_ENGINE_PROTOCOL_ID,
                *MODULE_RUNNER_PROTOCOL_METHODS,
                *sorted(RUNNER_FORBIDDEN_CAPABILITIES),
            ),
        )

    def cancel(self, cancellation_ref: str) -> None:
        self.cancelled.add(cancellation_ref)
        if self.provider_adapter is not None:
            self.provider_adapter.cancel(cancellation_ref)

    # --- hooks ---

    def _empty_dto(self) -> Any:
        raise NotImplementedError

    def _default_synthetic_dto(self, fixture: Mapping[str, Any]) -> Any:
        raise NotImplementedError

    def _build_synthetic_module_outputs(
        self, request: PrivateEngineExecutionRequest, ctx: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        _ = ctx
        fixture = self._fixture_from_request(request)
        if fixture.get("empty_dto") is True:
            dto = self._empty_dto()
        elif "dto" in fixture:
            dto = fixture["dto"]
            if isinstance(dto, Mapping):
                payload = dict(dto)
            else:
                payload = _dto_to_mapping(dto)
            envelope: dict[str, Any] = {
                "fake": True,
                "synthetic": True,
                "non_production": True,
                "book_id": request.book_id,
                "book_snapshot_id": request.book_snapshot_id,
                "configuration_fingerprint": request.configuration_fingerprint,
                **payload,
                **{k: v for k, v in fixture.items() if k not in {"dto", "evidence_candidates", "checkpoint"}},
            }
            return envelope
        else:
            dto = self._default_synthetic_dto(fixture)
        payload = _dto_to_mapping(dto)
        envelope = {
            "fake": True,
            "synthetic": True,
            "non_production": True,
            "book_id": request.book_id,
            "book_snapshot_id": request.book_snapshot_id,
            "configuration_fingerprint": request.configuration_fingerprint,
            **payload,
        }
        for key in (
            "partial",
            "unknown",
            "evidence_insufficient",
            "schema_error",
            "invalid_ref",
            "snapshot_mismatch",
            "cross_book",
            "duplicate",
            "conflict",
            "force_accept",
            "fixture_id",
            "asset_candidates",
            "relation_candidates",
            "conflict_candidates",
            "resolver_asset_ids",
            "resolver_entity_ids",
            "resolver_storyline_ids",
            "resolver_chapter_ids",
            "resolver_output_refs",
            "required_claims",
            "evidenced_claims",
            "skip_provider",
            "status_markers",
        ):
            if key in fixture:
                envelope[key] = fixture[key]
        return envelope

    def _fixture_from_request(self, request: PrivateEngineExecutionRequest) -> Mapping[str, Any]:
        # Explicit synthetic fixture only — never scan novel text / title / author.
        meta = request.provider_policy or {}
        fixture_id = meta.get("synthetic_fixture_id") or meta.get("fixture_id")
        if fixture_id and fixture_id in self.synthetic_fixtures:
            return self.synthetic_fixtures[str(fixture_id)]
        inline = meta.get("synthetic_output")
        if isinstance(inline, Mapping):
            return inline
        return {}

    def _resolve_context_bundle(self, request: PrivateEngineExecutionRequest) -> ContextBundle:
        # Ref format: fake-bundle:... or synthetic://bundle/{book}/{snap}
        ref = request.context_bundle_ref
        if ref.startswith("synthetic://bundle/"):
            parts = ref.split("/")
            book_id = int(parts[-2]) if len(parts) >= 2 else request.book_id
            snap_id = int(parts[-1]) if parts else request.book_snapshot_id
            return fake_context_bundle(book_id=book_id, book_snapshot_id=snap_id)
        return fake_context_bundle(book_id=request.book_id, book_snapshot_id=request.book_snapshot_id)


# ---------------------------------------------------------------------------
# Four Fake Runners
# ---------------------------------------------------------------------------


@dataclass
class FakeBookOverviewRunner(BaseWholeBookModuleRunner):
    module_key: WholeBookModuleKey = WholeBookModuleKey.BOOK_OVERVIEW

    def _empty_dto(self) -> BookOverviewResultDto:
        return empty_book_overview_dto()

    def _default_synthetic_dto(self, fixture: Mapping[str, Any]) -> BookOverviewResultDto:
        # Fixed synthetic only — never derives protagonist from novel body.
        mode = str(fixture.get("overview_mode", "empty"))
        if mode == "multi_protagonist":
            return BookOverviewResultDto(
                logline="[FAKE] multi-protagonist synthetic",
                premise="[FAKE] synthetic premise",
                central_question="[FAKE] synthetic question",
                primary_conflict="",
                protagonist_asset_id=None,
                major_storyline_ids=tuple(fixture.get("major_storyline_ids", (101, 102))),
                structure_summary="[FAKE] synthetic structure",
                ending_state="unknown",
                evidence_refs=(EvidenceRefLite("ev-synth-overview", "support"),),
                confidence=0.0,
            )
        if mode == "no_central_conflict":
            return BookOverviewResultDto(
                logline="[FAKE] no central conflict",
                premise="[FAKE]",
                central_question="",
                primary_conflict="",
                protagonist_asset_id=None,
                major_storyline_ids=tuple(fixture.get("major_storyline_ids", ())),
                structure_summary="",
                ending_state="unknown",
                evidence_refs=(),
                confidence=None,
            )
        if mode == "partial":
            return BookOverviewResultDto(
                logline="[FAKE] partial",
                premise="",
                central_question="",
                primary_conflict="",
                protagonist_asset_id=None,
                major_storyline_ids=(),
                structure_summary="",
                ending_state="",
                evidence_refs=(),
                confidence=None,
            )
        return empty_book_overview_dto()


@dataclass
class FakeStructureStagesRunner(BaseWholeBookModuleRunner):
    module_key: WholeBookModuleKey = WholeBookModuleKey.STRUCTURE_STAGES

    def _empty_dto(self) -> StructureStagesResultDto:
        return empty_structure_stages_dto()

    def _default_synthetic_dto(self, fixture: Mapping[str, Any]) -> StructureStagesResultDto:
        mode = str(fixture.get("structure_mode", "empty"))
        if mode == "two_stages":
            stages = (
                StructureStageItemDto("s1", "phase_a", (1, 2), "setup", 1),
                StructureStageItemDto("s2", "phase_b", (3, 4), "resolution", 2),
            )
            return StructureStagesResultDto(
                stages=stages,
                turning_points=(TurningPointDto("tp1", "shift", 2, "[FAKE]"),),
                act_or_phase_labels=("phase_a", "phase_b"),
                chapter_ranges=((1, 2), (3, 4)),
                narrative_function="synthetic",
                evidence_refs=(EvidenceRefLite("ev-struct", "support"),),
                confidence=0.0,
            )
        if mode == "five_stages":
            stages = tuple(
                StructureStageItemDto(f"s{i}", f"phase_{i}", (i, i), "transition", i)
                for i in range(1, 6)
            )
            return StructureStagesResultDto(
                stages=stages,
                turning_points=(),
                act_or_phase_labels=tuple(f"phase_{i}" for i in range(1, 6)),
                chapter_ranges=tuple((i, i) for i in range(1, 6)),
                narrative_function="synthetic",
                evidence_refs=(),
                confidence=None,
            )
        if mode == "non_contiguous":
            stages = (
                StructureStageItemDto("s1", "a", (1, 1), "setup", 1),
                StructureStageItemDto("s2", "b", (4, 5), "escalation", 2),
            )
            return StructureStagesResultDto(
                stages=stages,
                turning_points=(TurningPointDto("tp-nc", "jump", 4, "[FAKE]"),),
                act_or_phase_labels=("a", "b"),
                chapter_ranges=((1, 1), (4, 5)),
                narrative_function="synthetic",
                evidence_refs=(EvidenceRefLite("ev-tp", "support"),),
                confidence=0.0,
            )
        if mode == "unstable":
            return StructureStagesResultDto(
                stages=(),
                turning_points=(),
                act_or_phase_labels=(),
                chapter_ranges=(),
                narrative_function="no_stable_stages_identified",
                evidence_refs=(),
                confidence=None,
            )
        # Never force three-act.
        return empty_structure_stages_dto()


@dataclass
class FakeChapterFunctionsRunner(BaseWholeBookModuleRunner):
    module_key: WholeBookModuleKey = WholeBookModuleKey.CHAPTER_FUNCTIONS

    def _empty_dto(self) -> ChapterFunctionsResultDto:
        return empty_chapter_functions_dto()

    def _default_synthetic_dto(self, fixture: Mapping[str, Any]) -> ChapterFunctionsResultDto:
        mode = str(fixture.get("chapter_mode", "empty"))
        labels = tuple(fixture.get("function_labels", ()) or ())
        for label in labels:
            if label not in GENERAL_CHAPTER_FUNCTION_LABELS:
                raise ValueError(f"non-general chapter function label forbidden: {label}")
        if mode == "multi_label":
            labels = ("primary", "secondary", "setup")
        elif mode == "side_flashback":
            labels = ("side_story", "flashback")
        elif mode == "empty_chapter":
            labels = ("empty", "non_mainline")
        elif mode == "unknown":
            labels = ("unknown",)
        return ChapterFunctionsResultDto(
            chapter_id=int(fixture.get("chapter_id", 1)),
            chapter_order=int(fixture.get("chapter_order", 1)),
            function_labels=labels,
            primary_storyline_ids=tuple(fixture.get("primary_storyline_ids", ()) or ()),
            character_focus_ids=tuple(fixture.get("character_focus_ids", ()) or ()),
            hook_ids=(),
            payoff_ids=(),
            change_summary="[FAKE] synthetic chapter function",
            evidence_refs=(EvidenceRefLite("ev-ch-fn", "support"),) if labels else (),
        )


@dataclass
class FakeStorylinesRunner(BaseWholeBookModuleRunner):
    module_key: WholeBookModuleKey = WholeBookModuleKey.STORYLINES

    def _empty_dto(self) -> StorylinesResultDto:
        return empty_storylines_dto()

    def _default_synthetic_dto(self, fixture: Mapping[str, Any]) -> StorylinesResultDto:
        stype = str(fixture.get("storyline_type", "main"))
        if stype not in GENERAL_STORYLINE_TYPES:
            raise ValueError(f"non-general storyline type forbidden: {stype}")
        status = str(fixture.get("status", "active"))
        if status not in GENERAL_STORYLINE_STATUSES:
            raise ValueError(f"non-general storyline status forbidden: {status}")
        # Character lists must not be treated as storylines.
        if fixture.get("character_list_as_storyline") is True:
            raise ValueError("character lists cannot masquerade as storylines")
        return StorylinesResultDto(
            storyline_asset_id=int(fixture.get("storyline_asset_id", 501)),
            title="[FAKE] synthetic storyline",
            summary="[FAKE] synthetic summary",
            storyline_type=stype,
            chapter_range=(
                tuple(fixture["chapter_range"])  # type: ignore[arg-type]
                if "chapter_range" in fixture
                else (1, 3)
            ),
            key_event_ids=tuple(fixture.get("key_event_ids", (1,)) or ()),
            involved_entity_ids=tuple(fixture.get("involved_entity_ids", ()) or ()),
            relation_ids=tuple(fixture.get("relation_ids", ()) or ()),
            status=status,
            evidence_refs=(
                EvidenceRefLite("ev-sl-start", "support"),
                EvidenceRefLite("ev-sl-change", "context"),
                EvidenceRefLite("ev-sl-end", "support"),
            ),
        )


def build_first_four_fake_runners(
    *,
    prompt_pack: FakePromptPackServiceManifest | None = None,
    gateway: WholeBookProviderGateway | None = None,
) -> dict[WholeBookModuleKey, BaseWholeBookModuleRunner]:
    pack = prompt_pack or build_fake_prompt_pack()
    adapter = ModuleProviderExecutionAdapter(gateway=gateway or FakeProviderGateway())
    registry = build_default_module_spec_registry()
    common = {
        "registry": registry,
        "prompt_pack": pack,
        "provider_adapter": adapter,
    }
    return {
        WholeBookModuleKey.BOOK_OVERVIEW: FakeBookOverviewRunner(**common),
        WholeBookModuleKey.STRUCTURE_STAGES: FakeStructureStagesRunner(**common),
        WholeBookModuleKey.CHAPTER_FUNCTIONS: FakeChapterFunctionsRunner(**common),
        WholeBookModuleKey.STORYLINES: FakeStorylinesRunner(**common),
    }


def make_execution_request(
    *,
    module_key: WholeBookModuleKey = WholeBookModuleKey.BOOK_OVERVIEW,
    run_id: int = 1,
    book_id: int = 1,
    book_snapshot_id: int = 1,
    source_language: str = "zh",
    output_locale: str = "zh-CN",
    prompt_pack_ref: str = "fake.prompt_pack.first_four@0.0.1-fake",
    context_bundle_ref: str | None = None,
    configuration_fingerprint: str = "fake-config-fp",
    provider_policy: Mapping[str, Any] | None = None,
    budget_policy: Mapping[str, Any] | None = None,
    cancellation_ref: str | None = None,
    checkpoint_ref: str | None = None,
    analysis_mode: WholeBookAnalysisMode = WholeBookAnalysisMode.NATIVE,
    stage_key: WholeBookStageKey | str | None = None,
) -> PrivateEngineExecutionRequest:
    spec = get_module_spec(module_key)
    stage = stage_key or (spec.producer_stage_keys[0] if spec.producer_stage_keys else WholeBookStageKey.ANALYZE_STRUCTURE)
    return PrivateEngineExecutionRequest(
        run_id=run_id,
        stage_key=stage,
        attempt=0,
        book_id=book_id,
        book_snapshot_id=book_snapshot_id,
        analysis_mode=analysis_mode,
        requested_module_keys=(module_key,),
        resolved_module_keys=(module_key,),
        context_bundle_ref=context_bundle_ref or f"synthetic://bundle/{book_id}/{book_snapshot_id}",
        provider_policy=dict(provider_policy or {"provider_kind": "fake", "model_route": "fake"}),
        budget_policy=dict(budget_policy or {"fake": True}),
        output_locale=output_locale,
        source_language=source_language,
        configuration_fingerprint=configuration_fingerprint,
        prompt_pack_ref=prompt_pack_ref,
        cancellation_ref=cancellation_ref,
        checkpoint_ref=checkpoint_ref,
        mock=True,
        requested_at=datetime(2026, 7, 24, 0, 0, 0),
        run_stage_id=1,
    )


__all__ = [
    "DEFAULT_MODULE_SPEC_REGISTRY",
    "GENERAL_CHAPTER_FUNCTION_LABELS",
    "GENERAL_STORYLINE_STATUSES",
    "GENERAL_STORYLINE_TYPES",
    "BaseWholeBookModuleRunner",
    "FakeBookOverviewRunner",
    "FakeChapterFunctionsRunner",
    "FakeStorylinesRunner",
    "FakeStructureStagesRunner",
    "ModuleCheckpointBuilder",
    "ModuleCheckpointValidator",
    "ModuleProviderExecutionAdapter",
    "WholeBookModuleSpecRegistry",
    "build_default_module_spec_registry",
    "build_first_four_fake_runners",
    "empty_book_overview_dto",
    "empty_chapter_functions_dto",
    "empty_storylines_dto",
    "empty_structure_stages_dto",
    "make_execution_request",
]
