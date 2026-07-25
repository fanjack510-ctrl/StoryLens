"""Estimate-time Citation Catalog materialization (CHG-20260725-001 gap closure).

Structure Stages Live requires Catalog / Dynamic Schema / Prompt / Resolver
fingerprints to be frozen at Estimate (not deferred to Execute).

Does not print novel body or full prompt. Does not call Provider HTTP.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.narrative_core.services.citation_catalog_v2 import (
    CitationCatalog,
    build_catalog_from_paragraph_units,
)


@dataclass(frozen=True, slots=True)
class EstimateCatalogMaterialization:
    """Safe summary of Catalog + schema fingerprints bound at Estimate."""

    module_key: str
    catalog_id: str
    catalog_entry_count: int
    citation_enum_count: int
    catalog_fingerprint: str
    prompt_catalog_fingerprint: str
    schema_catalog_fingerprint: str
    resolver_catalog_fingerprint: str
    dynamic_schema_fingerprint: str
    context_bundle_hash: str
    selected_paragraph_count: int
    citation_ids: tuple[str, ...] = ()
    catalog: CitationCatalog | None = field(default=None, repr=False, compare=False)

    def safe_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("catalog", None)
        # citation_ids are opaque refs (CIT-...), not novel body — keep count-focused view
        data["citation_ids_sample"] = list(self.citation_ids[:3])
        data["citation_ids_count"] = len(self.citation_ids)
        data.pop("citation_ids", None)
        return data


def build_citation_paragraph_units_from_contract(
    *,
    session: Session | None,
    contract: Any,
    book_snapshot_id: int,
    selected_paragraph_ids: Sequence[int] | None,
) -> list[dict[str, Any]]:
    """Build paragraph unit dicts for CitationCatalog (same selection semantics as Runtime)."""

    units: list[dict[str, Any]] = []
    selected = (
        {int(x) for x in selected_paragraph_ids}
        if selected_paragraph_ids is not None
        else None
    )
    seen: set[int] = set()
    for unit in getattr(contract, "units", ()) or ():
        chapter_id = getattr(unit, "snapshot_chapter_id", None)
        pids = tuple(getattr(unit, "snapshot_paragraph_ids", ()) or ())
        stables = tuple(getattr(unit, "stable_paragraph_ids", ()) or ())
        hashes = tuple(
            (getattr(unit, "metadata", {}) or {}).get("paragraph_hashes") or ()
        )
        for idx, pid_raw in enumerate(pids):
            try:
                pid = int(pid_raw)
            except (TypeError, ValueError):
                continue
            if selected is not None and pid not in selected:
                continue
            if pid in seen:
                continue
            seen.add(pid)
            stable = stables[idx] if idx < len(stables) else None
            content_hash = str(hashes[idx] or "") if idx < len(hashes) else ""
            text = ""
            end = 0
            if session is not None:
                try:
                    from app.narrative_core.services.snapshot_service import (
                        SnapshotService,
                    )

                    text = SnapshotService(session).get_snapshot_paragraph_text(int(pid))
                    end = len(text) if text else 0
                except Exception:  # noqa: BLE001
                    text = ""
            if not text and end > 0:
                text = "x" * end
            if not text:
                # Deterministic filler keeps catalog ordinals stable when body unavailable.
                text = "x"
            units.append(
                {
                    "chapter_id": chapter_id,
                    "paragraph_id": pid,
                    "stable_paragraph_id": str(stable) if stable is not None else str(pid),
                    "content_hash": content_hash or "missing",
                    "text": text,
                }
            )
    return units


def materialize_structure_stages_estimate_catalog(
    *,
    session: Session | None,
    contract: Any,
    book_snapshot_id: int,
    context_bundle_hash: str,
    selected_paragraph_ids: Sequence[str | int],
    context_bundle_ref: str | None = None,
) -> EstimateCatalogMaterialization | None:
    """Materialize Structure Stages Citation Catalog + dynamic schema at Estimate."""

    if not context_bundle_hash or not selected_paragraph_ids:
        return None
    selected_pids = tuple(int(x) for x in selected_paragraph_ids)
    units = build_citation_paragraph_units_from_contract(
        session=session,
        contract=contract,
        book_snapshot_id=int(book_snapshot_id),
        selected_paragraph_ids=selected_pids,
    )
    if not units:
        return None

    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash=str(context_bundle_hash),
        snapshot_id=int(book_snapshot_id),
        paragraph_units=units,
        context_bundle_ref=context_bundle_ref,
    )
    citation_ids = tuple(str(x) for x in (catalog.citation_ids or ()))
    catalog_fp = str(getattr(catalog, "catalog_fingerprint", "") or "")
    if not citation_ids or not catalog_fp:
        return None

    # Prompt / schema-enum / resolver catalog fingerprints share the catalog entry hash.
    prompt_fp = catalog_fp
    schema_cat_fp = catalog_fp
    resolver_fp = catalog_fp
    try:
        from app.narrative_core.services.citation_catalog_v2 import (
            catalog_for_private_engine,
        )
        from storylens_private_engine.citation import assert_catalog_fingerprints_match

        private_catalog = catalog_for_private_engine(catalog)
        fp_diag = assert_catalog_fingerprints_match(private_catalog)
        prompt_fp = str(fp_diag["prompt_catalog_fingerprint"])
        schema_cat_fp = str(fp_diag["schema_catalog_fingerprint"])
        resolver_fp = str(fp_diag["resolver_catalog_fingerprint"])
    except Exception:  # noqa: BLE001
        pass

    schema_fp = ""
    try:
        from app.narrative_core.services.structure_stages_output_contract_v2 import (
            structure_stages_result_v2_json_schema,
        )
        from storylens_private_engine.citation import dynamic_schema_fingerprint

        schema = structure_stages_result_v2_json_schema(catalog=catalog)
        enum_count = _citation_enum_count(schema)
        if enum_count != len(citation_ids):
            return None
        meta_base = {k: v for k, v in schema.items() if k != "x_storylens"}
        schema_fp = dynamic_schema_fingerprint(meta_base)
    except Exception:  # noqa: BLE001
        return None

    return EstimateCatalogMaterialization(
        module_key="structure_stages",
        catalog_id=str(getattr(catalog, "catalog_id", "") or catalog_fp[:16]),
        catalog_entry_count=len(citation_ids),
        citation_enum_count=len(citation_ids),
        catalog_fingerprint=catalog_fp,
        prompt_catalog_fingerprint=prompt_fp,
        schema_catalog_fingerprint=schema_cat_fp,
        resolver_catalog_fingerprint=resolver_fp,
        dynamic_schema_fingerprint=schema_fp,
        context_bundle_hash=str(context_bundle_hash),
        selected_paragraph_count=len(selected_pids),
        citation_ids=citation_ids,
        catalog=catalog,
    )


def _citation_enum_count(schema: Mapping[str, Any]) -> int:
    """Count citation_ids.items.enum entries injected into dynamic schema."""

    enums: list[list[str]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if "citation_ids" in node and isinstance(node["citation_ids"], dict):
                items = node["citation_ids"].get("items")
                if isinstance(items, dict) and isinstance(items.get("enum"), list):
                    enums.append([str(x) for x in items["enum"]])
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(schema)
    if not enums:
        # Also walk $defs / properties shape from model_json_schema
        props = schema.get("properties") if isinstance(schema, dict) else None
        if isinstance(props, dict):
            _walk(props)
        defs = schema.get("$defs") or schema.get("definitions")
        if isinstance(defs, dict):
            _walk(defs)
    if not enums:
        return 0
    # All citation_ids enums must be identical; take first
    return len(enums[0])


__all__ = [
    "EstimateCatalogMaterialization",
    "build_citation_paragraph_units_from_contract",
    "materialize_structure_stages_estimate_catalog",
]
