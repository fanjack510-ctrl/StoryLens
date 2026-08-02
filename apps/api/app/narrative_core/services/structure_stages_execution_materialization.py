"""Immutable Structure Stages execution materialization (CHG-20260725-001).

Frozen at Estimate: selection + catalog + coverage binding fingerprints.
No novel body. No Provider HTTP. Shared by Estimate → Consent → Executor → Diagnostics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from app.narrative_core.services.citation_catalog_materialization import (
    EstimateCatalogMaterialization,
)
from app.narrative_core.services.citation_catalog_v2 import CitationCatalog
from app.narrative_core.services.execution_context_binding import (
    ExecutionContextBinding,
    compute_selection_fingerprint,
)

EXECUTION_CONTEXT_CATALOG_MISMATCH = "EXECUTION_CONTEXT_CATALOG_MISMATCH"
EXECUTION_CONTEXT_BINDING_FAILURE = "EXECUTION_CONTEXT_BINDING_FAILURE"
EXECUTION_CONTEXT_SELECTION_EMPTY = "EXECUTION_CONTEXT_SELECTION_EMPTY"


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(payload: Any) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StructureStagesExecutionMaterialization:
    """Estimate-frozen Structure Stages execution identity (selection + catalog + coverage)."""

    selected_chapter_ids: tuple[str, ...]
    selected_paragraph_ids: tuple[str, ...]
    selected_unit_refs: tuple[str, ...]
    selection_fingerprint: str
    context_bundle_hash: str
    catalog_id: str
    catalog_entry_count: int
    catalog_fingerprint: str
    dynamic_schema_fingerprint: str
    prompt_catalog_fingerprint: str
    resolver_catalog_fingerprint: str
    prompt_input_fingerprint: str
    execution_context_fingerprint: str
    expected_coverage_scope: str
    context_capabilities: Mapping[str, Any]
    requires_stage_observation: bool
    permits_empty_observation: bool
    schema_catalog_fingerprint: str = ""
    citation_ids: tuple[str, ...] = ()
    catalog: CitationCatalog | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.selected_paragraph_ids:
            raise ValueError(EXECUTION_CONTEXT_SELECTION_EMPTY)

    def safe_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("catalog", None)
        data["context_capabilities"] = dict(self.context_capabilities or {})
        data["selected_chapter_ids"] = list(self.selected_chapter_ids)
        data["selected_paragraph_ids"] = list(self.selected_paragraph_ids)
        data["selected_unit_refs"] = list(self.selected_unit_refs)
        data["citation_ids_count"] = len(self.citation_ids)
        data["citation_ids_sample"] = list(self.citation_ids[:3])
        data.pop("citation_ids", None)
        return data


def compute_execution_context_fingerprint(
    *,
    selection_fingerprint: str,
    context_bundle_hash: str,
    catalog_fingerprint: str,
    dynamic_schema_fingerprint: str,
    expected_coverage_scope: str,
) -> str:
    return _sha256_hex(
        {
            "v": "structure_stages_exec_ctx_fp.v1",
            "selection_fingerprint": selection_fingerprint,
            "context_bundle_hash": context_bundle_hash,
            "catalog_fingerprint": catalog_fingerprint,
            "dynamic_schema_fingerprint": dynamic_schema_fingerprint,
            "expected_coverage_scope": expected_coverage_scope,
        }
    )


def freeze_structure_stages_execution_materialization(
    *,
    selected_chapter_ids: Sequence[str],
    selected_paragraph_ids: Sequence[str | int],
    selected_unit_refs: Sequence[str],
    context_bundle_hash: str,
    catalog_mat: EstimateCatalogMaterialization,
    context_capabilities: Mapping[str, Any] | None = None,
    prompt_input_fingerprint: str = "",
    selection_policy_version: str = "context_strategy.v1.batch8",
) -> StructureStagesExecutionMaterialization:
    """Build immutable materialization from Estimate selection + catalog freeze."""

    paragraphs = tuple(str(x) for x in selected_paragraph_ids)
    if not paragraphs:
        raise ValueError(EXECUTION_CONTEXT_SELECTION_EMPTY)

    chapters = tuple(str(x) for x in selected_chapter_ids)
    units = tuple(str(x) for x in selected_unit_refs)
    selection_fp = compute_selection_fingerprint(
        selected_chapter_ids=chapters,
        selected_paragraph_ids=paragraphs,
        selected_unit_refs=units,
        selection_policy_version=selection_policy_version,
    )
    caps = dict(context_capabilities or {})
    expected_scope = ""
    requires_obs = True
    permits_empty = False
    try:
        from app.narrative_core.services.structure_stages_output_contract_v2 import (
            resolve_structure_context_capabilities,
        )
        from storylens_private_engine.citation import freeze_structure_coverage_binding

        caps_obj = resolve_structure_context_capabilities(caps)
        if caps_obj is not None:
            binding = freeze_structure_coverage_binding(caps_obj)
            expected_scope = str(binding.expected_coverage_scope)
            requires_obs = bool(binding.requires_stage_observation)
            permits_empty = bool(binding.permits_empty_observation)
            caps = caps_obj.safe_dict() if hasattr(caps_obj, "safe_dict") else caps
    except Exception:  # noqa: BLE001
        expected_scope = str(caps.get("expected_coverage_scope") or "")
        requires_obs = bool(caps.get("requires_stage_observation", True))
        permits_empty = bool(caps.get("permits_empty_observation", False))

    exec_fp = compute_execution_context_fingerprint(
        selection_fingerprint=selection_fp,
        context_bundle_hash=str(context_bundle_hash),
        catalog_fingerprint=str(catalog_mat.catalog_fingerprint),
        dynamic_schema_fingerprint=str(catalog_mat.dynamic_schema_fingerprint),
        expected_coverage_scope=expected_scope,
    )
    return StructureStagesExecutionMaterialization(
        selected_chapter_ids=chapters,
        selected_paragraph_ids=paragraphs,
        selected_unit_refs=units,
        selection_fingerprint=selection_fp,
        context_bundle_hash=str(context_bundle_hash),
        catalog_id=str(catalog_mat.catalog_id),
        catalog_entry_count=int(catalog_mat.catalog_entry_count),
        catalog_fingerprint=str(catalog_mat.catalog_fingerprint),
        dynamic_schema_fingerprint=str(catalog_mat.dynamic_schema_fingerprint),
        prompt_catalog_fingerprint=str(catalog_mat.prompt_catalog_fingerprint),
        resolver_catalog_fingerprint=str(catalog_mat.resolver_catalog_fingerprint),
        prompt_input_fingerprint=str(prompt_input_fingerprint or ""),
        execution_context_fingerprint=exec_fp,
        expected_coverage_scope=expected_scope,
        context_capabilities=caps,
        requires_stage_observation=requires_obs,
        permits_empty_observation=permits_empty,
        schema_catalog_fingerprint=str(catalog_mat.schema_catalog_fingerprint),
        citation_ids=tuple(catalog_mat.citation_ids),
        catalog=catalog_mat.catalog,
    )


def materialization_from_binding_and_catalog(
    *,
    binding: ExecutionContextBinding | Mapping[str, Any],
    catalog_mat: EstimateCatalogMaterialization | Mapping[str, Any],
) -> StructureStagesExecutionMaterialization:
    """Rebuild materialization from stored binding + catalog_materialization safes."""

    if isinstance(binding, ExecutionContextBinding):
        b = binding
        chapters = b.selected_chapter_ids
        paragraphs = b.selected_paragraph_ids
        units = b.selected_unit_refs
        ctx_hash = b.context_bundle_hash
        caps = dict(b.context_capabilities or {})
        prompt_fp = b.prompt_input_fingerprint
        policy = b.selection_policy_version
    else:
        chapters = tuple(str(x) for x in (binding.get("selected_chapter_ids") or ()))
        paragraphs = tuple(str(x) for x in (binding.get("selected_paragraph_ids") or ()))
        units = tuple(str(x) for x in (binding.get("selected_unit_refs") or ()))
        ctx_hash = str(binding.get("context_bundle_hash") or "")
        caps = dict(binding.get("context_capabilities") or {})
        prompt_fp = str(binding.get("prompt_input_fingerprint") or "")
        policy = str(
            binding.get("selection_policy_version") or "context_strategy.v1.batch8"
        )

    if isinstance(catalog_mat, EstimateCatalogMaterialization):
        mat = catalog_mat
    else:
        mat = EstimateCatalogMaterialization(
            module_key="structure_stages",
            catalog_id=str(catalog_mat.get("catalog_id") or ""),
            catalog_entry_count=int(catalog_mat.get("catalog_entry_count") or 0),
            citation_enum_count=int(
                catalog_mat.get("citation_enum_count")
                or catalog_mat.get("catalog_entry_count")
                or 0
            ),
            catalog_fingerprint=str(catalog_mat.get("catalog_fingerprint") or ""),
            prompt_catalog_fingerprint=str(
                catalog_mat.get("prompt_catalog_fingerprint") or ""
            ),
            schema_catalog_fingerprint=str(
                catalog_mat.get("schema_catalog_fingerprint") or ""
            ),
            resolver_catalog_fingerprint=str(
                catalog_mat.get("resolver_catalog_fingerprint") or ""
            ),
            dynamic_schema_fingerprint=str(
                catalog_mat.get("dynamic_schema_fingerprint") or ""
            ),
            context_bundle_hash=str(
                catalog_mat.get("context_bundle_hash") or ctx_hash
            ),
            selected_paragraph_count=len(paragraphs),
            citation_ids=tuple(catalog_mat.get("citation_ids") or ()),
            catalog=None,
        )
    return freeze_structure_stages_execution_materialization(
        selected_chapter_ids=chapters,
        selected_paragraph_ids=paragraphs,
        selected_unit_refs=units,
        context_bundle_hash=ctx_hash,
        catalog_mat=mat,
        context_capabilities=caps,
        prompt_input_fingerprint=prompt_fp,
        selection_policy_version=policy,
    )


def compare_catalog_to_materialization(
    *,
    materialization: StructureStagesExecutionMaterialization | Mapping[str, Any],
    catalog_fingerprint: str,
    catalog_entry_count: int,
    catalog_id: str | None = None,
) -> tuple[bool, str | None]:
    """Return (ok, failure_code) comparing a live catalog against frozen Estimate."""

    if isinstance(materialization, StructureStagesExecutionMaterialization):
        expected_fp = materialization.catalog_fingerprint
        expected_count = materialization.catalog_entry_count
        expected_id = materialization.catalog_id
    else:
        expected_fp = str(materialization.get("catalog_fingerprint") or "")
        expected_count = int(materialization.get("catalog_entry_count") or 0)
        expected_id = str(materialization.get("catalog_id") or "")
    if expected_fp and str(catalog_fingerprint or "") != expected_fp:
        return False, EXECUTION_CONTEXT_CATALOG_MISMATCH
    if expected_count and int(catalog_entry_count or 0) != expected_count:
        return False, EXECUTION_CONTEXT_CATALOG_MISMATCH
    if catalog_id and expected_id and str(catalog_id) != expected_id:
        return False, EXECUTION_CONTEXT_CATALOG_MISMATCH
    return True, None


__all__ = [
    "EXECUTION_CONTEXT_BINDING_FAILURE",
    "EXECUTION_CONTEXT_CATALOG_MISMATCH",
    "EXECUTION_CONTEXT_SELECTION_EMPTY",
    "StructureStagesExecutionMaterialization",
    "compare_catalog_to_materialization",
    "compute_execution_context_fingerprint",
    "freeze_structure_stages_execution_materialization",
    "materialization_from_binding_and_catalog",
]
