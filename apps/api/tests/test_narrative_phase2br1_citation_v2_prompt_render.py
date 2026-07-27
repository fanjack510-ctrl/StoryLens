"""CHG-058 — Live provider messages must render [CIT-...] adjacent to source units."""

from __future__ import annotations

from app.narrative_core.services.citation_catalog_v2 import build_catalog_from_paragraph_units
from app.narrative_core.services.data_transfer_consent_guard import (
    PrivateEngineProviderBudgetGuard,
)
from app.narrative_core.services.private_lab_service_adapters import (
    PrivateLabProviderExecutionServiceAdapter,
)
from app.narrative_core.services.provider_input_bundle_resolver import (
    FakeProviderInputBundleResolver,
)
from storylens_private_engine.citation.prompt_render import render_cited_source_blocks


def test_render_cited_blocks_prefix_each_unit():
    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash="abc123deadbeef00",
        snapshot_id=1,
        paragraph_units=[
            {
                "chapter_id": 1,
                "paragraph_id": 1,
                "stable_paragraph_id": "s1",
                "content_hash": "h1",
                "text": "alpha unit",
            },
            {
                "chapter_id": 1,
                "paragraph_id": 2,
                "stable_paragraph_id": "s2",
                "content_hash": "h2",
                "text": "beta unit",
            },
        ],
    )
    blocks = render_cited_source_blocks(catalog)
    assert len(blocks) == 2
    assert blocks[0].startswith(f"[{catalog.citation_ids[0]}]\n")
    assert "alpha unit" in blocks[0]
    assert blocks[1].startswith(f"[{catalog.citation_ids[1]}]\n")
    assert all(not cid.endswith("CIT-0001") for cid in catalog.citation_ids)


def test_provider_adapter_injects_cited_sources_into_user_message():
    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash="abc123deadbeef00",
        snapshot_id=1,
        paragraph_units=[
            {
                "chapter_id": 1,
                "paragraph_id": 1,
                "stable_paragraph_id": "s1",
                "content_hash": "h1",
                "text": "visible paragraph body",
            }
        ],
    )
    cid = catalog.citation_ids[0]
    assert cid.startswith("CIT-")
    assert "CIT-0001" not in cid

    adapter = PrivateLabProviderExecutionServiceAdapter(
        resolver=FakeProviderInputBundleResolver(),
        budget_guard=PrivateEngineProviderBudgetGuard(),
        dry_run=True,
        allow_network=False,
    )
    adapter.execute_module(
        module_key="book_overview",
        request={
            "book_id": 1,
            "book_snapshot_id": 1,
            "dry_run": True,
            "consent_valid": True,
            "estimate_valid": True,
            "context_bundle_hash": catalog.context_bundle_hash,
            "citation_catalog": catalog,
            "allowed_citation_ids": list(catalog.citation_ids),
            "citation_paragraph_units": [
                {
                    "chapter_id": 1,
                    "paragraph_id": 1,
                    "stable_paragraph_id": "s1",
                    "content_hash": "h1",
                    "text": "visible paragraph body",
                }
            ],
        },
        cancellation_ref=None,
    )
    payloads = list(adapter.last_payloads or [])
    assert payloads
    meta = payloads[-1]
    assert meta["cited_sources_injected"] is True
    assert meta["prompt_has_citation_brackets"] is True
    assert cid in meta["prompt_citation_ids"]
    assert meta["evidence_contract_version"] == "v2"
    # Body text must not appear in payload meta (only ids/flags).
    blob = str(meta)
    assert "visible paragraph body" not in blob
