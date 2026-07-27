"""CHG-059 ExecutionContextBinding fingerprint checks."""

from __future__ import annotations

from app.narrative_core.services.execution_context_binding import (
    EXECUTION_CONTEXT_FINGERPRINT_MISMATCH,
    build_execution_context_binding,
    compute_selection_fingerprint,
    verify_execution_context_fingerprints,
)


def test_selection_fingerprint_detects_formal_vs_frozen_divergence() -> None:
    expected = build_execution_context_binding(
        book_id=1,
        snapshot_id=2,
        module_key="book_overview",
        selected_chapter_ids=("1", "2"),
        selected_paragraph_ids=("10", "11", "12"),
        selected_unit_refs=("u1", "u2"),
        context_bundle_hash="a" * 64,
        citation_catalog_fingerprint="b" * 64,
        prompt_input_fingerprint="c" * 64,
        dynamic_schema_fingerprint="d" * 64,
        source_character_count=7000,
        citation_entry_count=32,
    )
    actual_fp = compute_selection_fingerprint(
        selected_chapter_ids=("1", "2"),
        selected_paragraph_ids=("10", "11", "99"),  # diverged
        selected_unit_refs=("u1", "u2"),
        selection_policy_version=expected.selection_policy_version,
    )
    check = verify_execution_context_fingerprints(
        expected=expected,
        actual_selection_fingerprint=actual_fp,
        actual_context_bundle_hash=expected.context_bundle_hash,
        actual_citation_catalog_fingerprint=expected.citation_catalog_fingerprint,
        actual_prompt_input_fingerprint=expected.prompt_input_fingerprint,
        actual_dynamic_schema_fingerprint=expected.dynamic_schema_fingerprint,
        executor_selection_count=3,
        executor_catalog_count=32,
    )
    assert check.ok is False
    assert check.failure_code == EXECUTION_CONTEXT_FINGERPRINT_MISMATCH
    assert check.diagnostics["all_execution_context_fingerprints_match"] is False


def test_context_hash_mismatch_fails_before_provider() -> None:
    expected = build_execution_context_binding(
        book_id=1,
        snapshot_id=2,
        module_key="book_overview",
        selected_chapter_ids=("1",),
        selected_paragraph_ids=("10",),
        selected_unit_refs=("u1",),
        context_bundle_hash="a" * 64,
        source_character_count=100,
        citation_entry_count=1,
    )
    check = verify_execution_context_fingerprints(
        expected=expected,
        actual_selection_fingerprint=expected.selection_fingerprint,
        actual_context_bundle_hash="f" * 64,
        actual_citation_catalog_fingerprint="",
        actual_prompt_input_fingerprint="",
        actual_dynamic_schema_fingerprint="",
        executor_selection_count=1,
        executor_catalog_count=1,
    )
    assert check.ok is False
    assert check.failure_code == EXECUTION_CONTEXT_FINGERPRINT_MISMATCH
