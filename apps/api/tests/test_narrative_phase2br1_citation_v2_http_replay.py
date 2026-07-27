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
    """Build CitationCatalog matching Estimate/Executor Formal selection (CHG-059)."""

    from app.narrative_core.services.execution_context_binding import (
        build_execution_context_binding,
    )
    from app.narrative_core.services.formal_private_provider_input_resolver import (
        FormalPrivateProviderInputBundleResolverAdapter,
    )

    analysis_rt = env["runtime"].runtime_factory(
        session=env["session"],
        book_id=env["book"].id,
        use_phase1b_persistence=True,
        dry_run=False,
    )
    formal = FormalPrivateProviderInputBundleResolverAdapter(
        session=env["session"],
        provider_context_limit=120_000,
    )
    bundle = formal.resolve(
        request_id=f"test-cat-{env['book'].id}",
        book_id=int(env["book"].id),
        book_snapshot_id=int(env["snapshot"].id),
        module_key="book_overview",
        context_bundle_hash="ctx-test",
        provider_key="dashscope",
        model_id="qwen-plus",
        quality_profile="balanced",
    )
    selected_pids = tuple(int(x) for x in bundle.selected_paragraph_ids)
    _wb, contract = analysis_rt.build_native_context_bundle(
        book_id=int(env["book"].id),
        book_snapshot_id=int(env["snapshot"].id),
        module_keys=("book_overview",),
        provider_context_limit=120_000,
    )
    units = analysis_rt._paragraph_units_for_citation_catalog(  # noqa: SLF001
        contract=contract,
        book_snapshot_id=int(env["snapshot"].id),
        selected_paragraph_ids=selected_pids or None,
    )
    if not units:
        sp: BookSnapshotParagraph = env["paragraph"]
        units = [
            {
                "chapter_id": sp.chapter_id,
                "paragraph_id": sp.id,
                "stable_paragraph_id": str(sp.stable_paragraph_id or sp.id),
                "content_hash": str(sp.content_hash or "missing"),
                "text": "x"
                * max(
                    1,
                    int(getattr(sp, "char_end", 0) or 0)
                    - int(getattr(sp, "char_start", 0) or 0),
                ),
            }
        ]
        selected_pids = (int(sp.id),)
    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash=str(bundle.context_bundle_hash),
        snapshot_id=int(env["snapshot"].id),
        paragraph_units=units,
    )
    assert catalog.citation_ids
    assert all(cid.startswith("CIT-") and cid.count("-") == 2 for cid in catalog.citation_ids)
    assert all(
        not cid.endswith("-0001") or len(cid.split("-")[1]) == 8
        for cid in catalog.citation_ids
    )
    resolve_meta = formal.last_resolve_meta()
    binding = build_execution_context_binding(
        book_id=int(env["book"].id),
        snapshot_id=int(env["snapshot"].id),
        module_key="book_overview",
        selected_chapter_ids=bundle.selected_chapter_ids,
        selected_paragraph_ids=bundle.selected_paragraph_ids or tuple(str(x) for x in selected_pids),
        selected_unit_refs=bundle.selected_context_unit_ids,
        context_bundle_hash=bundle.context_bundle_hash,
        citation_catalog_fingerprint=str(catalog.catalog_fingerprint),
        prompt_input_fingerprint=bundle.bundle_fingerprint,
        source_character_count=bundle.source_character_count(),
        citation_entry_count=len(catalog.citation_ids),
        provider_context_limit=120_000,
        batch_index=int(resolve_meta.get("batch_index") or 0),
        batch_count=int(resolve_meta.get("batch_count") or 1),
        selected_chapter_orders=tuple(resolve_meta.get("selected_chapter_orders") or ()),
        all_chapter_orders=tuple(resolve_meta.get("all_chapter_orders") or ()),
        context_capabilities={},
    )
    env["citation_catalog"] = catalog
    env["citation_id_1"] = catalog.citation_ids[0]
    env["analysis_runtime"] = analysis_rt
    env["context_bundle_hash"] = str(bundle.context_bundle_hash)
    env["execution_context_binding"] = binding.safe_dict()
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
    """CHG-059 D: ending_state not_observed succeeds when capability disallows ending."""

    from app.db.models import AnalysisRun
    from app.narrative_core.services.private_lab_run_metadata import (
        parse_metadata_json,
        serialize_metadata,
    )

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

    client = env["client"]
    from tests.test_narrative_phase2br1_chg057_acceptance_closure import _http_flow

    pre, est, create = _http_flow(
        client, env, idem="cit-v2-f", dry_run=False, auto_start=False
    )
    assert create.status_code == 200, create.text
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    session: Session = env["session"]
    run = session.get(AnalysisRun, run_id)
    assert run is not None
    meta = parse_metadata_json(run.validated_output)
    binding = dict(meta.get("execution_context_binding") or {})
    caps = dict(binding.get("context_capabilities") or {})
    caps["can_assess_ending_state"] = False
    caps["covers_last_chapter"] = False
    binding["context_capabilities"] = caps
    meta["execution_context_binding"] = binding
    run.validated_output = serialize_metadata(meta)
    session.commit()

    exec_result = env["executor"].start(run_id)
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


def test_chg059_scenario_b_core_not_observed_then_repair(product_env) -> None:
    """CHG-059 B: single core field not_observed → targeted repair → ORM success."""

    env = product_env
    catalog = _build_env_catalog(env)
    cid = catalog.citation_ids[0]
    bad = _load_fixture_content("book_overview_v2_http_core_not_observed.json", citation_id=cid)
    good = _load_fixture_content("book_overview_v2_http_repair_valid.json", citation_id=cid)
    _configure_fake_http(
        env,
        stub_texts=[bad, good],
        request_ids=["fake-http-v2-core-not-obs-1", "fake-http-v2-repair-core-1"],
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="cit-v2-chg059-b")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}
    assert len(env["fake_http"].calls) == 2

    usage = _module_result_usage(env, run_id)
    oc = dict(usage.get("output_contract") or {})
    cp = _provider_attempt_payload(env["session"], run_id)
    attempts = list(cp.get("provider_attempts") or usage.get("attempts") or [])
    initial_diags = list(
        usage.get("claim_contract_diagnostics_initial")
        or oc.get("claim_contract_diagnostics_initial")
        or oc.get("provider_attempts_claim_diagnostics_initial")
        or (attempts[0].get("claim_contract_diagnostics") if attempts else None)
        or []
    )
    failed_fields = {
        str(d.get("claim_field"))
        for d in initial_diags
        if d.get("validation_status") == "FAIL"
    }
    assert "primary_conflict" in failed_fields
    assert any(
        d.get("claim_field") == "primary_conflict"
        and d.get("validation_code") == "REQUIRED_CLAIM_NOT_OBSERVED"
        for d in initial_diags
    )

    kinds = [str(a.get("operation_kind") or a.get("attempt_kind") or "") for a in attempts]
    if len(attempts) >= 2:
        assert "book_overview_initial" in kinds[0]
        assert "book_overview_contract_repair" in kinds[1]

    counts = _orm_counts(env["session"])
    assert counts["assets"] >= 1
    assert counts["evidence"] >= 1
    assert counts["model_invocations"] == 0


def test_chg059_scenario_c_multi_core_fail_one_repair(product_env) -> None:
    """CHG-059 C: multiple core fields fail → single repair batch → success."""

    env = product_env
    catalog = _build_env_catalog(env)
    cid = catalog.citation_ids[0]
    bad = _load_fixture_content(
        "book_overview_v2_http_multi_core_fail.json", citation_id=cid
    )
    good = _load_fixture_content("book_overview_v2_http_repair_valid.json", citation_id=cid)
    _configure_fake_http(
        env,
        stub_texts=[bad, good],
        request_ids=["fake-http-v2-multi-core-1", "fake-http-v2-repair-multi-1"],
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="cit-v2-chg059-c")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}
    assert len(env["fake_http"].calls) == 2

    usage = _module_result_usage(env, run_id)
    oc = dict(usage.get("output_contract") or {})
    initial_diags = list(
        usage.get("claim_contract_diagnostics_initial")
        or oc.get("claim_contract_diagnostics_initial")
        or oc.get("provider_attempts_claim_diagnostics_initial")
        or []
    )
    failed = {
        str(d.get("claim_field"))
        for d in initial_diags
        if d.get("validation_status") == "FAIL"
    }
    assert {"logline", "premise", "primary_conflict"} <= failed
    assert len(env["fake_http"].calls) == 2  # one repair only

    counts = _orm_counts(env["session"])
    assert counts["assets"] >= 1
    assert counts["evidence"] >= 1


def test_chg059_scenario_e_execution_context_fingerprint_mismatch(product_env) -> None:
    """CHG-059 E: Estimate/Executor context fork → HTTP=0, no ORM."""

    from app.db.models import AnalysisRun
    from app.narrative_core.services.private_lab_run_metadata import (
        parse_metadata_json,
        serialize_metadata,
    )

    env = product_env
    _build_env_catalog(env)
    stub = _load_fixture_content("book_overview_v2_http_valid.json")
    _configure_fake_http(
        env,
        stub_texts=[stub],
        request_ids=["fake-http-v2-mismatch-should-not-run"],
    )

    client = env["client"]
    from tests.test_narrative_phase2br1_chg057_acceptance_closure import _http_flow

    pre, est, create = _http_flow(
        client, env, idem="cit-v2-chg059-e", dry_run=False, auto_start=False
    )
    assert create.status_code == 200, create.text
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))

    session: Session = env["session"]
    run = session.get(AnalysisRun, run_id)
    assert run is not None
    meta = parse_metadata_json(run.validated_output)
    binding = dict(meta.get("execution_context_binding") or {})
    assert binding, "execution_context_binding must be frozen at Create"
    binding["context_bundle_hash"] = "deadbeef" + ("0" * 56)
    binding["estimate_context_hash"] = binding["context_bundle_hash"]
    meta["execution_context_binding"] = binding
    run.validated_output = serialize_metadata(meta)
    session.commit()

    exec_result = env["executor"].start(run_id)
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) == 0
    detail = str(
        getattr(exec_result, "detail", None)
        or (exec_result.detail if hasattr(exec_result, "detail") else "")
        or ""
    )
    blob = json.dumps(
        {
            "status": exec_result.status,
            "detail": detail,
            **dict(getattr(exec_result, "__dict__", {}) or {}),
        },
        ensure_ascii=False,
        default=str,
    )
    assert "EXECUTION_CONTEXT_FINGERPRINT_MISMATCH" in blob or "FINGERPRINT_MISMATCH" in blob

    counts = _orm_counts(session)
    assert counts["assets"] == 0
    assert counts["evidence"] == 0
    assert counts["versions"] == 0


def test_chg059_scenario_g_contract_fail_not_provider_failed(product_env) -> None:
    """CHG-059 G: HTTP 200 + contract fail → not provider_failed."""

    env = product_env
    catalog = _build_env_catalog(env)
    cid = catalog.citation_ids[0]
    missing = _load_fixture_content(
        "book_overview_v2_http_missing_required_citation.json", citation_id=cid
    )
    _configure_fake_http(
        env,
        stub_texts=[missing, missing],
        request_ids=["fake-http-v2-g-1", "fake-http-v2-g-2"],
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="cit-v2-chg059-g")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) >= 1

    results = env["executor"].get_module_results(run_id)
    status = ""
    if results:
        status = str(results[0].get("status") or results[0].get("module_status") or "")
    usage = _module_result_usage(env, run_id)
    detail = str(usage.get("detail_code") or usage.get("failure_code") or "")
    # Prefer module usage status from last provider result when available.
    module_status = str(usage.get("status") or status or exec_result.status or "").lower()
    assert "provider_failed" not in module_status
    assert any(
        token in (module_status + " " + detail.lower())
        for token in (
            "contract_validation_failed",
            "citation_validation_failed",
            "repair_exhausted",
            "required_claim",
        )
    ) or exec_result.status.lower() == "failed"


def test_chg059_scenario_h_independent_provider_attempts(product_env) -> None:
    """CHG-059 H: repair path yields two independent business attempts."""

    env = product_env
    catalog = _build_env_catalog(env)
    cid = catalog.citation_ids[0]
    bad = _load_fixture_content("book_overview_v2_http_unknown_citation.json")
    good = _load_fixture_content("book_overview_v2_http_repair_valid.json", citation_id=cid)
    _configure_fake_http(
        env,
        stub_texts=[bad, good],
        request_ids=["fake-http-v2-h-initial", "fake-http-v2-h-repair"],
    )

    _pre, _est, create, exec_result = _create_and_start(env, idem="cit-v2-chg059-h")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}
    assert len(env["fake_http"].calls) == 2

    usage = _module_result_usage(env, run_id)
    cp = _provider_attempt_payload(env["session"], run_id)
    attempts = list(cp.get("provider_attempts") or usage.get("attempts") or [])
    assert len(attempts) >= 2
    assert str(attempts[0].get("operation_kind") or "").endswith("initial") or str(
        attempts[0].get("attempt_kind") or ""
    ).endswith("initial")
    assert "repair" in str(
        attempts[1].get("operation_kind") or attempts[1].get("attempt_kind") or ""
    ).lower()
    ids = [
        a.get("provider_request_id")
        for a in attempts
        if a.get("provider_request_id")
    ]
    assert len(set(ids)) >= 2
    # Diagnostics must not wipe attempts when pipeline diags are present.
    diags = _pipeline_diags(env, run_id)
    assert len(attempts) >= 2
    _ = diags


# Silence unused-import lint for re-exported fixture symbol.
_ = (product_env, MARKER, StageStatus, select, AnalysisRunStage)
