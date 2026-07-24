"""Citation → EvidenceCandidate enrichment (CHG-058 V2 path).

Resolves locators via CitationCatalogResolver only.
MUST NOT call quote_resolution.resolve_evidence_locator / SnapshotQuoteIndex.
"""

from __future__ import annotations

from typing import Any, Sequence

from app.narrative_core.enums import EvidenceRole
from app.narrative_core.private_engine_contract.evidence import EvidenceCandidate
from app.narrative_core.services.citation_catalog_v2 import (
    CitationCatalog,
    CitationCatalogResolver,
    CitationResolveFailure,
    ResolvedCitationLocator,
)
from app.narrative_core.services.output_ref_resolution import canonicalize_evidence_target_ref
from app.narrative_core.services.live_module_pipeline_diagnostics import (
    CitationEvidencePipelineDiagnostics,
    LiveModulePipelineDiagnostics,
    merge_rejection_codes,
)

_BANNED_QUOTE_FALLBACK_SYMBOLS = frozenset(
    {
        "resolve_evidence_locator",
        "SnapshotQuoteIndex",
        "resolve_by_quote_key",
        "resolve_by_unique_quote",
        "fallback_quote_match",
        "fuzzy_quote_match",
        "paragraph_id_guess",
        "stable_id_guess",
    }
)


def assert_v2_path_forbids_quote_fallback() -> None:
    """Runtime/test gate: V2 enrichment module must not import banned quote symbols."""

    import ast
    from pathlib import Path

    import app.narrative_core.services.citation_evidence_enrichment_v2 as self_mod

    src = Path(self_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if "quote_resolution" in mod:
                raise AssertionError("V2 path must not import quote_resolution")
            for alias in node.names:
                if alias.name in _BANNED_QUOTE_FALLBACK_SYMBOLS:
                    raise AssertionError(f"V2 path must not import {alias.name}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _BANNED_QUOTE_FALLBACK_SYMBOLS:
                raise AssertionError(f"V2 path must not call {node.func.id}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _BANNED_QUOTE_FALLBACK_SYMBOLS:
                raise AssertionError(f"V2 path must not call {node.func.attr}")


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _citation_id_from_candidate(ev: EvidenceCandidate) -> str:
    """Evidence candidates on V2 path carry citation_id in candidate_id (or key)."""

    cid = str(ev.candidate_id or "").strip()
    if cid.upper().startswith("CIT-"):
        return cid
    # Some builders may stash citation under extraction_method metadata-style keys —
    # keep candidate_id as the sole authoritative citation_id per contract.
    return cid


def enrich_evidence_from_citation_catalog(
    evidence: Sequence[EvidenceCandidate],
    *,
    catalog: CitationCatalog,
    book_id: int,
    book_snapshot_id: int,
    module_key: str,
    registered_refs: Sequence[str],
    asset_candidates: Sequence[Any] = (),
    diagnostics: LiveModulePipelineDiagnostics
    | CitationEvidencePipelineDiagnostics
    | None = None,
) -> tuple[EvidenceCandidate, ...]:
    """Resolve citation_id evidence via CitationCatalogResolver only."""

    if not evidence:
        return ()

    resolver = CitationCatalogResolver()
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
            if hasattr(diagnostics, "target_ref_resolved_count"):
                if resolution.resolution_status == "RESOLVED":
                    diagnostics.target_ref_resolved_count += 1
                else:
                    diagnostics.target_ref_rejected_count += 1
                    if hasattr(diagnostics, "evidence_rejection_codes"):
                        diagnostics.evidence_rejection_codes = merge_rejection_codes(
                            list(diagnostics.evidence_rejection_codes)
                            + [resolution.resolution_code]
                        )
                    elif hasattr(diagnostics, "rejection_codes"):
                        diagnostics.rejection_codes = merge_rejection_codes(
                            list(diagnostics.rejection_codes) + [resolution.resolution_code]
                        )

        canonical = resolution.canonical_output_ref or ev.target_output_ref
        citation_id = _citation_id_from_candidate(ev)
        result = resolver.resolve(
            citation_id,
            catalog,
            expected_bundle_hash=catalog.context_bundle_hash,
            expected_snapshot_id=catalog.snapshot_id,
            raise_on_error=False,
        )

        if isinstance(result, CitationResolveFailure):
            if diagnostics is not None:
                if hasattr(diagnostics, "citation_rejected_count"):
                    diagnostics.citation_rejected_count += 1
                    code = str(result.code)
                    if "STALE" in code:
                        diagnostics.stale_citation_count += 1
                    if "UNKNOWN" in code:
                        diagnostics.unknown_citation_count += 1
                    if "MISMATCH" in code:
                        diagnostics.catalog_mismatch_count += 1
                    diagnostics.rejection_codes = merge_rejection_codes(
                        list(getattr(diagnostics, "rejection_codes", []) or []) + [code]
                    )
                if hasattr(diagnostics, "evidence_rejection_codes"):
                    diagnostics.evidence_rejection_codes = merge_rejection_codes(
                        list(diagnostics.evidence_rejection_codes) + [str(result.code)]
                    )
                if not getattr(diagnostics, "failure_boundary", None):
                    diagnostics.failure_boundary = "EVIDENCE_VALIDATION_REJECTED"
                    diagnostics.failure_code = str(result.code)
            # Keep unresolved candidate for fail-closed validation (no quote fallback).
            enriched.append(
                EvidenceCandidate(
                    candidate_id=ev.candidate_id,
                    book_snapshot_id=ev.book_snapshot_id,
                    snapshot_chapter_id=ev.snapshot_chapter_id,
                    snapshot_paragraph_id=ev.snapshot_paragraph_id,
                    stable_paragraph_id=ev.stable_paragraph_id,
                    paragraph_content_hash=str(ev.paragraph_content_hash or ""),
                    start_offset=ev.start_offset,
                    end_offset=ev.end_offset,
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
            continue

        assert isinstance(result, ResolvedCitationLocator)
        if diagnostics is not None and hasattr(diagnostics, "citation_resolved_count"):
            diagnostics.citation_resolved_count += 1
            diagnostics.locator_validation_count += 1
        if diagnostics is not None and hasattr(diagnostics, "evidence_id_resolved_count"):
            diagnostics.evidence_id_resolved_count += 1

        pid = _as_int(result.paragraph_id)
        chapter = _as_int(result.chapter_id)
        snap = _as_int(result.snapshot_id)
        enriched.append(
            EvidenceCandidate(
                candidate_id=ev.candidate_id,
                book_snapshot_id=int(snap if snap is not None else book_snapshot_id),
                snapshot_chapter_id=chapter,
                snapshot_paragraph_id=pid,
                stable_paragraph_id=str(result.stable_paragraph_id)
                if result.stable_paragraph_id is not None
                else None,
                paragraph_content_hash=str(result.content_hash or ""),
                start_offset=int(result.start_offset),
                end_offset=int(result.end_offset),
                evidence_role=ev.evidence_role
                if isinstance(ev.evidence_role, EvidenceRole)
                else EvidenceRole(str(ev.evidence_role)),
                target_module_key=ev.target_module_key,
                target_output_ref=str(canonical),
                extraction_method=ev.extraction_method or "citation_catalog_v2",
                confidence=ev.confidence,
                source_context_unit_id=ev.source_context_unit_id,
                book_id=ev.book_id if ev.book_id is not None else book_id,
                preview="",  # never persist citation body text
                from_derived_summary=ev.from_derived_summary,
                provider_output_ref=provider_ref or ev.provider_output_ref,
            )
        )
    return tuple(enriched)


__all__ = [
    "assert_v2_path_forbids_quote_fallback",
    "enrich_evidence_from_citation_catalog",
]
