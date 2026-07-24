"""Private Whole-Book Analysis Runtime — Phase 2B-R Integration composition root.

Wires Agent S (Lab provider / runtime) + Agent T (four modules / Phase1B sink).
Default path remains Fake + Recording sink for tests.
Lab path (non-production only): create_lab_provider_gateway + private adapters
+ optional Phase1BCandidatePersistenceSink. Production must not construct Fake.
No global mutable production singleton. No License/Credential/frontend access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.private_engine_contract.context import ContextBundle
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineError,
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.private_engine_contract.evidence import EvidenceCandidate
from app.narrative_core.private_engine_contract.module_spec import FIRST_FOUR_MODULE_KEYS
from app.narrative_core.private_engine_contract.protocol import (
    PrivateEngineExecutionRequest,
    PrivateEngineExecutionResult,
    assert_request_has_no_forbidden_fields,
)
from app.narrative_core.private_engine_contract.quality import (
    DEFAULT_QUALITY_PROFILES,
    QualityProfileKey,
    WholeBookQualityProfile,
)
from app.narrative_core.services.auxiliary_context_source import (
    AuxiliaryContextSource,
    EmptyAuxiliaryContextSource,
)
from app.narrative_core.services.candidate_persistence_adapter import (
    CandidatePersistenceAdapter,
    Phase1BCandidatePersistenceSink,
    RecordingCandidatePersistenceSink,
    summarize_commands,
)
from app.narrative_core.services.evidence_validator_runtime_adapter import (
    DefaultEvidenceValidatorRuntimeAdapter,
)
from app.narrative_core.services.fake_private_whole_book_engine import FakePrivateWholeBookEngine
from app.narrative_core.services.fake_prompt_pack import (
    FakePromptPackServiceManifest,
    build_fake_prompt_pack,
    reject_fake_prompt_pack_in_production,
)
from app.narrative_core.services.paragraph_grouping_policy import (
    ParagraphGroupingPolicy,
    default_paragraph_grouping_policy,
)
from app.narrative_core.private_engine_contract.evidence import build_coverage_report
from app.narrative_core.private_engine_contract.manifest import fake_private_manifest
from app.narrative_core.private_engine_contract.prompt_pack import fake_prompt_pack_manifest
from app.narrative_core.services.private_engine_manifest_loader import (
    DefaultPrivateWholeBookEngineLoader,
    PrivateEngineManifestRepository,
    PromptPackCompatibilityValidator,
    PromptPackManifestRepository,
    write_fake_engine_package,
    write_fake_prompt_pack,
)
from app.narrative_core.services.private_engine_runtime_adapter import (
    PrivateWholeBookEngineRuntimeAdapter,
)
from app.narrative_core.services.private_engine_signature import (
    PrivateEnginePackageVerifier,
    PromptPackPackageVerifier,
    is_fake_or_test_engine_id,
)
from app.narrative_core.services.whole_book_candidate_builder import ModuleCandidateBuilder
from app.narrative_core.services.whole_book_context_bundle_mapper import WholeBookContextBundleMapper
from app.narrative_core.services.whole_book_context_pipeline import (
    ContextMode,
    DefaultWholeBookContextPipeline,
    EnhancedWholeBookContextProvider,
    HierarchicalContextPlanner,
    InMemoryContextBundleCache,
    NativeWholeBookContextProvider,
    WholeBookContextBundle,
    WholeBookContextBundleBuilder,
    WholeBookContextIndex,
    configuration_fingerprint,
)
from app.narrative_core.services.whole_book_context_units import (
    SnapshotTextResolver,
    UnitBuildConfig,
)
from app.narrative_core.services.whole_book_evaluation_harness import WholeBookEvaluationHarness
from app.narrative_core.services.whole_book_evidence_pipeline import (
    EvidenceCandidateBuilder,
    EvidenceCoverageCalculator,
)
from app.narrative_core.services.live_module_pipeline_diagnostics import (
    LiveModulePipelineDiagnostics,
    fingerprint_structured_output,
    infer_failure_boundary,
    merge_rejection_codes,
)
from app.narrative_core.services.output_ref_resolution import (
    build_candidate_output_refs,
    canonicalize_evidence_target_ref,
)
from app.narrative_core.services.quote_resolution import (
    SnapshotQuoteIndex,
    resolve_evidence_locator,
)
from app.narrative_core.services.whole_book_evidence_validator import (
    DefaultEvidenceValidator,
    EvidenceValidatorSnapshotView,
)
from app.narrative_core.services.whole_book_module_output_validator import (
    DefaultModuleOutputValidator,
    ModuleOutputValidationInput,
    ReferenceResolver,
)
from app.narrative_core.services.whole_book_module_runner import (
    BaseWholeBookModuleRunner,
    ModuleCheckpointBuilder,
    ModuleCheckpointValidator,
    ModuleProviderExecutionAdapter,
    WholeBookModuleSpecRegistry,
    build_default_module_spec_registry,
    build_first_four_fake_runners,
    build_private_module_runner_adapters,
    make_execution_request,
)
from app.narrative_core.services.whole_book_provider_gateway import (
    DefaultWholeBookProviderGateway,
    FakeProviderAdapter,
    NoCredentialFakeResolver,
    ProviderCredentialResolver,
    create_lab_provider_gateway,
)

RUNTIME_SCHEMA = "storylens.phase2b.private_analysis_runtime"
RUNTIME_VERSION = "1.0.0"


def try_load_first_four_private_runners(
    *,
    gateway: Any | None = None,
) -> Mapping[str, Any] | None:
    """Optional private package import — never vendors private sources into public tree."""

    try:
        from storylens_private_engine.modules import (  # type: ignore[import-not-found]
            build_first_four_private_runners,
        )
    except Exception:
        return None
    try:
        return build_first_four_private_runners(gateway=gateway)
    except Exception:
        return None


def _quality_profile(key: str | QualityProfileKey = "balanced") -> WholeBookQualityProfile:
    profile_key = key if isinstance(key, QualityProfileKey) else QualityProfileKey(key)
    return next(p for p in DEFAULT_QUALITY_PROFILES if p.profile_key == profile_key)


@dataclass(frozen=True, slots=True)
class ModulePipelineResultDTO:
    """Integration Result DTO — Fake/synthetic, never canonical."""

    schema: str
    version: str
    module_key: str
    module_version: str
    status: str
    context_bundle_hash: str
    configuration_fingerprint: str
    contract_bundle: ContextBundle
    runtime_bundle_mode: str
    engine_result: PrivateEngineExecutionResult
    validation: Mapping[str, Any]
    evidence_coverage: Mapping[str, Any]
    candidate_summary: Mapping[str, Any]
    checkpoint: Mapping[str, Any] | None
    usage: Mapping[str, Any]
    fake: bool = True
    synthetic: bool = True
    non_production: bool = True
    canonical: bool = False
    asset_written: bool = False
    network: bool = False
    model_called: bool = False
    formal_prompt: bool = False
    pipeline_diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class PrivateWholeBookAnalysisRuntime:
    """Phase 2B-R composition root (injectable; no production default Fake)."""

    schema: str = RUNTIME_SCHEMA
    version: str = RUNTIME_VERSION
    production: bool = False
    synthetic: bool = True
    non_production: bool = True
    lab_mode: bool = False
    private_modules_bound: bool = False

    # Agent P / S
    package_root: Path | None = None
    manifest_repository: PrivateEngineManifestRepository | None = None
    engine_package_verifier: PrivateEnginePackageVerifier | None = None
    prompt_pack_package_verifier: PromptPackPackageVerifier | None = None
    engine_loader: DefaultPrivateWholeBookEngineLoader | None = None
    runtime_adapter: PrivateWholeBookEngineRuntimeAdapter | None = None
    provider_gateway: DefaultWholeBookProviderGateway | None = None
    credential_resolver: ProviderCredentialResolver = field(default_factory=NoCredentialFakeResolver)
    fake_engine: FakePrivateWholeBookEngine | None = None
    fake_provider: FakeProviderAdapter | None = None

    # Agent Q
    session: Session | None = None
    grouping_policy: ParagraphGroupingPolicy = field(default_factory=default_paragraph_grouping_policy)
    context_pipeline: DefaultWholeBookContextPipeline | None = None
    text_resolver: SnapshotTextResolver | None = None
    context_index: WholeBookContextIndex | None = None
    context_bundle_builder: WholeBookContextBundleBuilder | None = None
    context_planner: HierarchicalContextPlanner = field(default_factory=HierarchicalContextPlanner)
    native_context_provider: NativeWholeBookContextProvider | None = None
    enhanced_context_provider: EnhancedWholeBookContextProvider | None = None
    evidence_builder: EvidenceCandidateBuilder = field(default_factory=EvidenceCandidateBuilder)
    evidence_validator: DefaultEvidenceValidator = field(default_factory=DefaultEvidenceValidator)
    evidence_coverage: EvidenceCoverageCalculator = field(default_factory=EvidenceCoverageCalculator)
    context_cache: InMemoryContextBundleCache = field(default_factory=InMemoryContextBundleCache)
    auxiliary_source: AuxiliaryContextSource = field(default_factory=EmptyAuxiliaryContextSource)

    # Agent R / T
    module_registry: WholeBookModuleSpecRegistry = field(default_factory=build_default_module_spec_registry)
    module_runners: dict[WholeBookModuleKey, BaseWholeBookModuleRunner] = field(default_factory=dict)
    output_validator: DefaultModuleOutputValidator | None = None
    candidate_builder: ModuleCandidateBuilder = field(default_factory=ModuleCandidateBuilder)
    checkpoint_builder: ModuleCheckpointBuilder = field(default_factory=ModuleCheckpointBuilder)
    checkpoint_validator: ModuleCheckpointValidator = field(default_factory=ModuleCheckpointValidator)
    evaluation_harness: WholeBookEvaluationHarness | None = None
    prompt_pack: FakePromptPackServiceManifest | None = None
    private_runners: Mapping[str, Any] | None = None
    fallback_to_fake: bool = True

    # Integration adapters
    bundle_mapper: WholeBookContextBundleMapper = field(default_factory=WholeBookContextBundleMapper)
    evidence_adapter: DefaultEvidenceValidatorRuntimeAdapter | None = None
    persistence: CandidatePersistenceAdapter = field(default_factory=RecordingCandidatePersistenceSink)

    # Runtime state
    contract_bundles: dict[str, ContextBundle] = field(default_factory=dict)
    runtime_bundles: dict[str, WholeBookContextBundle] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.production:
            # Production composition must never build Fake runtime.
            raise RuntimeError("PrivateWholeBookAnalysisRuntime forbids production=True Fake composition")
        if not self.non_production:
            raise RuntimeError("Phase 2B-R runtime must remain non_production")
        if not self.lab_mode and not self.synthetic:
            raise RuntimeError("default Fake path must remain synthetic")
        self.module_registry.validate()
        if self.prompt_pack is None:
            self.prompt_pack = build_fake_prompt_pack()
        if self.evidence_adapter is None:
            self.evidence_adapter = DefaultEvidenceValidatorRuntimeAdapter(validator=self.evidence_validator)
        if self.output_validator is None:
            self.output_validator = DefaultModuleOutputValidator(
                evidence_validator=self.evidence_adapter
            )
        if self.provider_gateway is None:
            if self.lab_mode:
                self.provider_gateway = create_lab_provider_gateway(dry_run=True)
                self.fake_provider = FakeProviderAdapter()
            else:
                self.fake_provider = self.fake_provider or FakeProviderAdapter()
                self.provider_gateway = DefaultWholeBookProviderGateway(
                    credential_resolver=self.credential_resolver,
                )
                # Ensure Fake adapter is the registered one we track.
                assert self.provider_gateway.registry is not None
                self.provider_gateway.registry.register(self.fake_provider)
        if self.fake_engine is None:
            self.fake_engine = FakePrivateWholeBookEngine()
        if self.runtime_adapter is None:
            self.runtime_adapter = PrivateWholeBookEngineRuntimeAdapter(
                engine=self.fake_engine,
                loader=self.engine_loader,
                prompt_pack=self.prompt_pack.manifest if self.prompt_pack else None,
            )
        if not self.module_runners:
            private = self.private_runners
            if private is None and self.lab_mode:
                private = try_load_first_four_private_runners(gateway=self.provider_gateway)
            if private:
                self.module_runners = build_private_module_runner_adapters(
                    private_runners=private,
                    prompt_pack=self.prompt_pack,
                    gateway=self.provider_gateway,
                    fallback_to_fake=self.fallback_to_fake,
                )
                self.private_modules_bound = True
                self.synthetic = False
            else:
                self.module_runners = build_first_four_fake_runners(
                    prompt_pack=self.prompt_pack,
                    gateway=self.provider_gateway,
                    output_validator=self.output_validator,
                )
                self.private_modules_bound = False
                self.synthetic = True
        else:
            for runner in self.module_runners.values():
                runner.output_validator = self.output_validator
                if runner.provider_adapter is None:
                    runner.provider_adapter = ModuleProviderExecutionAdapter(gateway=self.provider_gateway)
                else:
                    runner.provider_adapter.gateway = self.provider_gateway
        if self.evaluation_harness is None:
            self.evaluation_harness = WholeBookEvaluationHarness()
        if self.session is not None:
            self._wire_session(self.session)

    def _wire_session(self, session: Session) -> None:
        grouping = self.grouping_policy.to_grouping_dict()
        unit_config = UnitBuildConfig(grouping=grouping)
        self.context_pipeline = DefaultWholeBookContextPipeline(session, unit_config=unit_config)
        self.text_resolver = self.context_pipeline.text_resolver
        self.context_bundle_builder = WholeBookContextBundleBuilder(session)
        self.context_bundle_builder.pipeline._unit_config = unit_config
        self.context_bundle_builder.pipeline._builder = self.context_pipeline._builder
        self.native_context_provider = NativeWholeBookContextProvider(session)
        self.enhanced_context_provider = EnhancedWholeBookContextProvider(session)
        self.evidence_validator = DefaultEvidenceValidator(session=session)
        if self.evidence_adapter is not None:
            self.evidence_adapter.validator = self.evidence_validator

    def bind_session(self, session: Session) -> None:
        self.session = session
        self._wire_session(session)

    def _ensure_evidence_view(self, *, book_id: int, book_snapshot_id: int) -> None:
        """Register Snapshot view for Evidence Validator (Live ORM path)."""

        if self.session is None or self.evidence_adapter is None:
            return
        try:
            if getattr(self.evidence_validator, "_session", None) is None:
                self.evidence_validator = DefaultEvidenceValidator(session=self.session)
                self.evidence_adapter.validator = self.evidence_validator
            view = self.evidence_validator.build_view_from_session(
                book_id=int(book_id),
                book_snapshot_id=int(book_snapshot_id),
                known_output_refs=(),
            )
            self.register_evidence_view(view)
        except Exception:  # noqa: BLE001
            return

    def register_evidence_view(self, view: EvidenceValidatorSnapshotView) -> None:
        assert self.evidence_adapter is not None
        self.evidence_adapter.register_view(view)

    def _enrich_evidence_from_snapshot_view(
        self,
        evidence: Sequence[EvidenceCandidate],
        *,
        book_id: int,
        book_snapshot_id: int,
        module_key: str,
        registered_refs: Sequence[str],
        asset_candidates: Sequence[Any],
        selected_paragraph_ids: Sequence[int] | None = None,
        selected_chapter_ids: Sequence[int] | None = None,
        diagnostics: LiveModulePipelineDiagnostics | None = None,
    ) -> tuple[EvidenceCandidate, ...]:
        """Canonicalize target refs then resolve Context/Snapshot locators.

        Order: Output Ref Registry → target canonicalize → quote/key enrich.
        Does not invent locators; ambiguous matches are rejected (not first-hit).
        """

        if not evidence:
            return ()
        self._ensure_evidence_view(book_id=book_id, book_snapshot_id=book_snapshot_id)
        view = None
        if self.evidence_adapter is not None:
            view = self.evidence_adapter.views_by_snapshot.get(int(book_snapshot_id))
            if (
                view is None
                and self.evidence_adapter.snapshot_view is not None
                and int(self.evidence_adapter.snapshot_view.book_snapshot_id)
                == int(book_snapshot_id)
            ):
                view = self.evidence_adapter.snapshot_view

        quote_index: SnapshotQuoteIndex | None = None
        if self.session is not None:
            try:
                quote_index = SnapshotQuoteIndex.build_from_session(
                    self.session,
                    book_snapshot_id=int(book_snapshot_id),
                    view=view,
                    selected_paragraph_ids=selected_paragraph_ids,
                    selected_chapter_ids=selected_chapter_ids,
                )
            except Exception:  # noqa: BLE001
                quote_index = None

        enriched: list[EvidenceCandidate] = []
        for ev in evidence:
            provider_ref = str(ev.provider_output_ref or ev.target_output_ref or "")
            resolution = canonicalize_evidence_target_ref(
                {
                    "provider_output_ref": provider_ref,
                    "target_output_ref": provider_ref,
                    "target_module_key": str(
                        getattr(ev.target_module_key, "value", ev.target_module_key)
                    ),
                    "claim_key": None,
                    "candidate_id": ev.candidate_id,
                },
                module_key=module_key,
                registered_refs=registered_refs,
                asset_candidates=asset_candidates,
            )
            if diagnostics is not None:
                if resolution.resolution_status == "RESOLVED":
                    diagnostics.target_ref_resolved_count += 1
                else:
                    diagnostics.target_ref_rejected_count += 1
                    diagnostics.evidence_rejection_codes = merge_rejection_codes(
                        list(diagnostics.evidence_rejection_codes)
                        + [resolution.resolution_code]
                    )

            canonical = resolution.canonical_output_ref or ev.target_output_ref
            pid = ev.snapshot_paragraph_id
            chapter = ev.snapshot_chapter_id
            content_hash = ev.paragraph_content_hash
            stable = ev.stable_paragraph_id
            start = ev.start_offset
            end = ev.end_offset

            if quote_index is not None:
                quote_result = resolve_evidence_locator(
                    quote_index,
                    {
                        "evidence_key": ev.candidate_id,
                        "stable_paragraph_id": ev.stable_paragraph_id,
                        "snapshot_paragraph_id": ev.snapshot_paragraph_id,
                        "snapshot_chapter_id": ev.snapshot_chapter_id,
                        "preview": ev.preview,
                        "paragraph_content_hash": ev.paragraph_content_hash or None,
                        "start_offset": ev.start_offset,
                        "end_offset": ev.end_offset,
                    },
                    expected_snapshot_id=int(book_snapshot_id),
                )
                if quote_result.status == "resolved":
                    if diagnostics is not None:
                        diagnostics.quote_resolution_success_count += 1
                    pid = quote_result.paragraph_id
                    chapter = quote_result.chapter_id
                    stable = quote_result.stable_paragraph_id
                    content_hash = quote_result.paragraph_content_hash or content_hash
                    start = quote_result.start_offset
                    end = quote_result.end_offset
                elif (
                    ev.snapshot_paragraph_id is None
                    and not ev.stable_paragraph_id
                    and not (ev.preview or "").strip()
                ):
                    # No locator material — leave unresolved; validator will reject.
                    if diagnostics is not None:
                        diagnostics.quote_resolution_rejected_count += 1
                        if quote_result.failure_code:
                            diagnostics.evidence_rejection_codes = merge_rejection_codes(
                                list(diagnostics.evidence_rejection_codes)
                                + [quote_result.failure_code]
                            )
                elif quote_result.failure_code and quote_result.status == "rejected":
                    # Had locator hints but resolution failed — keep rejection code.
                    if diagnostics is not None:
                        diagnostics.quote_resolution_rejected_count += 1
                        diagnostics.evidence_rejection_codes = merge_rejection_codes(
                            list(diagnostics.evidence_rejection_codes)
                            + [quote_result.failure_code]
                        )
            elif view is not None:
                # Fallback: stable/paragraph id completion without quote index.
                stable_to_pid = {str(v): int(k) for k, v in view.stable_paragraph_ids.items()}
                for existing_pid in view.paragraph_ids:
                    stable_to_pid.setdefault(str(existing_pid), int(existing_pid))
                if pid is None and stable:
                    pid = stable_to_pid.get(str(stable))
                if pid is not None and chapter is None:
                    chapter = view.paragraph_chapter.get(int(pid))
                if pid is not None and (not content_hash or content_hash == "missing"):
                    content_hash = str(view.paragraph_hashes.get(int(pid)) or "")
                if pid is not None and not stable:
                    stable = view.stable_paragraph_ids.get(int(pid))
                if pid is not None and start is None and end is None:
                    para_len = view.paragraph_lengths.get(int(pid))
                    if para_len is not None and para_len > 0:
                        start, end = 0, int(para_len)

            enriched.append(
                EvidenceCandidate(
                    candidate_id=ev.candidate_id,
                    book_snapshot_id=ev.book_snapshot_id,
                    snapshot_chapter_id=chapter,
                    snapshot_paragraph_id=pid,
                    stable_paragraph_id=str(stable) if stable is not None else None,
                    paragraph_content_hash=str(content_hash or ""),
                    start_offset=start,
                    end_offset=end,
                    evidence_role=ev.evidence_role,
                    target_module_key=ev.target_module_key,
                    target_output_ref=str(canonical),
                    extraction_method=ev.extraction_method,
                    confidence=ev.confidence,
                    source_context_unit_id=ev.source_context_unit_id,
                    book_id=ev.book_id if ev.book_id is not None else book_id,
                    preview=ev.preview,
                    from_derived_summary=ev.from_derived_summary,
                    provider_output_ref=provider_ref or ev.provider_output_ref,
                )
            )
        return tuple(enriched)

    def build_native_context_bundle(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        module_keys: Sequence[str],
        provider_context_limit: int = 8_000,
        quality_profile_key: str = "balanced",
        source_language: str = "zh",
    ) -> tuple[WholeBookContextBundle, ContextBundle]:
        if self.context_bundle_builder is None:
            raise RuntimeError("session required for native context")
        profile = _quality_profile(quality_profile_key)
        specs = tuple(self.module_registry.get(k) for k in module_keys)
        grouping = self.grouping_policy.with_overrides(
            provider_context_limit=provider_context_limit,
            quality_profile_key=quality_profile_key,
        ).to_grouping_dict()
        runtime_bundle = self.context_bundle_builder.build(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            module_specs=specs,
            provider_context_limit=provider_context_limit,
            quality_profile=profile,
            source_language=source_language,
            analysis_mode=WholeBookAnalysisMode.NATIVE,
            mode=ContextMode.NATIVE,
            grouping=grouping,
        )
        contract = self.bundle_mapper.to_contract(runtime_bundle)
        from app.narrative_core.private_engine_contract.context import make_context_bundle_ref

        ref = make_context_bundle_ref(contract.bundle_hash)
        self.contract_bundles[ref] = contract
        self.contract_bundles[contract.bundle_hash] = contract
        self.runtime_bundles[ref] = runtime_bundle
        self._ensure_evidence_view(book_id=book_id, book_snapshot_id=book_snapshot_id)
        cache_key = InMemoryContextBundleCache.make_key(
            snapshot_content_hash=runtime_bundle.snapshot_content_hash,
            pipeline_version=runtime_bundle.pipeline_version,
            module_spec_versions=tuple(
                (
                    self.module_registry.get(k).module_key.value,
                    self.module_registry.get(k).module_version,
                )
                for k in module_keys
            ),
            quality_profile_key=runtime_bundle.quality_profile_key,
            configuration_fingerprint=runtime_bundle.configuration_fingerprint,
        )
        self.context_cache.put(cache_key, runtime_bundle)
        for runner in self.module_runners.values():
            runner.context_bundles[ref] = contract
            runner.context_bundles[contract.bundle_hash] = contract
        return runtime_bundle, contract

    def build_enhanced_context_bundle(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        module_keys: Sequence[str],
        provider_context_limit: int = 8_000,
        quality_profile_key: str = "balanced",
        source_language: str = "zh",
    ) -> tuple[WholeBookContextBundle, ContextBundle]:
        if self.enhanced_context_provider is None or self.context_bundle_builder is None:
            raise RuntimeError("session required for enhanced context")
        profile = _quality_profile(quality_profile_key)
        specs = tuple(self.module_registry.get(k) for k in module_keys)
        grouping = self.grouping_policy.with_overrides(
            provider_context_limit=provider_context_limit,
            quality_profile_key=quality_profile_key,
        ).to_grouping_dict()
        aux = self.auxiliary_source.load_auxiliary(
            book_id=book_id, book_snapshot_id=book_snapshot_id
        )
        warnings = list(aux.warnings)
        if aux.missing:
            warnings.append("enhanced_degraded_missing_aux")
        if aux.stale:
            warnings.append("enhanced_aux_stale_marked")
        runtime_bundle = self.context_bundle_builder.build(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            module_specs=specs,
            provider_context_limit=provider_context_limit,
            quality_profile=profile,
            source_language=source_language,
            analysis_mode=WholeBookAnalysisMode.ENHANCED,
            mode=ContextMode.ENHANCED,
            extra_units=aux.extra_units,
            warnings=tuple(warnings),
            grouping=grouping,
        )
        # Attach aux inventory into coverage notes without embedding bodies.
        notes = runtime_bundle.coverage.notes + tuple(
            f"aux:{r.kind}:{r.reason}:stale={r.stale}:excluded={r.excluded}" for r in aux.aux_refs
        )
        from dataclasses import replace

        from app.narrative_core.services.whole_book_context_pipeline import ContextCoverage

        coverage = ContextCoverage(
            chapter_units=runtime_bundle.coverage.chapter_units,
            scene_units=runtime_bundle.coverage.scene_units,
            paragraph_group_units=runtime_bundle.coverage.paragraph_group_units,
            evidence_window_units=runtime_bundle.coverage.evidence_window_units,
            derived_summary_units=runtime_bundle.coverage.derived_summary_units,
            levels_included=runtime_bundle.coverage.levels_included,
            degraded=True if aux.missing or aux.stale else runtime_bundle.coverage.degraded,
            notes=notes,
        )
        runtime_bundle = replace(runtime_bundle, coverage=coverage, warnings=tuple(warnings))
        contract = self.bundle_mapper.to_contract(runtime_bundle)
        from app.narrative_core.private_engine_contract.context import make_context_bundle_ref

        ref = make_context_bundle_ref(contract.bundle_hash)
        self.contract_bundles[ref] = contract
        self.contract_bundles[contract.bundle_hash] = contract
        self.runtime_bundles[ref] = runtime_bundle
        self._ensure_evidence_view(book_id=book_id, book_snapshot_id=book_snapshot_id)
        for runner in self.module_runners.values():
            runner.context_bundles[ref] = contract
            runner.context_bundles[contract.bundle_hash] = contract
        return runtime_bundle, contract

    def prepare_engine_packages(self, package_root: Path) -> Mapping[str, Any]:
        """Write Fake signed engine + prompt pack under package_root (test only)."""

        self.package_root = package_root
        engine_manifest = fake_private_manifest(signed=True, non_production=True)
        engine_dir = write_fake_engine_package(package_root, engine_manifest, include_signature=True)
        pack_manifest = fake_prompt_pack_manifest().manifest
        pack_dir = write_fake_prompt_pack(package_root, pack_manifest, include_signature=True)
        self.manifest_repository = PrivateEngineManifestRepository(package_root)
        self.engine_package_verifier = PrivateEnginePackageVerifier(production=False)
        self.prompt_pack_package_verifier = PromptPackPackageVerifier(production=False)
        self.engine_loader = DefaultPrivateWholeBookEngineLoader(
            repository=self.manifest_repository,
            verifier=self.engine_package_verifier,
            production=False,
        )
        handle = self.engine_loader.load(engine_manifest.engine_id)
        engine_id = handle.engine_id
        self.fake_engine = self.engine_loader.get_loaded_engine(engine_id) or FakePrivateWholeBookEngine(
            manifest=engine_manifest
        )
        self.runtime_adapter = PrivateWholeBookEngineRuntimeAdapter(
            engine=self.fake_engine,
            loader=self.engine_loader,
            prompt_pack_repository=PromptPackManifestRepository(package_root),
            prompt_pack_validator=PromptPackCompatibilityValidator(),
            prompt_pack=self.prompt_pack.manifest if self.prompt_pack else None,
        )
        return {
            "engine_ref": str(engine_dir),
            "prompt_pack_ref": str(pack_dir),
            "engine_id": engine_id,
            "fake": True,
            "signed": True,
            "non_production": True,
        }

    def execute_module_pipeline(
        self,
        *,
        module_key: WholeBookModuleKey | str,
        book_id: int,
        book_snapshot_id: int,
        run_id: int = 1,
        run_stage_id: int | None = None,
        context_bundle_ref: str,
        configuration_fingerprint_value: str,
        provider_policy: Mapping[str, Any] | None = None,
        source_language: str = "zh",
        output_locale: str = "zh-CN",
        analysis_mode: WholeBookAnalysisMode = WholeBookAnalysisMode.NATIVE,
        require_evidence_for_acceptance: bool = False,
        persist: bool = True,
    ) -> ModulePipelineResultDTO:
        key = module_key if isinstance(module_key, WholeBookModuleKey) else WholeBookModuleKey(module_key)
        if key not in FIRST_FOUR_MODULE_KEYS and key not in self.module_runners:
            raise private_engine_error(PrivateEngineErrorCode.MODULE_NOT_SUPPORTED)
        runner = self.module_runners[key]
        pack = self.prompt_pack
        assert pack is not None
        from app.narrative_core.private_engine_contract.context import (
            make_context_bundle_ref,
            parse_context_bundle_hash,
        )

        # Fail closed on legacy / unknown refs — no silent multi-key aliasing.
        try:
            if str(context_bundle_ref).startswith("bundle:"):
                raise private_engine_error(
                    PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                    detail_code="LEGACY_BUNDLE_RUN_ID_REF_FORBIDDEN",
                )
            # Accept either full ref or raw hash (hash must already be registered).
            if context_bundle_ref in self.contract_bundles:
                resolved_ref = str(context_bundle_ref)
            else:
                resolved_ref = make_context_bundle_ref(parse_context_bundle_hash(str(context_bundle_ref)))
        except ValueError as exc:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="CONTEXT_BUNDLE_REF_INVALID",
            ) from exc
        contract = self.contract_bundles.get(resolved_ref)
        if contract is None:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="CONTEXT_BUNDLE_REF_NOT_REGISTERED",
            )
        if int(contract.book_snapshot_id) != int(book_snapshot_id) or int(contract.book_id) != int(
            book_id
        ):
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="CONTEXT_BUNDLE_SNAPSHOT_MISMATCH",
            )
        context_bundle_ref = resolved_ref
        runner.context_bundles[context_bundle_ref] = contract
        runner.context_bundles[contract.bundle_hash] = contract

        request = make_execution_request(
            module_key=key,
            run_id=run_id,
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            source_language=source_language,
            output_locale=output_locale,
            prompt_pack_ref=f"{pack.manifest.prompt_pack_id}@{pack.manifest.prompt_pack_version}",
            context_bundle_ref=context_bundle_ref,
            configuration_fingerprint=configuration_fingerprint_value,
            provider_policy=provider_policy
            or (
                {"provider_kind": "fake", "model_route": "fake-route"}
                if not self.private_modules_bound
                else {
                    "provider_kind": "fake",
                    "model_route": "lab-fake-route",
                    "quality_profile": "balanced",
                }
            ),
            analysis_mode=analysis_mode,
        )
        assert_request_has_no_forbidden_fields(request)
        assert self.runtime_adapter is not None
        # Adapter validates request / prompt / budget / cancel boundaries first.
        translated = self.runtime_adapter.translate_request(request)

        # Fake engine health must not execute analysis.
        _ = self.runtime_adapter.health_check()

        # Module runner path (DTO-shaped) via Provider Gateway.
        engine_result = runner.execute(translated)
        provider_policy = dict(provider_policy or {})
        provider_attempt = dict(provider_policy.get("provider_attempt") or {})
        provider_backed = bool(provider_policy.get("provider_backed"))
        if provider_backed:
            # Live / FAKE_HTTP_TEST: never mark synthetic from Fake adapter defaults.
            usage_flags = {
                "fake": False,
                "synthetic": False,
                "provider_backed": True,
                "private_modules_bound": self.private_modules_bound,
                "lab_mode": self.lab_mode,
                "engine_kind": str(
                    (engine_result.usage or {}).get("engine_kind")
                    or provider_attempt.get("engine_kind")
                    or "PRIVATE_REAL"
                ),
                "transport_kind": provider_attempt.get("transport_kind")
                or (engine_result.usage or {}).get("transport_kind"),
                "provider_request_id": provider_attempt.get("provider_request_id")
                or (engine_result.usage or {}).get("provider_request_id"),
            }
        else:
            usage_flags = {
                "fake": not self.private_modules_bound,
                "synthetic": not self.private_modules_bound
                or bool((engine_result.module_outputs or {}).get("synthetic", False)),
                "private_modules_bound": self.private_modules_bound,
                "lab_mode": self.lab_mode,
                "provider_backed": False,
            }
        guarded = self.runtime_adapter.translate_result(
            PrivateEngineExecutionResult(
                schema=engine_result.schema,
                version=engine_result.version,
                engine_id=engine_result.engine_id,
                engine_version=engine_result.engine_version,
                stage_key=engine_result.stage_key,
                attempt=engine_result.attempt,
                status=engine_result.status,
                module_outputs=engine_result.module_outputs,
                evidence_candidates=engine_result.evidence_candidates,
                asset_candidates=engine_result.asset_candidates,
                relation_candidates=engine_result.relation_candidates,
                conflict_candidates=engine_result.conflict_candidates,
                checkpoint=engine_result.checkpoint,
                usage={**dict(engine_result.usage), **usage_flags},
                warnings=engine_result.warnings,
                validation_summary=engine_result.validation_summary,
                generated_at=engine_result.generated_at,
            )
        )

        # --- CHG-055 pipeline: Candidate Registry → target resolve → enrich → validate → persist
        diag = LiveModulePipelineDiagnostics(
            module_key=key.value,
            run_id=int(run_id),
            stage_id=int(run_stage_id) if run_stage_id is not None else None,
        )
        structured = dict(
            provider_policy.get("provider_structured_output")
            or (guarded.module_outputs or {})
            or {}
        )
        diag.structured_output_present = bool(structured)
        diag.structured_output_schema = str(
            structured.get("schema")
            or (guarded.module_outputs or {}).get("schema")
            or "BookOverviewResultDto"
        )
        diag.structured_output_fingerprint = fingerprint_structured_output(structured)
        outputs = dict(guarded.module_outputs or {})
        claim_count = 0
        for claim_name in ("logline", "overview", "premise", "primary_conflict"):
            if str(outputs.get(claim_name) or structured.get(claim_name) or "").strip():
                claim_count += 1
        diag.claim_count = claim_count
        provider_refs = outputs.get("evidence_refs") or structured.get("evidence_refs") or ()
        diag.provider_evidence_ref_count = len(tuple(provider_refs or ()))
        diag.private_candidate_count = len(tuple(guarded.asset_candidates or ()))
        diag.public_candidate_count = len(tuple(guarded.asset_candidates or ()))
        diag.evidence_coercion_input_count = len(tuple(guarded.evidence_candidates or ()))

        registered_refs = build_candidate_output_refs(
            module_key=key.value,
            asset_candidates=tuple(guarded.asset_candidates or ()),
            extra_refs=tuple(
                str(x) for x in outputs.get("resolver_output_refs", ()) or ()
            ),
        )
        diag.candidate_output_ref_count = len(registered_refs)

        selected_paragraph_ids = tuple(
            int(x) for x in (getattr(contract, "selected_paragraph_ids", None) or ())
        ) or None
        selected_chapter_ids = tuple(
            int(x) for x in (getattr(contract, "selected_chapter_ids", None) or ())
        ) or None
        # Context Bundle may expose paragraph ids via units metadata.
        if selected_paragraph_ids is None:
            unit_pids: list[int] = []
            for unit in getattr(contract, "units", ()) or ():
                for pid in getattr(unit, "snapshot_paragraph_ids", ()) or ():
                    try:
                        unit_pids.append(int(pid))
                    except (TypeError, ValueError):
                        continue
            selected_paragraph_ids = tuple(unit_pids) or None

        assert self.output_validator is not None
        evidence = self._enrich_evidence_from_snapshot_view(
            tuple(e for e in guarded.evidence_candidates if isinstance(e, EvidenceCandidate)),
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            module_key=key.value,
            registered_refs=registered_refs,
            asset_candidates=tuple(guarded.asset_candidates or ()),
            selected_paragraph_ids=selected_paragraph_ids,
            selected_chapter_ids=selected_chapter_ids,
            diagnostics=diag,
        )
        diag.evidence_coercion_output_count = len(evidence)

        # Keep enriched evidence on the guarded result for candidate builder.
        guarded = PrivateEngineExecutionResult(
            schema=guarded.schema,
            version=guarded.version,
            engine_id=guarded.engine_id,
            engine_version=guarded.engine_version,
            stage_key=guarded.stage_key,
            attempt=guarded.attempt,
            status=guarded.status,
            module_outputs=guarded.module_outputs,
            evidence_candidates=evidence,
            asset_candidates=guarded.asset_candidates,
            relation_candidates=guarded.relation_candidates,
            conflict_candidates=guarded.conflict_candidates,
            checkpoint=guarded.checkpoint,
            usage=guarded.usage,
            warnings=guarded.warnings,
            validation_summary=guarded.validation_summary,
            generated_at=guarded.generated_at,
        )
        validation = self.output_validator.validate(
            ModuleOutputValidationInput(
                module_key=key,
                module_outputs=guarded.module_outputs,
                evidence_candidates=evidence,
                book_id=book_id,
                book_snapshot_id=book_snapshot_id,
                expected_book_id=book_id,
                expected_book_snapshot_id=book_snapshot_id,
                resolver=ReferenceResolver(
                    asset_ids=frozenset(
                        int(x) for x in guarded.module_outputs.get("resolver_asset_ids", ()) or ()
                    ),
                    entity_ids=frozenset(
                        int(x) for x in guarded.module_outputs.get("resolver_entity_ids", ()) or ()
                    ),
                    storyline_ids=frozenset(
                        int(x) for x in guarded.module_outputs.get("resolver_storyline_ids", ()) or ()
                    ),
                    chapter_ids=frozenset(
                        int(x) for x in guarded.module_outputs.get("resolver_chapter_ids", ()) or ()
                    ),
                    output_refs=frozenset(registered_refs),
                ),
                require_evidence_for_acceptance=require_evidence_for_acceptance,
            )
        )
        if validation.evidence_valid:
            diag.evidence_valid_count = len(evidence)
            diag.evidence_rejected_count = 0
        else:
            diag.evidence_valid_count = 0
            diag.evidence_rejected_count = max(1, len(evidence))
            # Pull safe codes from validator when available.
            issues = getattr(getattr(validation, "evidence_report", None), "issues", ()) or ()
            codes = [str(getattr(i, "code", "") or "") for i in issues]
            if not codes and validation.error_code:
                codes = [str(validation.error_code)]
            diag.evidence_rejection_codes = merge_rejection_codes(
                list(diag.evidence_rejection_codes) + codes
            )
            if not diag.failure_boundary:
                diag.failure_boundary = "EVIDENCE_VALIDATION_REJECTED"
                diag.failure_code = str(validation.error_code or "EVIDENCE_REJECTED")

        coverage = build_coverage_report(
            module_key=key.value,
            required_claims=int(guarded.module_outputs.get("required_claims", 1) or 1),
            evidenced_claims=int(
                guarded.module_outputs.get(
                    "evidenced_claims", len(evidence) if validation.evidence_valid else 0
                )
                or 0
            ),
            missing_target_refs=tuple(validation.invalid_refs),
        )
        # Keep Q calculator available for claim-binding harnesses (not unused).
        _ = self.evidence_coverage
        # Candidate commands — only when accepted (force_accept fixtures for Fake E2E).
        built = self.candidate_builder.build(
            result=guarded,
            validation=validation,
            run_id=run_id,
            run_stage_id=run_stage_id,
            book_snapshot_id=book_snapshot_id,
            module_key=key.value,
            module_version=runner.spec.module_version,
            configuration_fingerprint=configuration_fingerprint_value,
            prompt_pack_id=pack.manifest.prompt_pack_id,
            prompt_pack_version=pack.manifest.prompt_pack_version,
            mock=not self.private_modules_bound,
        )
        diag.candidate_command_count = len(tuple(getattr(built, "asset_commands", ()) or ()))
        diag.evidence_command_count = len(tuple(getattr(built, "evidence_commands", ()) or ()))
        if getattr(built, "rejected", False) and diag.candidate_command_count < 1:
            diag.failure_boundary = diag.failure_boundary or "CANDIDATE_COMMAND_EMPTY"
            diag.failure_code = diag.failure_code or "CANDIDATE_BUILD_REJECTED"

        persist_summary: Mapping[str, Any] = {"recorded": False}
        if persist:
            # ORM only after evidence validated / commands built.
            if validation.accepted and not getattr(built, "rejected", False):
                diag.persistence_attempted = True
                diag.transaction_started = True
                try:
                    persist_summary = self.persistence.persist_commands(built)
                    if persist_summary.get("orm_transaction_committed") or persist_summary.get(
                        "orm_written"
                    ):
                        diag.transaction_committed = True
                    if persist_summary.get("rejected") or persist_summary.get("deny_reason"):
                        diag.transaction_rolled_back = True
                        diag.transaction_committed = False
                        diag.failure_boundary = "ORM_TRANSACTION_ROLLBACK"
                        diag.failure_code = str(
                            persist_summary.get("deny_reason") or "PERSIST_DENIED"
                        )
                except Exception as exc:  # noqa: BLE001
                    diag.transaction_rolled_back = True
                    diag.transaction_committed = False
                    diag.failure_boundary = "ORM_TRANSACTION_ROLLBACK"
                    diag.failure_code = type(exc).__name__
                    raise
            else:
                persist_summary = {
                    "recorded": False,
                    "orm_written": False,
                    "persistence_complete": False,
                    "candidate_written": False,
                    "evidence_written": False,
                    "artifact_written": False,
                    "skipped_reason": "evidence_or_candidate_rejected",
                }
                diag.persistence_attempted = False
                diag.transaction_started = False

        diag.asset_written_count = int(persist_summary.get("asset_count") or 0)
        diag.version_written_count = int(
            persist_summary.get("asset_count")
            or len(persist_summary.get("asset_version_ids") or ())
            or 0
        )
        diag.evidence_written_count = int(persist_summary.get("evidence_count") or 0)
        diag.artifact_written_count = (
            1 if persist_summary.get("artifact_written") or persist_summary.get("has_stage_artifact") else 0
        )
        diag.failure_boundary = infer_failure_boundary(diag)
        if diag.failure_boundary and not diag.failure_code:
            diag.failure_code = diag.failure_boundary

        runtime_bundle = self.runtime_bundles.get(context_bundle_ref)
        is_fake = not self.private_modules_bound
        return ModulePipelineResultDTO(
            schema="storylens.phase2b.module_pipeline_result",
            version="1.0.0",
            module_key=key.value,
            module_version=runner.spec.module_version,
            status=guarded.status,
            context_bundle_hash=contract.bundle_hash,
            configuration_fingerprint=configuration_fingerprint_value,
            contract_bundle=contract,
            runtime_bundle_mode=runtime_bundle.mode.value if runtime_bundle else "unknown",
            engine_result=guarded,
            validation={
                "accepted": validation.accepted,
                "schema_valid": validation.schema_valid,
                "references_valid": validation.references_valid,
                "evidence_valid": validation.evidence_valid,
                "snapshot_valid": validation.snapshot_valid,
                "duplicate_summary": validation.duplicate_summary,
                "conflict_summary": validation.conflict_summary,
                "error_code": validation.error_code,
                "warnings": list(validation.warnings),
            },
            evidence_coverage={
                "required_claims": coverage.required_claims,
                "evidenced_claims": coverage.evidenced_claims,
                "coverage_ratio": coverage.coverage_ratio,
                "incomplete": coverage.incomplete,
            },
            candidate_summary={**summarize_commands(built), "persist": dict(persist_summary)},
            checkpoint=None
            if guarded.checkpoint is None
            else {
                "protocol_version": guarded.checkpoint.protocol_version,
                "engine_id": guarded.checkpoint.engine_id,
                "engine_version": guarded.checkpoint.engine_version,
                "module_key": guarded.checkpoint.module_key,
                "module_version": guarded.checkpoint.module_version,
                "stage_key": guarded.checkpoint.stage_key,
                "attempt": guarded.checkpoint.attempt,
                "prompt_pack_id": guarded.checkpoint.prompt_pack_id,
                "prompt_pack_version": guarded.checkpoint.prompt_pack_version,
                "context_bundle_hash": guarded.checkpoint.context_bundle_hash,
                "configuration_fingerprint": guarded.checkpoint.configuration_fingerprint,
                "book_snapshot_id": guarded.checkpoint.book_snapshot_id,
                "integrity_hash": guarded.checkpoint.integrity_hash,
            },
            usage=dict(guarded.usage),
            fake=is_fake,
            synthetic=is_fake or bool(guarded.module_outputs.get("synthetic", False)),
            non_production=True,
            canonical=False,
            asset_written=bool(persist_summary.get("orm_written")),
            network=False,
            model_called=False,
            formal_prompt=False,
            pipeline_diagnostics=diag.to_safe_dict(),
        )

    def assert_production_isolation(self) -> Mapping[str, Any]:
        """Prove production gates reject Fake engine/pack and never Mock-fallback."""

        from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
        from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
        from app.narrative_core.run_shell_contract.private_engine_lab import (
            WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
        )
        from app.narrative_core.services.whole_book_engine_registry import (
            PRODUCTION_DEFAULT_ENGINE_ID,
        )

        errors: list[str] = []
        # Production loader must reject Fake.
        if self.package_root is not None:
            prod_loader = DefaultPrivateWholeBookEngineLoader(
                repository=PrivateEngineManifestRepository(self.package_root),
                production=True,
            )
            try:
                prod_loader.load("fake.signed.private_engine")
                errors.append("production_loaded_fake_engine")
            except PrivateEngineError as exc:
                if exc.code != PrivateEngineErrorCode.PRIVATE_ENGINE_NOT_FOUND:
                    errors.append(f"unexpected_prod_engine_error:{exc.code}")
        if self.prompt_pack is not None:
            try:
                reject_fake_prompt_pack_in_production(self.prompt_pack, production=True)
                errors.append("production_accepted_fake_prompt_pack")
            except RuntimeError:
                pass
        try:
            create_private_whole_book_analysis_runtime(production=True)
            errors.append("production_fake_runtime_constructed")
        except RuntimeError:
            pass
        if PRODUCTION_DEFAULT_ENGINE_ID is not None:
            errors.append("PRODUCTION_DEFAULT_ENGINE_ID_not_none")
        if WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is not True:
            errors.append("WHOLE_BOOK_RUNS_ENDPOINT_DISABLED_not_true")
        if WHOLE_BOOK_MOCK_LAB_ENABLED is not False:
            errors.append("WHOLE_BOOK_MOCK_LAB_ENABLED_not_false")
        if WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED is not False:
            errors.append("WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED_not_false")
        return {
            "ok": not errors,
            "errors": errors,
            "production_default_engine_id": PRODUCTION_DEFAULT_ENGINE_ID,
            "whole_book_runs_endpoint_disabled": WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
            "mock_lab_enabled_default": WHOLE_BOOK_MOCK_LAB_ENABLED,
            "private_engine_lab_enabled_default": WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
            "fake_runtime_forbidden_in_production": True,
            "network": False,
            "model_called": False,
            "formal_prompt": False,
        }


def create_private_whole_book_analysis_runtime(
    *,
    session: Session | None = None,
    production: bool = False,
    package_root: Path | None = None,
    grouping_policy: ParagraphGroupingPolicy | None = None,
    auxiliary_source: AuxiliaryContextSource | None = None,
    persistence: CandidatePersistenceAdapter | None = None,
    lab_mode: bool = False,
    private_runners: Mapping[str, Any] | None = None,
    use_phase1b_persistence: bool = False,
    book_id: int | None = None,
    lab_dry_run: bool = True,
    fallback_to_fake: bool = True,
    require_private_real: bool = False,
) -> PrivateWholeBookAnalysisRuntime:
    """Factory — tests inject isolated runtimes. Production must not call with Fake.

    Default: Fake runners + Recording sink.
    Lab mode: create_lab_provider_gateway + optional private runners + optional Phase1B sink.
    """

    if production:
        raise RuntimeError("production must not construct Fake PrivateWholeBookAnalysisRuntime")

    sink: CandidatePersistenceAdapter
    if persistence is not None:
        sink = persistence
    elif use_phase1b_persistence:
        if session is None or book_id is None:
            raise ValueError("Phase1B persistence requires session and book_id")
        sink = Phase1BCandidatePersistenceSink(session, book_id=book_id)
    else:
        sink = RecordingCandidatePersistenceSink()

    gateway = None
    if lab_mode:
        gateway = create_lab_provider_gateway(dry_run=lab_dry_run)

    effective_private_runners = private_runners
    if require_private_real:
        effective_private_runners = try_load_first_four_private_runners(gateway=gateway)
        if effective_private_runners is None:
            raise RuntimeError("LIVE_PRIVATE_ENGINE_PACKAGE_MISSING")
        fallback_to_fake = False

    # Lab or explicit private runners: still non-production; synthetic flipped when bound.
    effective_lab = bool(lab_mode or effective_private_runners is not None)
    runtime = PrivateWholeBookAnalysisRuntime(
        production=False,
        synthetic=True,
        non_production=True,
        lab_mode=effective_lab,
        grouping_policy=grouping_policy or default_paragraph_grouping_policy(),
        auxiliary_source=auxiliary_source or EmptyAuxiliaryContextSource(),
        persistence=sink,
        provider_gateway=gateway,
        private_runners=effective_private_runners,
        fallback_to_fake=fallback_to_fake,
    )
    if session is not None:
        runtime.bind_session(session)
    if package_root is not None:
        runtime.prepare_engine_packages(package_root)
    if require_private_real:
        if not runtime.private_modules_bound:
            raise RuntimeError("LIVE_SYNTHETIC_ENGINE_FORBIDDEN")
        bound_engine_id = ""
        private = runtime.private_runners or {}
        for runner in private.values():
            bound_engine_id = str(getattr(runner, "engine_id", "") or "")
            if bound_engine_id:
                break
        if not bound_engine_id or is_fake_or_test_engine_id(bound_engine_id):
            raise RuntimeError("LIVE_SYNTHETIC_ENGINE_FORBIDDEN")
    return runtime


def create_lab_private_whole_book_analysis_runtime(
    *,
    session: Session | None = None,
    book_id: int | None = None,
    use_phase1b_persistence: bool = True,
    lab_dry_run: bool = True,
    private_runners: Mapping[str, Any] | None = None,
    fallback_to_fake: bool = True,
    require_private_real: bool = False,
) -> PrivateWholeBookAnalysisRuntime:
    """Private Engine Lab composition — non-production only; no live calls by default."""

    return create_private_whole_book_analysis_runtime(
        session=session,
        lab_mode=True,
        lab_dry_run=lab_dry_run,
        private_runners=private_runners,
        use_phase1b_persistence=use_phase1b_persistence and session is not None and book_id is not None,
        book_id=book_id,
        fallback_to_fake=fallback_to_fake,
        require_private_real=require_private_real,
    )


# Aliases matching composition naming options in the brief.
PrivateEngineRuntimeContainer = PrivateWholeBookAnalysisRuntime
PrivateWholeBookRuntime = PrivateWholeBookAnalysisRuntime


PRIVATE_WHOLE_BOOK_RUNTIME_ALIASES = (
    "PrivateWholeBookAnalysisRuntime",
    "PrivateEngineRuntimeContainer",
    "PrivateWholeBookRuntime",
)

__all__ = [
    "ModulePipelineResultDTO",
    "PRIVATE_WHOLE_BOOK_RUNTIME_ALIASES",
    "PrivateEngineRuntimeContainer",
    "PrivateWholeBookAnalysisRuntime",
    "PrivateWholeBookRuntime",
    "RUNTIME_SCHEMA",
    "RUNTIME_VERSION",
    "create_lab_private_whole_book_analysis_runtime",
    "create_private_whole_book_analysis_runtime",
    "try_load_first_four_private_runners",
]
