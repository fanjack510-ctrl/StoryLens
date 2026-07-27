"""CHG-058 — V2 enrich path must not invoke legacy quote fallback."""

from __future__ import annotations

from app.narrative_core.enums import EvidenceRole, WholeBookModuleKey
from app.narrative_core.private_engine_contract.evidence import EvidenceCandidate
from app.narrative_core.services.citation_catalog_v2 import build_catalog_from_paragraph_units
from app.narrative_core.services.citation_evidence_enrichment_v2 import (
    assert_v2_path_forbids_quote_fallback,
    enrich_evidence_from_citation_catalog,
)
from app.narrative_core.services.live_module_pipeline_diagnostics import (
    CitationEvidencePipelineDiagnostics,
)


def test_v2_enrich_resolves_citation_without_quote_index() -> None:
    assert_v2_path_forbids_quote_fallback()
    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash="abcdef0123456789deadbeef",
        snapshot_id=42,
        paragraph_units=[
            {
                "chapter_id": 7,
                "paragraph_id": 101,
                "stable_paragraph_id": "stable-101",
                "content_hash": "hash-101",
                "text": "alpha paragraph body for citation",
            }
        ],
    )
    citation_id = catalog.citation_ids[0]
    assert citation_id.startswith("CIT-")
    assert "ABCDEF01" in citation_id.upper() or "abcdef01".upper()[:8] in citation_id

    ev = EvidenceCandidate(
        candidate_id=citation_id,
        book_snapshot_id=42,
        snapshot_chapter_id=None,
        snapshot_paragraph_id=None,
        stable_paragraph_id=None,
        paragraph_content_hash="",
        start_offset=None,
        end_offset=None,
        evidence_role=EvidenceRole.SUPPORT,
        target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        target_output_ref="book_overview.logline",
        extraction_method="citation_catalog_v2",
        confidence=0.9,
        source_context_unit_id=None,
        book_id=1,
        preview="",
    )
    diag = CitationEvidencePipelineDiagnostics(
        module_key="book_overview",
        evidence_contract_version="v2",
    )
    enriched = enrich_evidence_from_citation_catalog(
        (ev,),
        catalog=catalog,
        book_id=1,
        book_snapshot_id=42,
        module_key="book_overview",
        registered_refs=("book_overview.logline",),
        diagnostics=diag,
    )
    assert len(enriched) == 1
    assert enriched[0].snapshot_paragraph_id == 101
    assert enriched[0].snapshot_chapter_id == 7
    assert enriched[0].paragraph_content_hash == "hash-101"
    assert diag.citation_resolved_count == 1
    assert diag.citation_rejected_count == 0
    assert diag.quote_resolution_success_count == 0
    assert diag.quote_resolution_rejected_count == 0


def test_v2_unknown_citation_fail_closed_no_quote_fallback() -> None:
    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash="1111222233334444",
        snapshot_id=1,
        paragraph_units=[
            {
                "chapter_id": 1,
                "paragraph_id": 1,
                "stable_paragraph_id": "s1",
                "content_hash": "h1",
                "text": "body",
            }
        ],
    )
    ev = EvidenceCandidate(
        candidate_id="CIT-DEADBEEF-0001",
        book_snapshot_id=1,
        snapshot_chapter_id=None,
        snapshot_paragraph_id=None,
        stable_paragraph_id=None,
        paragraph_content_hash="",
        start_offset=None,
        end_offset=None,
        evidence_role=EvidenceRole.SUPPORT,
        target_module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        target_output_ref="book_overview.premise",
        extraction_method="citation_catalog_v2",
        confidence=0.5,
        source_context_unit_id=None,
        book_id=1,
    )
    diag = CitationEvidencePipelineDiagnostics(module_key="book_overview")
    enriched = enrich_evidence_from_citation_catalog(
        (ev,),
        catalog=catalog,
        book_id=1,
        book_snapshot_id=1,
        module_key="book_overview",
        registered_refs=("book_overview.premise",),
        diagnostics=diag,
    )
    assert len(enriched) == 1
    assert enriched[0].snapshot_paragraph_id is None
    assert diag.citation_rejected_count == 1
    assert diag.failure_boundary == "EVIDENCE_VALIDATION_REJECTED"
    assert diag.quote_resolution_success_count == 0
