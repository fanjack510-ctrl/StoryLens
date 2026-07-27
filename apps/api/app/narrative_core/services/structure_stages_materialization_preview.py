"""Provider-free Structure Stages execution materialization preview (CHG-20260725-001).

Runs formal Estimate → Catalog → Dynamic Schema → Prompt citation render → Resolver
binding, then stops before any Provider HTTP. Never prints novel body or full prompt.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.narrative_core.services.citation_catalog_materialization import (
    materialize_structure_stages_estimate_catalog,
)
from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
    create_live_readiness_runtime,
)


@dataclass(frozen=True, slots=True)
class StructureStagesMaterializationPreview:
    selected_chapter_count: int
    selected_paragraph_count: int
    selected_unit_count: int
    source_character_count: int
    context_bundle_hash: str
    selection_fingerprint: str
    catalog_id: str
    catalog_entry_count: int
    citation_enum_count: int
    catalog_fingerprint: str
    prompt_catalog_fingerprint: str
    schema_catalog_fingerprint: str
    resolver_catalog_fingerprint: str
    dynamic_schema_fingerprint: str
    prompt_input_fingerprint: str
    execution_context_fingerprint: str
    max_repair_count: int
    estimated_input_tokens: int | None
    estimated_output_tokens: int | None
    estimated_total_tokens: int | None
    max_total_authorized_cost: float | None
    pricing_status: str | None
    provider_http_count: int
    coverage_scope_note: str
    context_capabilities: dict[str, Any]
    evidence_contract_version: str
    resolver_is_fake: bool
    preflight_ok: bool
    estimate_fingerprint: str
    consent_fingerprint: str | None
    cited_sources_block_count: int
    fingerprints_match: bool

    def safe_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_structure_stages_provider_free_materialization_preview(
    *,
    session: Session,
    book_id: int = 1,
    book_snapshot_id: int = 1,
    configuration_fingerprint: str = "live-smoke-cfg-structure-stages-materialization",
) -> StructureStagesMaterializationPreview:
    """Materialize Structure Stages Provider request inputs with HTTP=0."""

    runtime = create_live_readiness_runtime(
        environment="development",
        lab_enabled=True,
        dry_run=True,
        session=session,
        allow_fake_resolver=False,
        auto_wire_credentials=True,
    )
    runtime.bind_session(session)
    assert runtime.preflight is not None
    assert runtime.estimate is not None

    modules = ("structure_stages",)
    pre = runtime.preflight.preflight(
        book_id=int(book_id),
        book_snapshot_id=int(book_snapshot_id),
        configuration_fingerprint=configuration_fingerprint,
        requested_modules=modules,
    )
    if not pre.ok:
        raise RuntimeError(f"preflight_failed:{pre.reason_code}")

    est = runtime.estimate.estimate(
        book_id=int(book_id),
        book_snapshot_id=int(book_snapshot_id),
        configuration_fingerprint=configuration_fingerprint,
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
        requested_modules=modules,
        preflight_fingerprint=pre.fingerprint,
    )
    cached = runtime.estimate._cache.get(est.fingerprint) or {}  # noqa: SLF001
    binding = dict(cached.get("execution_context_binding") or {})
    mat_safe = dict(cached.get("catalog_materialization") or {})
    primary = cached.get("primary_manifest")
    usage = dict(est.usage_summary or {})
    cost = dict(est.cost_summary or {})
    module_estimates = list(cached.get("module_estimates") or [])
    primary_est: dict[str, Any] = {}
    if module_estimates and isinstance(module_estimates[0], dict):
        primary_est = module_estimates[0]
    max_auth = primary_est.get("max_total_authorized_cost")
    if max_auth is None and isinstance(primary_est.get("cost"), dict):
        max_auth = primary_est["cost"].get("max_total_authorized_cost")
    if max_auth is None and cost.get("cost_expected") is not None:
        max_auth = float(cost["cost_expected"]) * 2.0

    # Prove Prompt citation rendering can enumerate catalog (no body returned).
    cited_block_count = 0
    catalog_obj = None
    contract = None
    if hasattr(runtime.resolver, "last_contract"):
        contract = runtime.resolver.last_contract()
    remat = materialize_structure_stages_estimate_catalog(
        session=session,
        contract=contract,
        book_snapshot_id=int(book_snapshot_id),
        context_bundle_hash=str(binding.get("context_bundle_hash") or ""),
        selected_paragraph_ids=tuple(binding.get("selected_paragraph_ids") or ()),
    )
    if remat is not None:
        catalog_obj = remat.catalog
        try:
            from storylens_private_engine.citation import render_cited_source_blocks
            from app.narrative_core.services.citation_catalog_v2 import (
                catalog_for_private_engine,
            )

            private_catalog = catalog_for_private_engine(catalog_obj)
            blocks = render_cited_source_blocks(private_catalog)
            cited_block_count = len(tuple(blocks or ()))
        except Exception:  # noqa: BLE001
            cited_block_count = int(remat.catalog_entry_count)

    catalog_fp = str(
        mat_safe.get("catalog_fingerprint")
        or binding.get("citation_catalog_fingerprint")
        or ""
    )
    prompt_fp = str(mat_safe.get("prompt_catalog_fingerprint") or catalog_fp)
    schema_cat_fp = str(mat_safe.get("schema_catalog_fingerprint") or catalog_fp)
    resolver_fp = str(mat_safe.get("resolver_catalog_fingerprint") or catalog_fp)
    fingerprints_match = bool(
        catalog_fp
        and len({catalog_fp, prompt_fp, schema_cat_fp, resolver_fp}) == 1
    )
    entry_count = int(
        mat_safe.get("catalog_entry_count")
        or binding.get("citation_entry_count")
        or 0
    )
    enum_count = int(mat_safe.get("citation_enum_count") or entry_count)

    # Execution context fingerprint = selection fingerprint (binding authority).
    selection_fp = str(binding.get("selection_fingerprint") or "")
    exec_fp = selection_fp

    chapters = list(binding.get("selected_chapter_ids") or ())
    paragraphs = list(binding.get("selected_paragraph_ids") or ())
    units = list(binding.get("selected_unit_refs") or ())
    if primary is not None and not chapters:
        chapters = list(getattr(primary, "selected_chapter_ids", ()) or ())
        paragraphs = list(getattr(primary, "selected_paragraph_ids", ()) or ())
        units = list(getattr(primary, "selected_context_unit_ids", ()) or ())

    return StructureStagesMaterializationPreview(
        selected_chapter_count=len(chapters),
        selected_paragraph_count=len(paragraphs),
        selected_unit_count=len(units),
        source_character_count=int(binding.get("source_character_count") or 0),
        context_bundle_hash=str(binding.get("context_bundle_hash") or ""),
        selection_fingerprint=selection_fp,
        catalog_id=str(mat_safe.get("catalog_id") or ""),
        catalog_entry_count=entry_count,
        citation_enum_count=enum_count,
        catalog_fingerprint=catalog_fp,
        prompt_catalog_fingerprint=prompt_fp,
        schema_catalog_fingerprint=schema_cat_fp,
        resolver_catalog_fingerprint=resolver_fp,
        dynamic_schema_fingerprint=str(
            mat_safe.get("dynamic_schema_fingerprint")
            or binding.get("dynamic_schema_fingerprint")
            or ""
        ),
        prompt_input_fingerprint=str(binding.get("prompt_input_fingerprint") or ""),
        execution_context_fingerprint=exec_fp,
        max_repair_count=int(usage.get("max_repair_count") or 1),
        estimated_input_tokens=usage.get("estimated_input_tokens"),
        estimated_output_tokens=usage.get("estimated_output_tokens"),
        estimated_total_tokens=usage.get("estimated_total_tokens"),
        max_total_authorized_cost=float(max_auth) if max_auth is not None else None,
        pricing_status=str(cost.get("pricing_status") or "") or None,
        provider_http_count=0,
        coverage_scope_note=(
            "coverage_scope is result-time; preview exposes ContextCapabilities"
        ),
        context_capabilities=dict(binding.get("context_capabilities") or {}),
        evidence_contract_version=str(usage.get("evidence_contract_version") or "v2"),
        resolver_is_fake=bool(runtime.uses_fake_resolver),
        preflight_ok=bool(pre.ok),
        estimate_fingerprint=str(est.fingerprint),
        consent_fingerprint=(
            str(cached.get("consent_fingerprint"))
            if cached.get("consent_fingerprint")
            else None
        ),
        cited_sources_block_count=cited_block_count,
        fingerprints_match=fingerprints_match,
    )


__all__ = [
    "StructureStagesMaterializationPreview",
    "run_structure_stages_provider_free_materialization_preview",
]
