"""CHG-20260724-058 Citation V2 — product HTTP Replay scenarios.

Direct product-boundary (HTTP Lab + FakeHttpProviderTransport + executor).
Zero real network. Independent temp SQLite per test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, AnalysisRunStage, BookSnapshotParagraph
from app.narrative_core.enums import StageStatus
from app.narrative_core.services.citation_catalog_v2 import build_catalog_from_paragraph_units
from app.narrative_core.services.provider_transport_kind import FakeHttpProviderTransport

# Reuse CHG-057 product harness helpers.
from tests.test_narrative_phase2br1_chg057_acceptance_closure import (  # noqa: E402
    MARKER,
    _assert_fail_closed,
    _assert_no_sensitive,
    _configure_fake_http,
    _create_and_start,
    _module_result_usage,
    _orm_counts,
    _pipeline_diags,
    _provider_attempt_payload,
    product_env,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "provider_http"


def _load_fixture_content(name: str, *, citation_id: str | None = None) -> str:
    raw = (FIXTURE_DIR / name).read_text(encoding="utf-8")
    if citation_id:
        raw = raw.replace("{{CITATION_ID_1}}", citation_id)
    envelope = json.loads(raw)
    content = envelope["choices"][0]["message"]["content"]
    # content is a JSON string of BookOverviewResultV2
    assert isinstance(content, str)
    parsed = json.loads(content)
    assert parsed.get("contract_version") == "v2"
    # Never hardcode CIT-0001 without bundle prefix.
    blob = json.dumps(parsed, ensure_ascii=False)
    assert "CIT-0001" not in blob
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def _build_env_catalog(env: dict[str, Any]) -> Any:
    """Build CitationCatalog matching Live enrich (bundle hash + paragraph units)."""

    analysis_rt = env["runtime"].runtime_factory(
        session=env["session"],
        book_id=env["book"].id,
        use_phase1b_persistence=True,
        dry_run=False,
    )
    _wb, contract = analysis_rt.build_native_context_bundle(
        book_id=int(env["book"].id),
        book_snapshot_id=int(env["snapshot"].id),
        module_keys=("book_overview",),
    )
    units = analysis_rt._paragraph_units_for_citation_catalog(  # noqa: SLF001
        contract=contract,
        book_snapshot_id=int(env["snapshot"].id),
        selected_paragraph_ids=None,
    )
    if not units:
        sp: BookSnapshotParagraph = env["paragraph"]
        units = [
            {
                "chapter_id": sp.chapter_id,
                "paragraph_id": sp.id,
                "stable_paragraph_id": str(sp.stable_paragraph_id or sp.id),
                "content_hash": str(sp.content_hash or "missing"),
                "text": "x" * max(1, int(getattr(sp, "char_end", 0) or 0) - int(getattr(sp, "char_start", 0) or 0)),
            }
        ]
    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash=str(contract.bundle_hash),
        snapshot_id=int(env["snapshot"].id),
        paragraph_units=units,
    )
    assert catalog.citation_ids
    assert all(cid.startswith("CIT-") and cid.count("-") == 2 for cid in catalog.citation_ids)
    assert all(not cid.endswith("-0001") or len(cid.split("-")[1]) == 8 for cid in catalog.citation_ids)
    env["citation_catalog"] = catalog
    env["citation_id_1"] = catalog.citation_ids[0]
    env["analysis_runtime"] = analysis_rt
    env["context_bundle_hash"] = str(contract.bundle_hash)
    return catalog


def _quote_fallback_counts(diags: dict[str, Any]) -> tuple[int, int]:
    return (
        int(diags.get("quote_resolution_success_count") or 0),
        int(diags.get("quote_resolution_rejected_count") or 0),
    )


def test_citation_v2_scenario_a_valid_no_repair(product_env) -> None:
    env = product_env
    catalog = _build_env_catalog(env)
    cid = catalog.citation_ids[0]
    stub = _load_fixture_content("book_overview_v2_http_valid.json", citation_id=cid)
    _configure_fake_http(
        env,
        stub_texts=[stub],
        request_ids=["fake-http-v2-valid-1"],
        request_id="fake-http-v2-valid-1",
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="cit-v2-a")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}

    fake: FakeHttpProviderTransport = env["fake_http"]
    assert len(fake.calls) == 1
    assert len(env["capturing"].calls) == 0

    usage = _module_result_usage(env, run_id)
    contract = dict(usage.get("output_contract") or {})
    diags = _pipeline_diags(env, run_id)
    repair_count = int(
        contract.get("repair_count")
        if contract.get("repair_count") is not None
        else (diags.get("repair_count") or 0)
    )
    assert repair_count == 0
    q_ok, q_rej = _quote_fallback_counts(diags)
    assert q_ok == 0
    assert q_rej == 0

    counts = _orm_counts(env["session"])
    assert counts["assets"] >= 1
    assert counts["versions"] >= 1
    assert counts["evidence"] >= 1
    assert counts["artifacts"] >= 1
    assert counts["model_invocations"] == 0

    result_resp = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results/book_overview")
    assert result_resp.status_code == 200, result_resp.text
    body = result_resp.json()
    assert str(body.get("module_status") or "").lower() == "completed"
    _assert_no_sensitive(json.dumps(body, ensure_ascii=False))


def test_citation_v2_scenario_b_unknown_then_repair(product_env) -> None:
    env = product_env
    catalog = _build_env_catalog(env)
    cid = catalog.citation_ids[0]
    bad = _load_fixture_content("book_overview_v2_http_unknown_citation.json")
    good = _load_fixture_content("book_overview_v2_http_repair_valid.json", citation_id=cid)
    _configure_fake_http(
        env,
        stub_texts=[bad, good],
        request_ids=["fake-http-v2-unknown-1", "fake-http-v2-repair-1"],
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="cit-v2-b")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}

    fake: FakeHttpProviderTransport = env["fake_http"]
    assert len(fake.calls) == 2
    usage = _module_result_usage(env, run_id)
    attempts = list(usage.get("attempts") or [])
    ids = list(usage.get("provider_request_ids") or [])
    cp = _provider_attempt_payload(env["session"], run_id)
    if cp:
        ids = ids or list(cp.get("provider_request_ids") or [])
        attempts = attempts or list(cp.get("attempts") or [])
    assert len(fake.calls) == 2
    assert len(ids) == 2 or len(attempts) == 2

    counts = _orm_counts(env["session"])
    assert counts["assets"] >= 1
    assert counts["evidence"] >= 1
    assert counts["model_invocations"] == 0
    assert len(env["capturing"].calls) == 0


def test_citation_v2_scenario_c_repair_still_invalid(product_env) -> None:
    env = product_env
    _build_env_catalog(env)
    bad = _load_fixture_content("book_overview_v2_http_unknown_citation.json")
    still_bad = _load_fixture_content("book_overview_v2_http_repair_invalid.json")
    _configure_fake_http(
        env,
        stub_texts=[bad, still_bad],
        request_ids=["fake-http-v2-unknown-1", "fake-http-v2-repair-invalid-1"],
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="cit-v2-c")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) == 2

    session: Session = env["session"]
    run = session.get(AnalysisRun, run_id)
    assert run is not None
    assert str(run.status).lower() == "failed"
    counts = _orm_counts(session)
    assert counts["assets"] == 0
    assert counts["versions"] == 0
    assert counts["evidence"] == 0
    assert counts["model_invocations"] == 0

    cp = _provider_attempt_payload(session, run_id)
    ids = list(cp.get("provider_request_ids") or [])
    attempts = list(cp.get("attempts") or [])
    assert len(ids) == 2 or len(attempts) == 2 or len(env["fake_http"].calls) == 2

    result_resp = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results")
    assert result_resp.status_code == 200
    _assert_fail_closed(session, run_id, result_resp.json())
    assert len(env["capturing"].calls) == 0


def test_citation_v2_scenario_d_stale_bundle_fail_closed(product_env) -> None:
    env = product_env
    _build_env_catalog(env)
    stale = _load_fixture_content("book_overview_v2_http_stale_bundle_citation.json")
    _configure_fake_http(
        env,
        stub_texts=[stale, stale],
        request_ids=["fake-http-v2-stale-1", "fake-http-v2-stale-2"],
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="cit-v2-d")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) <= 2
    assert len(env["fake_http"].calls) >= 1

    diags = _pipeline_diags(env, run_id)
    q_ok, _q_rej = _quote_fallback_counts(diags)
    assert q_ok == 0

    counts = _orm_counts(env["session"])
    assert counts["assets"] == 0
    assert counts["evidence"] == 0
    assert counts["model_invocations"] == 0
    result_resp = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results")
    _assert_fail_closed(env["session"], run_id, result_resp.json())
    assert len(env["capturing"].calls) == 0


def test_citation_v2_scenario_e_missing_required_citation(product_env) -> None:
    env = product_env
    catalog = _build_env_catalog(env)
    cid = catalog.citation_ids[0]
    missing = _load_fixture_content(
        "book_overview_v2_http_missing_required_citation.json", citation_id=cid
    )
    _configure_fake_http(
        env,
        stub_texts=[missing, missing],
        request_ids=["fake-http-v2-missing-1", "fake-http-v2-missing-2"],
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="cit-v2-e")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) <= 2
    assert len(env["fake_http"].calls) >= 1

    counts = _orm_counts(env["session"])
    assert counts["assets"] == 0
    assert counts["evidence"] == 0
    assert counts["model_invocations"] == 0
    result_resp = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results")
    _assert_fail_closed(env["session"], run_id, result_resp.json())
    assert len(env["capturing"].calls) == 0


def test_citation_v2_scenario_f_ending_not_observed_success(product_env) -> None:
    env = product_env
    catalog = _build_env_catalog(env)
    cid = catalog.citation_ids[0]
    stub = _load_fixture_content(
        "book_overview_v2_http_not_observed_valid.json", citation_id=cid
    )
    _configure_fake_http(
        env,
        stub_texts=[stub],
        request_ids=["fake-http-v2-not-observed-1"],
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="cit-v2-f")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}
    assert len(env["fake_http"].calls) == 1
    assert len(env["capturing"].calls) == 0

    counts = _orm_counts(env["session"])
    assert counts["assets"] >= 1
    assert counts["evidence"] >= 1
    assert counts["model_invocations"] == 0

    diags = _pipeline_diags(env, run_id)
    q_ok, _ = _quote_fallback_counts(diags)
    assert q_ok == 0

    result_resp = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results/book_overview")
    assert result_resp.status_code == 200
    assert str(result_resp.json().get("module_status") or "").lower() == "completed"
    _assert_no_sensitive(result_resp.text)


# Silence unused-import lint for re-exported fixture symbol.
_ = (product_env, MARKER, StageStatus, select, AnalysisRunStage)
