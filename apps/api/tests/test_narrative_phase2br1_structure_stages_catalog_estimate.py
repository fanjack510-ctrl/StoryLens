"""CHG-20260725-001: Structure Stages Estimate Catalog materialization + consistency.

Provider-free. No real network. No Create / ORM business writes.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    AnalysisRunStage,
    NarrativeAsset,
    NarrativeAssetVersion,
)

# Reuse CHG-057 product harness fixture via pytest_plugins-style import.
pytest_plugins: list[str] = []

from tests.test_narrative_phase2br1_chg057_acceptance_closure import (  # noqa: E402
    product_env,
)


def _business_counts(session: Any) -> dict[str, int]:
    return {
        "analysis_runs": len(session.scalars(select(AnalysisRun)).all()),
        "analysis_run_stages": len(session.scalars(select(AnalysisRunStage)).all()),
        "narrative_assets": len(session.scalars(select(NarrativeAsset)).all()),
        "narrative_asset_versions": len(
            session.scalars(select(NarrativeAssetVersion)).all()
        ),
        "analysis_evidence": len(session.scalars(select(AnalysisEvidence)).all()),
        "analysis_artifacts": len(session.scalars(select(AnalysisArtifact)).all()),
    }


@pytest.fixture
def structure_env(product_env: dict[str, Any]) -> dict[str, Any]:
    return product_env


def test_structure_estimate_materializes_nonempty_catalog(
    structure_env: dict[str, Any],
) -> None:
    from app.narrative_core.services.structure_stages_materialization_preview import (
        run_structure_stages_provider_free_materialization_preview,
    )

    session = structure_env["session"]
    before = _business_counts(session)
    preview = run_structure_stages_provider_free_materialization_preview(
        session=session,
        book_id=int(structure_env["book"].id),
        book_snapshot_id=int(structure_env["snapshot"].id),
        configuration_fingerprint="test-ss-catalog-materialization",
    )
    after = _business_counts(session)

    assert preview.preflight_ok is True
    assert preview.resolver_is_fake is False
    assert preview.provider_http_count == 0
    assert preview.catalog_entry_count > 0
    assert preview.citation_enum_count == preview.catalog_entry_count
    assert preview.cited_sources_block_count == preview.catalog_entry_count
    assert preview.fingerprints_match is True
    assert (
        preview.catalog_fingerprint
        == preview.prompt_catalog_fingerprint
        == preview.schema_catalog_fingerprint
        == preview.resolver_catalog_fingerprint
    )
    assert preview.dynamic_schema_fingerprint
    assert preview.selection_fingerprint
    assert preview.context_bundle_hash
    assert preview.prompt_input_fingerprint
    assert preview.max_repair_count == 1
    assert preview.selected_paragraph_count > 0
    assert preview.selected_chapter_count > 0
    assert after == before


def test_structure_estimate_binding_catalog_count_projected(
    structure_env: dict[str, Any],
) -> None:
    from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
        create_live_readiness_runtime,
    )

    session = structure_env["session"]
    runtime = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        dry_run=True,
        session=session,
        allow_fake_resolver=False,
        auto_wire_credentials=True,
    )
    runtime.bind_session(session)
    assert runtime.preflight is not None and runtime.estimate is not None
    pre = runtime.preflight.preflight(
        book_id=int(structure_env["book"].id),
        book_snapshot_id=int(structure_env["snapshot"].id),
        configuration_fingerprint="test-ss-est-binding",
        requested_modules=("structure_stages",),
    )
    assert pre.ok
    est = runtime.estimate.estimate(
        book_id=int(structure_env["book"].id),
        book_snapshot_id=int(structure_env["snapshot"].id),
        configuration_fingerprint="test-ss-est-binding",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
        requested_modules=("structure_stages",),
        preflight_fingerprint=pre.fingerprint,
    )
    binding = runtime.estimate.cached_execution_context_binding(est.fingerprint)
    mat = runtime.estimate.cached_catalog_materialization(est.fingerprint)
    assert binding is not None
    assert int(binding.get("citation_entry_count") or 0) > 0
    assert str(binding.get("citation_catalog_fingerprint") or "")
    assert str(binding.get("dynamic_schema_fingerprint") or "")
    assert mat is not None
    assert int(mat["catalog_entry_count"]) == int(binding["citation_entry_count"])
    assert mat["catalog_fingerprint"] == binding["citation_catalog_fingerprint"]
    assert (
        mat["catalog_fingerprint"]
        == mat["prompt_catalog_fingerprint"]
        == mat["schema_catalog_fingerprint"]
        == mat["resolver_catalog_fingerprint"]
    )


def test_structure_estimate_executor_catalog_fingerprints_match(
    structure_env: dict[str, Any],
) -> None:
    """Estimate catalog fingerprint must match Executor deterministic rebuild."""

    from app.narrative_core.services.citation_catalog_materialization import (
        materialize_structure_stages_estimate_catalog,
    )
    from app.narrative_core.services.execution_context_binding import (
        binding_from_safe_dict,
        compute_selection_fingerprint,
        verify_execution_context_fingerprints,
    )
    from app.narrative_core.services.formal_private_provider_input_resolver import (
        FormalPrivateProviderInputBundleResolverAdapter,
    )
    from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
        create_live_readiness_runtime,
    )

    session = structure_env["session"]
    runtime = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        dry_run=True,
        session=session,
        allow_fake_resolver=False,
        auto_wire_credentials=True,
    )
    runtime.bind_session(session)
    assert runtime.preflight is not None and runtime.estimate is not None
    book_id = int(structure_env["book"].id)
    snap_id = int(structure_env["snapshot"].id)
    pre = runtime.preflight.preflight(
        book_id=book_id,
        book_snapshot_id=snap_id,
        configuration_fingerprint="test-ss-est-exec-match",
        requested_modules=("structure_stages",),
    )
    est = runtime.estimate.estimate(
        book_id=book_id,
        book_snapshot_id=snap_id,
        configuration_fingerprint="test-ss-est-exec-match",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
        requested_modules=("structure_stages",),
        preflight_fingerprint=pre.fingerprint,
    )
    binding_raw = runtime.estimate.cached_execution_context_binding(est.fingerprint)
    assert binding_raw is not None
    expected = binding_from_safe_dict(binding_raw)
    assert expected.citation_entry_count > 0
    assert expected.citation_catalog_fingerprint

    formal = FormalPrivateProviderInputBundleResolverAdapter(
        session=session,
        provider_context_limit=int(expected.provider_context_limit or 120_000),
    )
    formal_bundle = formal.resolve(
        request_id="test-exec-rebuild",
        book_id=book_id,
        book_snapshot_id=snap_id,
        module_key="structure_stages",
        context_bundle_hash=expected.context_bundle_hash,
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
    )
    assert tuple(str(x) for x in formal_bundle.selected_paragraph_ids) == tuple(
        expected.selected_paragraph_ids
    )
    remat = materialize_structure_stages_estimate_catalog(
        session=session,
        contract=formal.last_contract(),
        book_snapshot_id=snap_id,
        context_bundle_hash=str(formal_bundle.context_bundle_hash),
        selected_paragraph_ids=formal_bundle.selected_paragraph_ids,
    )
    assert remat is not None
    assert remat.catalog_fingerprint == expected.citation_catalog_fingerprint
    assert remat.dynamic_schema_fingerprint == expected.dynamic_schema_fingerprint

    actual_selection_fp = compute_selection_fingerprint(
        selected_chapter_ids=formal_bundle.selected_chapter_ids,
        selected_paragraph_ids=formal_bundle.selected_paragraph_ids,
        selected_unit_refs=formal_bundle.selected_context_unit_ids,
        selection_policy_version=expected.selection_policy_version,
    )
    check = verify_execution_context_fingerprints(
        expected=expected,
        actual_selection_fingerprint=actual_selection_fp,
        actual_context_bundle_hash=str(formal_bundle.context_bundle_hash),
        actual_citation_catalog_fingerprint=remat.catalog_fingerprint,
        actual_prompt_input_fingerprint=str(formal_bundle.bundle_fingerprint),
        actual_dynamic_schema_fingerprint=remat.dynamic_schema_fingerprint,
        executor_selection_count=len(formal_bundle.selected_paragraph_ids),
        executor_catalog_count=remat.catalog_entry_count,
    )
    assert check.ok is True


def test_structure_selected_refs_tamper_fail_closed(
    structure_env: dict[str, Any],
) -> None:
    from app.narrative_core.services.execution_context_binding import (
        EXECUTION_CONTEXT_FINGERPRINT_MISMATCH,
        binding_from_safe_dict,
        compute_selection_fingerprint,
        verify_execution_context_fingerprints,
    )
    from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
        create_live_readiness_runtime,
    )

    session = structure_env["session"]
    runtime = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        dry_run=True,
        session=session,
        allow_fake_resolver=False,
        auto_wire_credentials=True,
    )
    runtime.bind_session(session)
    assert runtime.preflight is not None and runtime.estimate is not None
    pre = runtime.preflight.preflight(
        book_id=int(structure_env["book"].id),
        book_snapshot_id=int(structure_env["snapshot"].id),
        configuration_fingerprint="test-ss-tamper",
        requested_modules=("structure_stages",),
    )
    est = runtime.estimate.estimate(
        book_id=int(structure_env["book"].id),
        book_snapshot_id=int(structure_env["snapshot"].id),
        configuration_fingerprint="test-ss-tamper",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
        requested_modules=("structure_stages",),
        preflight_fingerprint=pre.fingerprint,
    )
    binding_raw = dict(runtime.estimate.cached_execution_context_binding(est.fingerprint) or {})
    expected = binding_from_safe_dict(binding_raw)
    # Tamper selected paragraph refs
    tampered_pids = tuple(list(expected.selected_paragraph_ids) + ["999999"])
    actual_fp = compute_selection_fingerprint(
        selected_chapter_ids=expected.selected_chapter_ids,
        selected_paragraph_ids=tampered_pids,
        selected_unit_refs=expected.selected_unit_refs,
        selection_policy_version=expected.selection_policy_version,
    )
    check = verify_execution_context_fingerprints(
        expected=expected,
        actual_selection_fingerprint=actual_fp,
        actual_context_bundle_hash=expected.context_bundle_hash,
        actual_citation_catalog_fingerprint=expected.citation_catalog_fingerprint,
        actual_prompt_input_fingerprint=expected.prompt_input_fingerprint,
        actual_dynamic_schema_fingerprint=expected.dynamic_schema_fingerprint,
        executor_selection_count=len(tampered_pids),
        executor_catalog_count=expected.citation_entry_count,
    )
    assert check.ok is False
    assert str(check.failure_code) == EXECUTION_CONTEXT_FINGERPRINT_MISMATCH


def test_structure_dynamic_schema_enum_equals_catalog_ids(
    structure_env: dict[str, Any],
) -> None:
    from app.narrative_core.services.citation_catalog_materialization import (
        _citation_enum_count,
        materialize_structure_stages_estimate_catalog,
    )
    from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
        create_live_readiness_runtime,
    )
    from app.narrative_core.services.structure_stages_output_contract_v2 import (
        structure_stages_result_v2_json_schema,
    )

    session = structure_env["session"]
    runtime = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        dry_run=True,
        session=session,
        allow_fake_resolver=False,
        auto_wire_credentials=True,
    )
    runtime.bind_session(session)
    assert runtime.preflight is not None and runtime.estimate is not None
    pre = runtime.preflight.preflight(
        book_id=int(structure_env["book"].id),
        book_snapshot_id=int(structure_env["snapshot"].id),
        configuration_fingerprint="test-ss-enum",
        requested_modules=("structure_stages",),
    )
    est = runtime.estimate.estimate(
        book_id=int(structure_env["book"].id),
        book_snapshot_id=int(structure_env["snapshot"].id),
        configuration_fingerprint="test-ss-enum",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
        requested_modules=("structure_stages",),
        preflight_fingerprint=pre.fingerprint,
    )
    binding = runtime.estimate.cached_execution_context_binding(est.fingerprint) or {}
    mat = materialize_structure_stages_estimate_catalog(
        session=session,
        contract=runtime.resolver.last_contract(),
        book_snapshot_id=int(structure_env["snapshot"].id),
        context_bundle_hash=str(binding.get("context_bundle_hash") or ""),
        selected_paragraph_ids=tuple(binding.get("selected_paragraph_ids") or ()),
    )
    assert mat is not None and mat.catalog is not None
    schema = structure_stages_result_v2_json_schema(catalog=mat.catalog)
    assert _citation_enum_count(schema) == mat.catalog_entry_count
    # No Create / no provider
    assert _business_counts(session)["analysis_runs"] == 0
