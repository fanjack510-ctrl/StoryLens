"""Formal Private Provider Input Bundle resolver adapter (Phase 2B-R1 CHG-049).

Bridges Snapshot/ContextPipeline → private PrivateProviderInputBundleResolver →
public ProviderInputBundle for Lab Preflight/Estimate/Execute.

Fail-closed: missing private package or unbound session raises — no silent Fake fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.narrative_core.enums import WholeBookAnalysisMode
from app.narrative_core.private_engine_contract.data_transfer import (
    DataTransferManifestBuilder,
    WholeBookDataTransferManifest,
)
from app.narrative_core.private_engine_contract.provider_estimate import ProviderEstimateResult
from app.narrative_core.private_engine_contract.provider_input import (
    ProviderChatMessage,
    ProviderInputBundle,
    SourceDataBlock,
)
from app.narrative_core.private_engine_contract.quality import (
    DEFAULT_QUALITY_PROFILES,
    QualityProfileKey,
    WholeBookQualityProfile,
)
from app.narrative_core.services.whole_book_context_bundle_mapper import WholeBookContextBundleMapper
from app.narrative_core.services.whole_book_context_pipeline import (
    ContextMode,
    DefaultWholeBookContextPipeline,
    UnitBuildConfig,
    WholeBookContextBundleBuilder,
)
from app.narrative_core.services.whole_book_module_runner import build_default_module_spec_registry
from app.narrative_core.services.whole_book_provider_estimate_service import (
    WholeBookProviderEstimateService,
)


def _quality_profile(key: str = "balanced") -> WholeBookQualityProfile:
    profile_key = QualityProfileKey(key)
    return next(p for p in DEFAULT_QUALITY_PROFILES if p.profile_key == profile_key)


class FormalPrivateResolverUnavailable(RuntimeError):
    """Raised when the private formal resolver cannot be constructed."""


def load_private_provider_input_bundle_resolver(*, text_resolver: Any = None) -> Any:
    """Import private formal resolver — fail closed, never return Fake."""

    try:
        from storylens_private_engine.provider_input import (  # type: ignore[import-not-found]
            PrivateProviderInputBundleResolver,
        )
    except Exception as exc:  # noqa: BLE001 — fail closed on any import/wiring error
        raise FormalPrivateResolverUnavailable(
            "PrivateProviderInputBundleResolver unavailable; "
            "formal Lab runtime refuses Fake silent fallback"
        ) from exc
    return PrivateProviderInputBundleResolver(text_resolver=text_resolver)


@dataclass
class FormalPrivateProviderInputBundleResolverAdapter:
    """Session-bound adapter implementing the Lab estimate resolver surface."""

    session: Session | None = None
    estimate_service: WholeBookProviderEstimateService = field(
        default_factory=WholeBookProviderEstimateService
    )
    manifest_builder: DataTransferManifestBuilder = field(default_factory=DataTransferManifestBuilder)
    module_registry: Any = field(default_factory=build_default_module_spec_registry)
    bundle_mapper: WholeBookContextBundleMapper = field(default_factory=WholeBookContextBundleMapper)
    provider_context_limit: int = 120_000
    _pipeline: DefaultWholeBookContextPipeline | None = field(default=None, repr=False)
    _bundle_builder: WholeBookContextBundleBuilder | None = field(default=None, repr=False)
    _private: Any | None = field(default=None, repr=False)
    is_fake: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        # Construct private resolver eagerly so missing package fails at composition time.
        self._private = load_private_provider_input_bundle_resolver(text_resolver=None)
        if self.session is not None:
            self.bind_session(self.session)

    def bind_session(self, session: Session) -> None:
        self.session = session
        self._pipeline = DefaultWholeBookContextPipeline(session, unit_config=UnitBuildConfig())
        self._bundle_builder = WholeBookContextBundleBuilder(session)
        # Share unit builder so text refs resolve consistently.
        self._bundle_builder.pipeline._builder = self._pipeline._builder  # noqa: SLF001
        text_resolver = self._pipeline.text_resolver

        def _resolve_text(uri: str) -> str:
            return text_resolver.resolve(uri)

        self._private = load_private_provider_input_bundle_resolver(text_resolver=_resolve_text)

    def _require_ready(self) -> None:
        if self.session is None or self._pipeline is None or self._bundle_builder is None:
            raise FormalPrivateResolverUnavailable(
                "formal resolver requires a bound SQLAlchemy session"
            )
        if self._private is None:
            raise FormalPrivateResolverUnavailable("private resolver not loaded")

    def _build_contract_bundle(
        self,
        *,
        book_id: int,
        book_snapshot_id: int,
        module_key: str,
        quality_profile: str,
        source_language: str,
    ) -> Any:
        self._require_ready()
        assert self._bundle_builder is not None
        profile = _quality_profile(quality_profile)
        spec = self.module_registry.get(module_key)
        runtime_bundle = self._bundle_builder.build(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            module_specs=(spec,),
            provider_context_limit=self.provider_context_limit,
            quality_profile=profile,
            source_language=source_language,
            analysis_mode=WholeBookAnalysisMode.NATIVE,
            mode=ContextMode.NATIVE,
        )
        return self.bundle_mapper.to_contract(runtime_bundle)

    def resolve(
        self,
        *,
        request_id: str,
        book_id: int,
        book_snapshot_id: int,
        module_key: str,
        context_bundle_hash: str,
        provider_key: str,
        model_id: str,
        quality_profile: str = "balanced",
        source_blocks: Sequence[Mapping[str, Any]] | None = None,
        prompt_pack_id: str = "private.prompt_pack",
        prompt_pack_version: str = "1.0.0",
        system_instruction_ref: str = "private://instruction",
        response_schema_ref: str = "dto://ModuleResult",
        source_language: str = "zh",
        output_locale: str = "zh-CN",
        token_budget: int | None = None,
        cost_budget: float | None = None,
        data_handling_policy: Mapping[str, Any] | None = None,
        context_limit_ok: bool = True,
        warnings: Sequence[str] = (),
    ) -> ProviderInputBundle:
        _ = (
            context_bundle_hash,
            source_blocks,
            prompt_pack_id,
            prompt_pack_version,
            system_instruction_ref,
            response_schema_ref,
            context_limit_ok,
            warnings,
        )
        # Formal path ignores client/synthetic source_blocks — Snapshot is sole fact source.
        self._require_ready()
        contract = self._build_contract_bundle(
            book_id=book_id,
            book_snapshot_id=book_snapshot_id,
            module_key=module_key,
            quality_profile=quality_profile,
            source_language=source_language,
        )
        assembled = self._private.resolve(
            request_id=request_id,
            book_id=int(book_id),
            book_snapshot_id=int(book_snapshot_id),
            module_key=module_key,
            context_bundle=contract,
            provider_key=provider_key,
            model_id=model_id,
            quality_profile=quality_profile,
            source_language=source_language,
            output_locale=output_locale,
            token_budget=token_budget,
            cost_budget=cost_budget,
            data_handling_policy=data_handling_policy
            or {
                "execution_location": "cloud",
                "sends_source_text": True,
                "sends_derived_text": False,
                "retention_policy": "provider_ephemeral",
                "user_consent_required": True,
            },
        )
        return _assembled_to_public_bundle(assembled)

    def estimate(self, bundle: ProviderInputBundle, **kwargs: Any) -> ProviderEstimateResult:
        return self.estimate_service.estimate(bundle, **kwargs)

    def build_transfer_manifest(
        self,
        bundle: ProviderInputBundle,
        *,
        estimate: ProviderEstimateResult | None = None,
        execution_location: str | None = None,
        snapshot_content_hash: str = "",
    ) -> WholeBookDataTransferManifest:
        est = estimate or self.estimate(bundle)
        policy = bundle.data_handling_policy
        return self.manifest_builder.build(
            book_id=bundle.book_id,
            book_snapshot_id=bundle.book_snapshot_id,
            module_key=bundle.module_key,
            provider_key=bundle.provider_key,
            model_id=bundle.model_id,
            execution_location=execution_location
            or str(policy.get("execution_location") or "cloud"),
            context_bundle_hash=bundle.context_bundle_hash,
            selected_context_unit_ids=bundle.selected_context_unit_ids,
            selected_chapter_ids=bundle.selected_chapter_ids,
            selected_paragraph_ids=bundle.selected_paragraph_ids,
            source_character_count=bundle.source_character_count(),
            estimated_input_tokens=est.estimated_input_tokens,
            estimated_output_tokens=est.estimated_output_tokens,
            estimated_cost_low=est.cost.cost_low,
            estimated_cost_expected=est.cost.cost_expected,
            estimated_cost_high=est.cost.cost_high,
            max_retry_cost=est.cost.max_retry_cost,
            pricing_version=est.cost.pricing_version,
            sends_source_text=bool(policy.get("sends_source_text", True)),
            sends_derived_text=bool(policy.get("sends_derived_text", False)),
            retention_policy=str(policy.get("retention_policy") or "provider_ephemeral"),
            consent_required=bool(policy.get("user_consent_required", True)),
            estimate_fingerprint=est.estimate_fingerprint,
            prompt_pack_id=bundle.prompt_pack_id,
            prompt_pack_version=bundle.prompt_pack_version,
            pricing_status=est.cost.pricing_status,
            snapshot_content_hash=snapshot_content_hash,
            warnings=tuple(dict.fromkeys([*bundle.warnings, *est.warnings])),
        )


def _assembled_to_public_bundle(assembled: Any) -> ProviderInputBundle:
    blocks = tuple(
        SourceDataBlock(
            block_id=b.block_id,
            unit_type=str(b.unit_type),
            chapter_ref=b.chapter_ref,
            paragraph_refs=tuple(str(p) for p in b.paragraph_refs),
            source_kind=str(b.source_kind),
            character_count=int(b.character_count),
            content_hash=str(b.content_hash),
            text=str(getattr(b, "text", "") or ""),
            untrusted_source_data=True,
        )
        for b in assembled.source_data_blocks
    )
    messages = tuple(
        ProviderChatMessage(
            role=str(m.role),
            content=str(m.content),
            untrusted_source_data=bool(getattr(m, "untrusted_source_data", False)),
        )
        for m in assembled.messages
    )
    return ProviderInputBundle(
        schema=str(assembled.schema),
        version=str(assembled.version),
        request_id=str(assembled.request_id),
        book_id=int(assembled.book_id),
        book_snapshot_id=int(assembled.book_snapshot_id),
        module_key=str(assembled.module_key),
        context_bundle_hash=str(assembled.context_bundle_hash),
        prompt_pack_id=str(assembled.prompt_pack_id),
        prompt_pack_version=str(assembled.prompt_pack_version),
        system_instruction_ref=str(assembled.system_instruction_ref),
        source_data_blocks=blocks,
        response_schema_ref=str(assembled.response_schema_ref),
        source_language=str(assembled.source_language),
        output_locale=str(assembled.output_locale),
        provider_key=str(assembled.provider_key),
        model_id=str(assembled.model_id),
        quality_profile=str(assembled.quality_profile),
        token_budget=assembled.token_budget,
        cost_budget=assembled.cost_budget,
        data_handling_policy=dict(assembled.data_handling_policy),
        bundle_fingerprint=str(assembled.bundle_fingerprint),
        system_instruction=str(getattr(assembled, "system_instruction", "") or ""),
        messages=messages,
        selected_context_unit_ids=tuple(str(x) for x in assembled.selected_context_unit_ids),
        selected_chapter_ids=tuple(str(x) for x in assembled.selected_chapter_ids),
        selected_paragraph_ids=tuple(str(x) for x in assembled.selected_paragraph_ids),
        context_limit_ok=bool(assembled.context_limit_ok),
        warnings=tuple(str(w) for w in assembled.warnings),
    )


__all__ = [
    "FormalPrivateProviderInputBundleResolverAdapter",
    "FormalPrivateResolverUnavailable",
    "load_private_provider_input_bundle_resolver",
]
