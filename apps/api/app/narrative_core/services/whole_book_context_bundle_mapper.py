"""Context Bundle Mapper (Phase 2B Integration / CHG-040).

Freezes ContextBundle as the cross-component transport contract.
WholeBookContextBundle is the runtime-enhanced model and must convert
explicitly via this mapper — no implicit field compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.narrative_core.private_engine_contract.context import (
    CONTEXT_SCHEMA,
    CONTEXT_SCHEMA_VERSION,
    ContextBundle,
    WholeBookContextUnit,
)
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineErrorCode,
    private_engine_error,
)
from app.narrative_core.services.whole_book_context_pipeline import (
    ContextCoverage,
    ContextMode,
    HierarchicalContextPlan,
    WholeBookContextBundle,
)


@dataclass(frozen=True, slots=True)
class ContextBundleCompatibilityReport:
    compatible: bool
    error_code: str | None = None
    details: tuple[str, ...] = ()


class WholeBookContextBundleMapper:
    """Explicit mapper between runtime WholeBookContextBundle and contract ContextBundle."""

    @staticmethod
    def to_contract(bundle: WholeBookContextBundle) -> ContextBundle:
        WholeBookContextBundleMapper.validate_compatibility(bundle)
        return ContextBundle(
            book_id=bundle.book_id,
            book_snapshot_id=bundle.book_snapshot_id,
            snapshot_content_hash=bundle.snapshot_content_hash,
            chapter_hashes=bundle.chapter_hashes,
            paragraph_hashes=bundle.paragraph_hashes,
            context_schema=bundle.schema,
            context_schema_version=bundle.schema_version,
            pipeline_version=bundle.pipeline_version,
            configuration_fingerprint=bundle.configuration_fingerprint,
            units=bundle.units,
            bundle_hash=bundle.bundle_hash,
        )

    @staticmethod
    def from_contract(
        contract: ContextBundle,
        *,
        context_unit_refs: tuple[str, ...] | None = None,
        requested_modules: tuple[str, ...] = (),
        resolved_modules: tuple[str, ...] = (),
        mode: ContextMode = ContextMode.NATIVE,
        analysis_mode: str = "native",
        quality_profile_key: str = "balanced",
        source_language: str = "unknown",
        token_estimate: int = 0,
        character_estimate: int = 0,
        coverage: ContextCoverage | None = None,
        warnings: tuple[str, ...] = (),
        plan: HierarchicalContextPlan | None = None,
    ) -> WholeBookContextBundle:
        WholeBookContextBundleMapper.validate_contract(contract)
        refs = context_unit_refs
        if refs is None:
            refs = tuple(u.unit_id for u in contract.units)
        cov = coverage or ContextCoverage(
            chapter_units=sum(1 for u in contract.units if u.unit_type.value == "chapter"),
            scene_units=sum(1 for u in contract.units if u.unit_type.value == "scene"),
            paragraph_group_units=sum(
                1 for u in contract.units if u.unit_type.value == "paragraph_group"
            ),
            evidence_window_units=sum(
                1 for u in contract.units if u.unit_type.value == "evidence_window"
            ),
            derived_summary_units=sum(
                1 for u in contract.units if u.unit_type.value == "derived_summary"
            ),
            levels_included=(),
        )
        return WholeBookContextBundle(
            schema=contract.context_schema,
            schema_version=contract.context_schema_version,
            pipeline_version=contract.pipeline_version,
            book_id=contract.book_id,
            book_snapshot_id=contract.book_snapshot_id,
            snapshot_content_hash=contract.snapshot_content_hash,
            chapter_hashes=contract.chapter_hashes,
            paragraph_hashes=contract.paragraph_hashes,
            context_unit_refs=refs,
            units=contract.units,
            requested_modules=requested_modules,
            resolved_modules=resolved_modules,
            configuration_fingerprint=contract.configuration_fingerprint,
            bundle_hash=contract.bundle_hash,
            mode=mode,
            analysis_mode=analysis_mode,
            quality_profile_key=quality_profile_key,
            source_language=source_language,
            token_estimate=token_estimate,
            character_estimate=character_estimate,
            coverage=cov,
            warnings=warnings,
            plan=plan,
        )

    @staticmethod
    def validate_contract(contract: ContextBundle) -> None:
        if contract.context_schema != CONTEXT_SCHEMA:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="schema_mismatch",
            )
        if contract.context_schema_version != CONTEXT_SCHEMA_VERSION:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="schema_version_mismatch",
            )
        if not contract.snapshot_content_hash.strip():
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="missing_snapshot_hash",
            )
        if not contract.configuration_fingerprint.strip():
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="missing_configuration_fingerprint",
            )
        if not contract.bundle_hash.strip():
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="missing_bundle_hash",
            )
        for unit in contract.units:
            WholeBookContextBundleMapper._assert_unit_safe(unit)

    @staticmethod
    def validate_compatibility(
        bundle: WholeBookContextBundle | Mapping[str, Any],
    ) -> ContextBundleCompatibilityReport:
        if isinstance(bundle, Mapping):
            schema = str(bundle.get("schema") or bundle.get("context_schema") or "")
            schema_version = str(
                bundle.get("schema_version") or bundle.get("context_schema_version") or ""
            )
            snapshot_hash = str(bundle.get("snapshot_content_hash") or "")
            chapter_hashes = bundle.get("chapter_hashes")
            unit_refs = bundle.get("context_unit_refs")
            pipeline_version = str(bundle.get("pipeline_version") or "")
            config_fp = str(bundle.get("configuration_fingerprint") or "")
            warnings = bundle.get("warnings")
            coverage = bundle.get("coverage")
            requested = bundle.get("requested_modules")
            resolved = bundle.get("resolved_modules")
        else:
            schema = bundle.schema
            schema_version = bundle.schema_version
            snapshot_hash = bundle.snapshot_content_hash
            chapter_hashes = bundle.chapter_hashes
            unit_refs = bundle.context_unit_refs
            pipeline_version = bundle.pipeline_version
            config_fp = bundle.configuration_fingerprint
            warnings = bundle.warnings
            coverage = bundle.coverage
            requested = bundle.requested_modules
            resolved = bundle.resolved_modules

        details: list[str] = []
        if schema != CONTEXT_SCHEMA:
            details.append("schema_mismatch")
        if schema_version != CONTEXT_SCHEMA_VERSION:
            details.append("schema_version_mismatch")
        if not snapshot_hash:
            details.append("missing_snapshot_hash")
        if chapter_hashes is None:
            details.append("missing_chapter_hashes")
        if unit_refs is None:
            details.append("missing_context_unit_refs")
        if not pipeline_version:
            details.append("missing_pipeline_version")
        if not config_fp:
            details.append("missing_configuration_fingerprint")
        if requested is None:
            details.append("missing_requested_modules")
        if resolved is None:
            details.append("missing_resolved_modules")
        if coverage is None:
            details.append("missing_coverage")
        if warnings is None:
            details.append("missing_warnings")

        if details:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code=",".join(details),
            )
        if not isinstance(bundle, Mapping):
            for unit in bundle.units:
                WholeBookContextBundleMapper._assert_unit_safe(unit)
        return ContextBundleCompatibilityReport(compatible=True)

    @staticmethod
    def round_trip(bundle: WholeBookContextBundle) -> WholeBookContextBundle:
        """Contract round-trip preserving required identity fields."""

        contract = WholeBookContextBundleMapper.to_contract(bundle)
        restored = WholeBookContextBundleMapper.from_contract(
            contract,
            context_unit_refs=bundle.context_unit_refs,
            requested_modules=bundle.requested_modules,
            resolved_modules=bundle.resolved_modules,
            mode=bundle.mode,
            analysis_mode=bundle.analysis_mode,
            quality_profile_key=bundle.quality_profile_key,
            source_language=bundle.source_language,
            token_estimate=bundle.token_estimate,
            character_estimate=bundle.character_estimate,
            coverage=bundle.coverage,
            warnings=bundle.warnings,
            plan=bundle.plan,
        )
        # Identity fields that must survive.
        if restored.snapshot_content_hash != bundle.snapshot_content_hash:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="round_trip_snapshot_hash_lost",
            )
        if restored.chapter_hashes != bundle.chapter_hashes:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="round_trip_chapter_hashes_lost",
            )
        if restored.context_unit_refs != bundle.context_unit_refs:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="round_trip_unit_refs_lost",
            )
        if restored.requested_modules != bundle.requested_modules:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="round_trip_requested_modules_lost",
            )
        if restored.resolved_modules != bundle.resolved_modules:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="round_trip_resolved_modules_lost",
            )
        if restored.pipeline_version != bundle.pipeline_version:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="round_trip_pipeline_version_lost",
            )
        if restored.configuration_fingerprint != bundle.configuration_fingerprint:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="round_trip_configuration_fingerprint_lost",
            )
        if restored.bundle_hash != bundle.bundle_hash:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="round_trip_bundle_hash_lost",
            )
        if restored.coverage != bundle.coverage:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="round_trip_coverage_lost",
            )
        if restored.warnings != bundle.warnings:
            raise private_engine_error(
                PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                detail_code="round_trip_warnings_lost",
            )
        return restored

    @staticmethod
    def _assert_unit_safe(unit: WholeBookContextUnit) -> None:
        meta = unit.metadata or {}
        for banned in ("full_text", "novel_body", "cache_object", "temporary_cache"):
            if banned in meta:
                raise private_engine_error(
                    PrivateEngineErrorCode.CONTEXT_BUNDLE_INVALID,
                    detail_code=f"forbidden_unit_metadata:{banned}",
                )


__all__ = [
    "ContextBundleCompatibilityReport",
    "WholeBookContextBundleMapper",
]
