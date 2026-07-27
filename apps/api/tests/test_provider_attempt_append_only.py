"""CHG-058 — provider_attempts must be append-only across stage checkpoints."""

from __future__ import annotations

from app.narrative_core.services.run_stage_repository import merge_checkpoint_namespaces


def test_pipeline_diagnostics_does_not_replace_provider_attempts():
    base = {
        "provider_attempts": [
            {"attempt_index": 0, "attempt_kind": "initial", "http_status": 200},
        ],
        "pipeline_diagnostics": {"phase": "early"},
    }
    merged = merge_checkpoint_namespaces(
        base,
        {
            "pipeline_diagnostics": {"phase": "late", "catalog_entry_count": 3},
            "persistence_summary": {"transaction_committed": True},
        },
    )
    assert len(merged["provider_attempts"]) == 1
    assert merged["provider_attempts"][0]["attempt_kind"] == "initial"
    assert merged["pipeline_diagnostics"]["phase"] == "late"
    assert merged["persistence_summary"]["transaction_committed"] is True


def test_repair_attempt_appends_second_record():
    base = {"provider_attempts": [{"attempt_index": 0, "attempt_kind": "initial"}]}
    merged = merge_checkpoint_namespaces(
        base,
        {},
        append_provider_attempt={
            "attempt_index": 1,
            "attempt_kind": "repair",
            "http_status": 200,
        },
    )
    assert len(merged["provider_attempts"]) == 2
    assert merged["provider_attempts"][1]["attempt_kind"] == "repair"
