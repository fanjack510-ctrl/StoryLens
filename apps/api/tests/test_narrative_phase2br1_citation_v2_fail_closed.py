"""CHG-058 F8-ish: V2 must not fall back to V1 evidence_refs quote path."""

from __future__ import annotations

import ast
from pathlib import Path

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


def test_f8_v2_enrich_module_forbids_quote_imports() -> None:
    assert_v2_path_forbids_quote_fallback()
    root = Path(__file__).resolve().parents[1] / "app" / "narrative_core" / "services"
    src = (root / "citation_evidence_enrichment_v2.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "quote_resolution" not in node.module
            for alias in node.names:
                assert alias.name not in {
                    "SnapshotQuoteIndex",
                    "resolve_evidence_locator",
                }


def test_f8_v2_unknown_citation_does_not_use_evidence_refs_quote_path() -> None:
    """Unknown citation_id fails closed — never repaired via V1 evidence_refs quotes."""

    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash="aaaaaaaa" + ("b" * 56),
        snapshot_id=7,
        paragraph_units=[
            {
                "chapter_id": 1,
                "paragraph_id": 11,
                "stable_paragraph_id": "s11",
                "content_hash": "h11",
                "text": "合成证据段落。",
            }
        ],
    )
    # Stale / foreign bundle prefix — must not resolve via quote fallback.
    ev = EvidenceCandidate(
        candidate_id="CIT-DEADBEEF-0001",
        book_snapshot_id=7,
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
        confidence=0.5,
        source_context_unit_id=None,
        book_id=1,
        preview="合成证据段落。",
    )
    diag = CitationEvidencePipelineDiagnostics(
        module_key="book_overview",
        evidence_contract_version="v2",
    )
    enriched = enrich_evidence_from_citation_catalog(
        (ev,),
        catalog=catalog,
        book_id=1,
        book_snapshot_id=7,
        module_key="book_overview",
        registered_refs=("book_overview.logline",),
        diagnostics=diag,
    )
    assert len(enriched) == 1
    assert enriched[0].snapshot_paragraph_id is None
    assert diag.citation_rejected_count == 1
    assert diag.quote_resolution_success_count == 0
    assert diag.quote_resolution_rejected_count == 0
    assert diag.failure_boundary == "EVIDENCE_VALIDATION_REJECTED"
