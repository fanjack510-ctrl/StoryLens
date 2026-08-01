"""Canonical product/Lab adapter for StructureStagesResultV2 (WB-2.1).

Both product GET /structure and Lab GET .../results/structure_stages should
resolve V2 via this module — no duplicated recognition logic.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisConflict, WholeBookCheckpoint, WholeBookRun
from app.narrative_core.services.whole_book_minimal_structure_stages_v1_service import (
    STRUCTURE_RESULT_CHECKPOINT_KEY,
    STRUCTURE_STAGE_CODE,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run


def load_structure_checkpoint_envelope(session: Session, run_id: int) -> dict[str, Any] | None:
    row = session.scalar(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == run_id,
            WholeBookCheckpoint.stage_code == STRUCTURE_STAGE_CODE,
            WholeBookCheckpoint.checkpoint_key == STRUCTURE_RESULT_CHECKPOINT_KEY,
        )
    )
    if row is None:
        return None
    try:
        data = json.loads(row.checkpoint_payload_json or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _lab_v2_from_result_index(session: Session, run_id: int) -> dict[str, Any] | None:
    """Fallback: Lab projection artifact path (same V2 fields)."""

    try:
        from app.narrative_core.services.whole_book_result_projection import (
            WholeBookResultIndexService,
        )

        svc = WholeBookResultIndexService(session)
        result = svc.get_module_result(run_id, "structure_stages")
        if not isinstance(result, dict):
            return None
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else result
        stages_v2 = payload.get("stages_v2")
        if not isinstance(stages_v2, list) and str(payload.get("contract_version") or "") != "v2":
            return None
        structure = {
            "contract_version": "v2",
            "evidence_contract_version": payload.get("evidence_contract_version") or "v2",
            "coverage_scope": payload.get("coverage_scope"),
            "stages": list(stages_v2 or payload.get("stages") or []),
            "turning_points": list(
                payload.get("turning_points_v2") or payload.get("turning_points") or []
            ),
            "analysis_confidence": payload.get("confidence") or payload.get("analysis_confidence"),
            "overall_confidence": payload.get("overall_confidence") or payload.get("confidence"),
            "limitations": list(payload.get("limitations") or ()),
            "context_capabilities": payload.get("context_capabilities"),
        }
        return {
            "result_status": "completed",
            "contract_version": "v2",
            "coverage_scope": structure.get("coverage_scope"),
            "structure": structure,
            "source": "lab_result_index",
        }
    except Exception:  # noqa: BLE001
        return None


def get_run_structure_product_v1(session: Session, run_id: int) -> dict[str, Any] | None:
    """Product envelope for GET /api/v1/whole-book/runs/{run_id}/structure."""

    try:
        run = get_run(session, run_id)
    except Exception:  # noqa: BLE001
        return None

    if run.status == "cancelled":
        return {
            "result_status": "canceled",
            "contract_version": "v2",
            "coverage_scope": None,
            "structure": None,
            "failure_code": None,
            "source_revision": {
                "run_id": run.id,
                "snapshot_id": run.snapshot_id,
                "book_id": run.book_id,
            },
            "evidence_references": [],
            "fixture_test_data": True,
        }

    envelope = load_structure_checkpoint_envelope(session, run_id)
    if envelope is None:
        envelope = _lab_v2_from_result_index(session, run_id)
    if envelope is None:
        if run.status == "failed" and (run.failure_code or "").startswith("STRUCTURE_"):
            return {
                "result_status": "failed",
                "contract_version": "v2",
                "coverage_scope": None,
                "structure": None,
                "failure_code": run.failure_code,
                "source_revision": {
                    "run_id": run.id,
                    "snapshot_id": run.snapshot_id,
                    "book_id": run.book_id,
                },
                "evidence_references": [],
            }
        return None

    structure = envelope.get("structure")
    result_status = str(envelope.get("result_status") or "completed")
    product_status = str(envelope.get("product_result_status") or result_status)
    if product_status == "insufficient":
        # Freeze: legal insufficient is completed for Free UX, with coverage_scope.
        result_status = "completed"
    if product_status == "conflict":
        result_status = "conflict"

    # Detect open conflicts for structure assets of this run.
    if result_status == "completed":
        open_conflicts = session.scalars(
            select(AnalysisConflict).where(
                AnalysisConflict.book_id == run.book_id,
                AnalysisConflict.status == "open",
                AnalysisConflict.conflict_type == "locked_asset_vs_new_run",
            )
        ).all()
        for conflict in open_conflicts:
            try:
                meta = json.loads(conflict.resolution_json or "{}")
            except json.JSONDecodeError:
                meta = {}
            if meta.get("whole_book_run_id") == run_id:
                result_status = "conflict"
                break

    return {
        "result_status": result_status,
        "contract_version": envelope.get("contract_version") or "v2",
        "schema_version": envelope.get("schema_version") or "2.0.0",
        "coverage_scope": envelope.get("coverage_scope")
        or (structure or {}).get("coverage_scope")
        if isinstance(structure, dict)
        else envelope.get("coverage_scope"),
        "structure": structure,
        "failure_code": envelope.get("failure_code"),
        "source_revision": envelope.get("source_revision")
        or {
            "run_id": run.id,
            "snapshot_id": run.snapshot_id,
            "book_id": run.book_id,
        },
        "evidence_references": list(envelope.get("evidence_references") or []),
        "fixture_test_data": bool(envelope.get("fixture_test_data")),
        "persist": envelope.get("persist"),
    }


def get_lab_structure_stages_canonical_v2(session: Session, run_id: int) -> dict[str, Any] | None:
    """Shared V2 payload for Lab results/structure_stages adapter."""

    product = get_run_structure_product_v1(session, run_id)
    if product is None:
        return None
    structure = product.get("structure")
    if not isinstance(structure, dict):
        return None
    return dict(structure)
