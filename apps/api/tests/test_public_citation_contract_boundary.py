"""CHG-058 — Public citation product contract boundary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.narrative_core.product_contract import (
    BookOverviewResultV2,
    ClaimStatus,
    CitedClaimDto,
)
from app.narrative_core.services.citation_catalog_v2 import (
    build_catalog_from_paragraph_units,
    fingerprints_match,
    format_citation_id,
    parse_citation_id,
)
from app.narrative_core.private_engine_contract.provider_estimate import (
    ProviderCostEstimate,
    ProviderEstimateResult,
)


def test_public_citation_contract_boundary_script() -> None:
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "check_live_citation_v2_boundary.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_cited_claim_and_book_overview_v2_dto() -> None:
    claim = CitedClaimDto(
        value="A story about change",
        status=ClaimStatus.OBSERVED,
        citation_ids=("CIT-ABCDEF01-0001",),
        confidence=0.8,
    )
    not_obs = CitedClaimDto(value=None, status=ClaimStatus.NOT_OBSERVED, citation_ids=())
    dto = BookOverviewResultV2(
        logline=claim,
        premise=claim,
        central_question=claim,
        primary_conflict=claim,
        structure_summary=claim,
        ending_state=not_obs,
    )
    assert dto.contract_version == "v2"


def test_cited_claim_rejects_status_conflicts() -> None:
    with pytest.raises(ValueError):
        CitedClaimDto(value="x", status=ClaimStatus.OBSERVED, citation_ids=())
    with pytest.raises(ValueError):
        CitedClaimDto(
            value=None,
            status=ClaimStatus.NOT_OBSERVED,
            citation_ids=("CIT-ABCDEF01-0001",),
        )


def test_citation_id_contract_stable() -> None:
    cid = format_citation_id("deadbeefcafebabe", 1)
    assert cid == "CIT-DEADBEEF-0001"
    assert parse_citation_id(cid) == ("DEADBEEF", 1)
    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash="deadbeefcafebabe",
        snapshot_id=9,
        paragraph_units=[
            {
                "chapter_id": 1,
                "paragraph_id": 2,
                "stable_paragraph_id": "s2",
                "content_hash": "h2",
                "text": "hello",
            }
        ],
    )
    assert catalog.citation_ids == ("CIT-DEADBEEF-0001",)
    assert fingerprints_match(catalog)


def test_estimate_safe_dict_exposes_v2_and_citation_repair() -> None:
    est = ProviderEstimateResult(
        schema="storylens.provider_estimate_result",
        version="1.0.0",
        request_id="r1",
        provider_key="aliyun_qwen_plus",
        model_id="qwen-plus",
        module_key="book_overview",
        estimated_input_tokens=100,
        estimated_output_tokens=200,
        estimated_total_tokens=300,
        estimate_method="generic_char_heuristic_v1",
        confidence=0.5,
        warnings=(),
        cost=ProviderCostEstimate(
            currency="CNY",
            pricing_version="v1",
            pricing_status="known",
            cost_low=0.01,
            cost_expected=0.02,
            cost_high=0.03,
            max_retry_cost=0.02,
        ),
        estimate_fingerprint="fp",
        max_retries=1,
    )
    payload = est.safe_dict()
    assert payload["evidence_contract_version"] == "v2"
    assert payload["max_repair_count"] == 1
    assert "citation" in str(payload["repair_policy"])
