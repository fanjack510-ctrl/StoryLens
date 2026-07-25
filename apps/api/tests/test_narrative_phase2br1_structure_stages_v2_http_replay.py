"""CHG-20260725-001 Structure Stages V2 — product HTTP Replay scenarios A–J.

Direct product-boundary (HTTP Lab + FakeHttpProviderTransport + executor).
Zero real network. Independent temp SQLite per test.

Book overview HTTP replay coverage remains in
``test_narrative_phase2br1_citation_v2_http_replay.py`` (separate module).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun,
    BookSnapshotParagraph,
    Chapter,
    NarrativeAssetVersion,
    Paragraph,
)
from app.narrative_core.services.candidate_persistence_adapter import (
    Phase1BCandidatePersistenceSink,
)
from app.narrative_core.services.provider_transport_kind import FakeHttpProviderTransport
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.structure_stages_output_contract_v2 import (
    FAILURE_STAGE_RANGE_OVERLAP,
)

from tests.test_narrative_phase2br1_chg057_acceptance_closure import (  # noqa: E402
    MARKER,
    _assert_fail_closed,
    _assert_no_sensitive,
    _configure_fake_http,
    _http_flow,
    _module_result_usage,
    _orm_counts,
    _pipeline_diags,
    _provider_attempt_payload,
    product_env,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "provider_http"
SS_MODULES = ("structure_stages",)


def _load_fixture_content(name: str, *, citation_ids: list[str] | None = None) -> str:
    raw = (FIXTURE_DIR / name).read_text(encoding="utf-8")
    if citation_ids:
        for index, cid in enumerate(citation_ids, start=1):
            raw = raw.replace(f"{{{{CITATION_ID_{index}}}}}", cid)
    envelope = json.loads(raw)
    content = envelope["choices"][0]["message"]["content"]
    assert isinstance(content, str)
    parsed = json.loads(content)
    assert parsed.get("contract_version") == "v2"
    blob = json.dumps(parsed, ensure_ascii=False)
    assert "CIT-0001" not in blob
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def _ensure_four_paragraph_snapshot(env: dict[str, Any]) -> None:
    """Extend product_env book to ≥4 paragraphs and refresh snapshot."""

    session: Session = env["session"]
    book = env["book"]
    chapter = session.scalars(select(Chapter).where(Chapter.book_id == book.id)).first()
    assert chapter is not None
    texts = ["合成段落甲。", "合成段落乙。", "合成段落丙。", "合成段落丁。"]
    existing = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.book_id == book.id)
            .order_by(Paragraph.paragraph_index)
        ).all()
    )
    if len(existing) >= 4:
        return
    for idx in range(len(existing), 4):
        text = texts[idx]
        session.add(
            Paragraph(
                id=f"B{book.id:04d}-C0001-P{idx + 1:04d}",
                book_id=book.id,
                chapter_id=chapter.id,
                paragraph_index=idx + 1,
                raw_text=text,
                normalized_text=text,
                char_start=idx * 10,
                char_end=idx * 10 + len(text),
            )
        )
    session.commit()
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    env["snapshot"] = snapshot
    paragraph = session.scalars(
        select(BookSnapshotParagraph)
        .where(BookSnapshotParagraph.snapshot_id == snapshot.id)
        .order_by(BookSnapshotParagraph.paragraph_order)
    ).first()
    assert paragraph is not None
    env["paragraph"] = paragraph
    snap_paras = list(
        session.scalars(
            select(BookSnapshotParagraph)
            .where(BookSnapshotParagraph.snapshot_id == snapshot.id)
            .order_by(BookSnapshotParagraph.paragraph_order)
        ).all()
    )
    assert len(snap_paras) >= 4


def _build_ss_env_catalog(env: dict[str, Any]) -> Any:
    """Build CitationCatalog for structure_stages Formal selection (≥4 citation_ids)."""

    from app.narrative_core.services.citation_catalog_v2 import build_catalog_from_paragraph_units
    from app.narrative_core.services.execution_context_binding import (
        build_execution_context_binding,
    )
    from app.narrative_core.services.formal_private_provider_input_resolver import (
        FormalPrivateProviderInputBundleResolverAdapter,
    )

    _ensure_four_paragraph_snapshot(env)
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
        request_id=f"test-ss-cat-{env['book'].id}",
        book_id=int(env["book"].id),
        book_snapshot_id=int(env["snapshot"].id),
        module_key="structure_stages",
        context_bundle_hash="ctx-test-ss",
        provider_key="dashscope",
        model_id="qwen-plus",
        quality_profile="balanced",
    )
    selected_pids = tuple(int(x) for x in bundle.selected_paragraph_ids)
    _wb, contract = analysis_rt.build_native_context_bundle(
        book_id=int(env["book"].id),
        book_snapshot_id=int(env["snapshot"].id),
        module_keys=("structure_stages",),
        provider_context_limit=120_000,
    )
    units = analysis_rt._paragraph_units_for_citation_catalog(  # noqa: SLF001
        contract=contract,
        book_snapshot_id=int(env["snapshot"].id),
        selected_paragraph_ids=selected_pids or None,
    )
    if len(units) < 4:
        snap_paras = list(
            env["session"].scalars(
                select(BookSnapshotParagraph)
                .where(BookSnapshotParagraph.snapshot_id == env["snapshot"].id)
                .order_by(BookSnapshotParagraph.paragraph_order)
            ).all()
        )
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
            for sp in snap_paras[:4]
        ]
        selected_pids = tuple(int(sp.id) for sp in snap_paras[:4])
    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash=str(bundle.context_bundle_hash),
        snapshot_id=int(env["snapshot"].id),
        paragraph_units=units,
    )
    assert len(catalog.citation_ids) >= 4
    assert all(cid.startswith("CIT-") and cid.count("-") == 2 for cid in catalog.citation_ids)
    resolve_meta = formal.last_resolve_meta()
    binding = build_execution_context_binding(
        book_id=int(env["book"].id),
        snapshot_id=int(env["snapshot"].id),
        module_key="structure_stages",
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
    env["citation_ids"] = list(catalog.citation_ids)
    env["analysis_runtime"] = analysis_rt
    env["context_bundle_hash"] = str(bundle.context_bundle_hash)
    env["execution_context_binding"] = binding.safe_dict()
    return catalog


def _default_ss_context_capabilities(*, local_only: bool = False) -> dict[str, Any]:
    """Capabilities aligned with ≥4-paragraph single-chapter product_env extension."""

    from dataclasses import asdict

    try:
        from storylens_private_engine.citation import derive_structure_context_capabilities

        caps_obj = derive_structure_context_capabilities(
            selected_chapter_orders=(1,),
            all_chapter_orders=(1,),
            selected_paragraph_count=2 if local_only else 4,
            batch_index=0,
            batch_count=1,
        )
        caps = asdict(caps_obj)
        caps["selected_chapter_orders"] = [1]
        caps["all_chapter_orders"] = [1]
        if local_only:
            caps["can_identify_span_stages"] = False
            caps["is_full_book_coverage"] = False
        return caps
    except Exception:  # noqa: BLE001
        return {
            "selected_chapter_orders": [1],
            "all_chapter_orders": [1],
            "selected_paragraph_count": 2 if local_only else 4,
            "selected_chapter_count": 1,
            "batch_index": 0,
            "batch_count": 1,
            "can_identify_local_stages": True,
            "can_identify_span_stages": not local_only,
            "is_full_book_coverage": not local_only,
        }


def _patch_ss_context_capabilities(
    env: dict[str, Any],
    run_id: int,
    *,
    local_only: bool = False,
) -> None:
    """Freeze derived structure capabilities on the Lab run before Executor start."""

    from app.db.models import AnalysisRun
    from app.narrative_core.services.private_lab_run_metadata import (
        parse_metadata_json,
        serialize_metadata,
    )

    session: Session = env["session"]
    run = session.get(AnalysisRun, int(run_id))
    assert run is not None
    meta = parse_metadata_json(run.validated_output)
    caps = _default_ss_context_capabilities(local_only=local_only)
    binding = dict(meta.get("execution_context_binding") or {})
    binding["context_capabilities"] = caps
    meta["execution_context_binding"] = binding
    meta["context_capabilities"] = caps
    run.validated_output = serialize_metadata(meta)
    session.commit()


def _create_and_start_ss(
    env: dict[str, Any],
    *,
    idem: str,
    local_only: bool = False,
) -> tuple[Any, Any, Any, Any]:
    client = env["client"]
    pre, est, create = _http_flow(
        client,
        env,
        idem=idem,
        dry_run=False,
        auto_start=False,
        modules=SS_MODULES,
    )
    assert pre.status_code == 200, pre.text
    assert est.status_code == 200, est.text
    assert create.status_code == 200, create.text
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    _patch_ss_context_capabilities(env, run_id, local_only=local_only)
    exec_result = env["executor"].start(run_id)
    return pre, est, create, exec_result


def _quote_fallback_counts(diags: dict[str, Any]) -> tuple[int, int]:
    return (
        int(diags.get("quote_resolution_success_count") or 0),
        int(diags.get("quote_resolution_rejected_count") or 0),
    )


def _execution_context_match(env: dict[str, Any], run_id: int) -> bool | None:
    usage = _module_result_usage(env, run_id)
    ctx_diag = dict(usage.get("execution_context_diagnostics") or {})
    if not ctx_diag:
        cp = _provider_attempt_payload(env["session"], run_id)
        ctx_diag = dict(cp.get("execution_context_diagnostics") or {})
    if ctx_diag:
        return bool(
            ctx_diag.get("execution_context_fingerprints_match")
            or ctx_diag.get("all_execution_context_fingerprints_match")
        )
    return None


def _assert_ss_fail_closed(session: Session, run_id: int, result_json: dict[str, Any]) -> None:
    _assert_fail_closed(session, run_id, result_json)
    modules = list(result_json.get("modules") or [])
    ss = next((m for m in modules if m.get("module_key") == "structure_stages"), None)
    if ss is not None:
        assert str(ss.get("module_status") or "").lower() != "completed"


def test_structure_stages_v2_scenario_a_valid_no_repair(product_env) -> None:
    env = product_env
    catalog = _build_ss_env_catalog(env)
    cids = list(catalog.citation_ids[:4])
    stub = _load_fixture_content("structure_stages_v2_http_valid.json", citation_ids=cids)
    _configure_fake_http(
        env,
        stub_texts=[stub],
        request_ids=["fake-http-ss-v2-valid-1"],
    )

    _pre, _est, create, exec_result = _create_and_start_ss(env, idem="ss-v2-a")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}, exec_result.detail

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

    ctx_match = _execution_context_match(env, run_id)
    if ctx_match is not None:
        assert ctx_match is True
    assert (
        contract.get("dto_validation_status") == "SUCCESS"
        or diags.get("dto_validation_status") == "SUCCESS"
    )
    assert diags.get("dto_mapper_status") in {"mapped", "SUCCESS", "success", None} or (
        diags.get("mapper_status") in {"mapped", "SUCCESS", "success"}
    )
    stage_candidates = int(
        diags.get("stage_candidate_count")
        or diags.get("private_candidate_count")
        or diags.get("semantic_claim_count")
        or 0
    )
    assert stage_candidates >= 1
    assert int(diags.get("citation_resolved_count") or 0) >= 1
    assert int(diags.get("evidence_valid_count") or diags.get("evidence_written_count") or 0) >= 1
    assert diags.get("transaction_committed") is True or (
        env["executor"].get_module_results(run_id)[0]
        .get("persistence_summary", {})
        .get("persistence_complete")
        is True
    )
    assert diags.get("persistence_complete") is True or diags.get("transaction_committed") is True

    counts = _orm_counts(env["session"])
    assert counts["assets"] >= 1
    assert counts["versions"] >= 1
    assert counts["evidence"] >= 1
    assert counts["artifacts"] >= 1
    assert counts["model_invocations"] == 0

    result_resp = env["client"].get(
        f"/api/v1/whole-book-runs/{run_id}/results/structure_stages"
    )
    assert result_resp.status_code == 200, result_resp.text
    body = result_resp.json()
    assert str(body.get("module_status") or "").lower() == "completed"
    payload = dict(body.get("payload") or {})
    stages = list(payload.get("stages") or payload.get("stages_v2") or ())
    assert len(stages) >= 1
    _assert_no_sensitive(json.dumps(body, ensure_ascii=False))


def test_structure_stages_v2_scenario_b_missing_summary_one_repair(product_env) -> None:
    env = product_env
    catalog = _build_ss_env_catalog(env)
    cids = list(catalog.citation_ids[:4])
    bad = _load_fixture_content(
        "structure_stages_v2_http_missing_summary_citation.json", citation_ids=cids
    )
    good = _load_fixture_content("structure_stages_v2_http_repair_valid.json", citation_ids=cids)
    _configure_fake_http(
        env,
        stub_texts=[bad, good],
        request_ids=["fake-http-ss-v2-missing-1", "fake-http-ss-v2-repair-1"],
    )

    _pre, _est, create, exec_result = _create_and_start_ss(env, idem="ss-v2-b")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}
    assert len(env["fake_http"].calls) == 2

    usage = _module_result_usage(env, run_id)
    assert int(usage.get("output_contract", {}).get("repair_count") or usage.get("retry_count") or 0) == 1
    counts = _orm_counts(env["session"])
    assert counts["assets"] >= 1
    assert counts["evidence"] >= 1
    assert counts["model_invocations"] == 0


def test_structure_stages_v2_scenario_c_multi_fail_one_repair(product_env) -> None:
    env = product_env
    catalog = _build_ss_env_catalog(env)
    cids = list(catalog.citation_ids[:4])
    bad = _load_fixture_content("structure_stages_v2_http_multi_fail.json", citation_ids=cids)
    good = _load_fixture_content("structure_stages_v2_http_repair_valid.json", citation_ids=cids)
    _configure_fake_http(
        env,
        stub_texts=[bad, good],
        request_ids=["fake-http-ss-v2-multi-1", "fake-http-ss-v2-repair-multi-1"],
    )

    _pre, _est, create, exec_result = _create_and_start_ss(env, idem="ss-v2-c")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}
    assert len(env["fake_http"].calls) == 2

    usage = _module_result_usage(env, run_id)
    oc = dict(usage.get("output_contract") or {})
    initial_code = str(oc.get("initial_contract_failure_code") or "")
    assert (
        "STRUCTURE_STAGE_SUMMARY_CITATION_EMPTY" in initial_code
        or "TURNING_POINT_CITATION_EMPTY" in initial_code
        or oc.get("repair_attempted")
    )
    counts = _orm_counts(env["session"])
    assert counts["assets"] >= 1
    assert counts["evidence"] >= 1


def test_structure_stages_v2_scenario_d_local_coverage_candidate_unconfirmed(product_env) -> None:
    env = product_env
    catalog = _build_ss_env_catalog(env)
    cids = list(catalog.citation_ids[:4])
    stub = _load_fixture_content(
        "structure_stages_v2_http_local_coverage.json", citation_ids=cids
    )
    _configure_fake_http(
        env,
        stub_texts=[stub],
        request_ids=["fake-http-ss-v2-local-1"],
    )

    _pre, _est, create, exec_result = _create_and_start_ss(
        env, idem="ss-v2-d", local_only=True
    )
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}

    result_resp = env["client"].get(
        f"/api/v1/whole-book-runs/{run_id}/results/structure_stages?view=candidate"
    )
    assert result_resp.status_code == 200, result_resp.text
    body = result_resp.json()
    assert str(body.get("module_status") or "").lower() == "completed"
    review = dict(body.get("review_summary") or {})
    assert int(review.get("candidate_count") or 0) >= 1
    assert int(review.get("confirmed_count") or 0) == 0

    session: Session = env["session"]
    versions = list(session.scalars(select(NarrativeAssetVersion)).all())
    assert versions
    assert all(str(v.review_status) == "candidate" for v in versions)
    assert all(v.is_canonical is not True for v in versions)

    payload = dict(body.get("payload") or {})
    assert payload.get("coverage_scope") == "local"
    _assert_no_sensitive(result_resp.text)


def test_structure_stages_v2_scenario_e_context_fingerprint_mismatch(product_env) -> None:
    from app.narrative_core.services.private_lab_run_metadata import (
        parse_metadata_json,
        serialize_metadata,
    )

    env = product_env
    catalog = _build_ss_env_catalog(env)
    cids = list(catalog.citation_ids[:4])
    stub = _load_fixture_content("structure_stages_v2_http_valid.json", citation_ids=cids)
    _configure_fake_http(
        env,
        stub_texts=[stub],
        request_ids=["fake-http-ss-v2-mismatch-should-not-run"],
    )

    client = env["client"]
    pre, est, create = _http_flow(
        client, env, idem="ss-v2-e", dry_run=False, auto_start=False, modules=SS_MODULES
    )
    assert create.status_code == 200, create.text
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))

    session: Session = env["session"]
    run = session.get(AnalysisRun, run_id)
    assert run is not None
    meta = parse_metadata_json(run.validated_output)
    binding = dict(meta.get("execution_context_binding") or {})
    assert binding
    binding["context_bundle_hash"] = "deadbeef" + ("0" * 56)
    binding["estimate_context_hash"] = binding["context_bundle_hash"]
    meta["execution_context_binding"] = binding
    run.validated_output = serialize_metadata(meta)
    session.commit()

    exec_result = env["executor"].start(run_id)
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) == 0

    blob = json.dumps(
        {
            "status": exec_result.status,
            "detail": getattr(exec_result, "detail", None),
        },
        ensure_ascii=False,
        default=str,
    )
    assert "EXECUTION_CONTEXT_FINGERPRINT_MISMATCH" in blob or "FINGERPRINT_MISMATCH" in blob
    counts = _orm_counts(session)
    assert counts["assets"] == 0
    assert counts["evidence"] == 0


def test_structure_stages_v2_scenario_f_repair_still_fails(product_env) -> None:
    env = product_env
    catalog = _build_ss_env_catalog(env)
    cids = list(catalog.citation_ids[:4])
    bad = _load_fixture_content(
        "structure_stages_v2_http_missing_summary_citation.json", citation_ids=cids
    )
    still_bad = _load_fixture_content(
        "structure_stages_v2_http_repair_invalid.json", citation_ids=cids
    )
    _configure_fake_http(
        env,
        stub_texts=[bad, still_bad],
        request_ids=["fake-http-ss-v2-repair-bad-1", "fake-http-ss-v2-repair-bad-2"],
    )

    _pre, _est, create, exec_result = _create_and_start_ss(env, idem="ss-v2-f")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) == 2

    counts = _orm_counts(env["session"])
    assert counts["assets"] == 0
    assert counts["evidence"] == 0
    assert counts["versions"] == 0

    result_resp = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results")
    _assert_ss_fail_closed(env["session"], run_id, result_resp.json())


def test_structure_stages_v2_scenario_g_overlap_fail_closed(product_env) -> None:
    env = product_env
    catalog = _build_ss_env_catalog(env)
    cids = list(catalog.citation_ids[:4])
    overlap = _load_fixture_content("structure_stages_v2_http_overlap.json", citation_ids=cids)
    _configure_fake_http(
        env,
        stub_texts=[overlap, overlap],
        request_ids=["fake-http-ss-v2-overlap-1", "fake-http-ss-v2-overlap-2"],
    )

    _pre, _est, create, exec_result = _create_and_start_ss(env, idem="ss-v2-g")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"
    assert len(env["fake_http"].calls) <= 2
    assert len(env["fake_http"].calls) >= 1

    usage = _module_result_usage(env, run_id)
    detail = json.dumps(usage, ensure_ascii=False, default=str)
    diags = _pipeline_diags(env, run_id)
    diag_blob = json.dumps(diags, ensure_ascii=False, default=str)
    cp = _provider_attempt_payload(env["session"], run_id)
    cp_blob = json.dumps(cp, ensure_ascii=False, default=str)
    oc = dict((usage.get("output_contract") or cp.get("output_contract") or {}))
    initial_code = str(oc.get("initial_contract_failure_code") or "")
    assert (
        FAILURE_STAGE_RANGE_OVERLAP in detail
        or FAILURE_STAGE_RANGE_OVERLAP in diag_blob
        or FAILURE_STAGE_RANGE_OVERLAP in cp_blob
        or FAILURE_STAGE_RANGE_OVERLAP in initial_code
        or "STRUCTURE_STAGE_RANGE_OVERLAP" in detail
        or "STRUCTURE_STAGE_RANGE_OVERLAP" in diag_blob
        or "STRUCTURE_STAGE_RANGE_OVERLAP" in cp_blob
        or "STRUCTURE_STAGE_RANGE_OVERLAP" in initial_code
    )

    counts = _orm_counts(env["session"])
    assert counts["assets"] == 0
    assert counts["evidence"] == 0
    result_resp = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results")
    _assert_ss_fail_closed(env["session"], run_id, result_resp.json())


def test_structure_stages_v2_scenario_h_unknown_stale_no_quote_fallback(product_env) -> None:
    env = product_env
    _build_ss_env_catalog(env)
    unknown = _load_fixture_content("structure_stages_v2_http_unknown_citation.json")
    stale = _load_fixture_content("structure_stages_v2_http_stale_bundle_citation.json")
    for fixture, idem_suffix in (
        (unknown, "unknown"),
        (stale, "stale"),
    ):
        _configure_fake_http(
            env,
            stub_texts=[fixture, fixture],
            request_ids=[f"fake-http-ss-v2-{idem_suffix}-1", f"fake-http-ss-v2-{idem_suffix}-2"],
        )
        _pre, _est, create, exec_result = _create_and_start_ss(
            env, idem=f"ss-v2-h-{idem_suffix}"
        )
        run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
        assert exec_result.status.lower() == "failed"
        diags = _pipeline_diags(env, run_id)
        q_ok, _ = _quote_fallback_counts(diags)
        assert q_ok == 0
        counts = _orm_counts(env["session"])
        assert counts["assets"] == 0
        assert counts["evidence"] == 0


def test_structure_stages_v2_scenario_i_turning_points_in_result_api(product_env) -> None:
    env = product_env
    catalog = _build_ss_env_catalog(env)
    cids = list(catalog.citation_ids[:4])
    stub = _load_fixture_content(
        "structure_stages_v2_http_with_turning_points.json", citation_ids=cids
    )
    _configure_fake_http(
        env,
        stub_texts=[stub],
        request_ids=["fake-http-ss-v2-with-tp-1"],
    )

    _pre, _est, create, exec_result = _create_and_start_ss(env, idem="ss-v2-i")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() in {"completed", "complete"}

    result_resp = env["client"].get(
        f"/api/v1/whole-book-runs/{run_id}/results/structure_stages"
    )
    assert result_resp.status_code == 200, result_resp.text
    body = result_resp.json()
    payload = dict(body.get("payload") or {})
    turning_points = list(payload.get("turning_points") or ())
    turning_points_v2 = list(payload.get("turning_points_v2") or ())
    assert turning_points or turning_points_v2
    combined = turning_points or turning_points_v2
    assert len(combined) >= 1
    first = combined[0]
    assert isinstance(first, dict)
    desc = first.get("description")
    summary = first.get("summary")
    if isinstance(desc, dict):
        text = desc.get("value")
    elif isinstance(summary, str):
        text = summary
    else:
        text = first.get("label")
    assert str(text or "")


def test_structure_stages_v2_scenario_j_persistence_failure_rollback(
    product_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = product_env
    catalog = _build_ss_env_catalog(env)
    cids = list(catalog.citation_ids[:4])
    stub = _load_fixture_content("structure_stages_v2_http_valid.json", citation_ids=cids)
    _configure_fake_http(
        env,
        stub_texts=[stub],
        request_ids=["fake-http-ss-v2-persist-fail-1"],
    )

    def _boom(_self: Phase1BCandidatePersistenceSink, _built: Any) -> dict[str, Any]:
        raise RuntimeError("INJECTED_PERSIST_FAILURE")

    monkeypatch.setattr(Phase1BCandidatePersistenceSink, "persist_commands", _boom)

    _pre, _est, create, exec_result = _create_and_start_ss(env, idem="ss-v2-j")
    run_id = int(create.json().get("run_id") or create.json().get("lab_run_id"))
    assert exec_result.status.lower() == "failed"

    counts = _orm_counts(env["session"])
    assert counts["assets"] == 0
    assert counts["versions"] == 0
    assert counts["evidence"] == 0
    assert counts["artifacts"] == 0

    diags = _pipeline_diags(env, run_id)
    if diags:
        assert diags.get("transaction_committed") is not True
        assert diags.get("persistence_complete") is not True
        assert (
            diags.get("transaction_rolled_back") is True
            or diags.get("failure_boundary") == "ORM_TRANSACTION_ROLLBACK"
        )

    result_resp = env["client"].get(f"/api/v1/whole-book-runs/{run_id}/results")
    _assert_ss_fail_closed(env["session"], run_id, result_resp.json())


def test_offline_ss_v2_mapper_accepts_valid_fixture(product_env) -> None:
    env = product_env
    catalog = _build_ss_env_catalog(env)
    cids = list(catalog.citation_ids[:4])
    payload = json.loads(
        _load_fixture_content("structure_stages_v2_http_valid.json", citation_ids=cids)
    )
    from app.narrative_core.services.structure_stages_result_mapper_v2 import (
        map_structure_stages_result_v2,
    )

    caps = _default_ss_context_capabilities()
    mapped = map_structure_stages_result_v2(
        payload, catalog=catalog, capabilities=caps
    )
    assert mapped.status == "mapped", mapped.failure_code
    assert len(mapped.asset_candidates) >= 1
    assert len(mapped.evidence_refs) >= 1


def test_offline_ss_v2_executor_catalog_map(product_env) -> None:
    """Catalog + payload must match Formal executor rebuild (not stale test hash)."""

    env = product_env
    _build_ss_env_catalog(env)
    _ensure_four_paragraph_snapshot(env)
    from app.narrative_core.services.citation_catalog_v2 import build_catalog_from_paragraph_units
    from app.narrative_core.services.formal_private_provider_input_resolver import (
        FormalPrivateProviderInputBundleResolverAdapter,
    )
    from app.narrative_core.services.structure_stages_result_mapper_v2 import (
        map_structure_stages_result_v2,
    )

    formal = FormalPrivateProviderInputBundleResolverAdapter(
        session=env["session"],
        provider_context_limit=120_000,
    )
    binding = dict(env.get("execution_context_binding") or {})
    bundle = formal.resolve(
        request_id=f"exec-bind-test-{env['book'].id}",
        book_id=int(env["book"].id),
        book_snapshot_id=int(env["snapshot"].id),
        module_key="structure_stages",
        context_bundle_hash=str(binding.get("context_bundle_hash") or ""),
        provider_key="dashscope",
        model_id="qwen-plus",
        quality_profile="balanced",
    )
    contract = formal.last_contract()
    assert contract is not None
    analysis_rt = env["runtime"].runtime_factory(
        session=env["session"],
        book_id=env["book"].id,
        use_phase1b_persistence=True,
        dry_run=False,
    )
    units = analysis_rt._paragraph_units_for_citation_catalog(  # noqa: SLF001
        contract=contract,
        book_snapshot_id=int(env["snapshot"].id),
        selected_paragraph_ids=tuple(
            int(x) for x in (binding.get("selected_paragraph_ids") or ())
        )
        or None,
    )
    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash=str(bundle.context_bundle_hash),
        snapshot_id=int(env["snapshot"].id),
        paragraph_units=units,
    )
    cids = list(catalog.citation_ids[:4])
    payload = json.loads(
        _load_fixture_content("structure_stages_v2_http_valid.json", citation_ids=cids)
    )
    caps = _default_ss_context_capabilities()
    mapped = map_structure_stages_result_v2(
        payload, catalog=catalog, capabilities=caps
    )
    assert mapped.status == "mapped", mapped.failure_code


def test_book_overview_http_replay_is_separate_module() -> None:
    """Regression guard: book_overview FakeHttp replay lives in citation_v2 file."""

    sibling = Path(__file__).with_name("test_narrative_phase2br1_citation_v2_http_replay.py")
    assert sibling.is_file()
    text = sibling.read_text(encoding="utf-8")
    assert "book_overview_v2_http_valid.json" in text
    assert "structure_stages_v2_http_valid.json" not in text


_ = (product_env, MARKER)
