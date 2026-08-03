"""Canonical product/Lab adapter for ChapterFunctionsResultV2 (WB-2.2).

Product GET /chapter-functions and Lab GET .../results/chapter_functions resolve
via this module — Lab adapts V1 items from V2 (no duplicated recognition).
"""

from __future__ import annotations

import base64
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisConflict, WholeBookCheckpoint
from app.narrative_core.services.chapter_functions_result_mapper_v2 import (
    lab_v1_items_from_chapter_functions_v2,
)
from app.narrative_core.services.whole_book_minimal_chapter_functions_v1_service import (
    CHAPTER_FUNCTIONS_RESULT_CHECKPOINT_KEY,
    CHAPTER_FUNCTIONS_STAGE_CODE,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200


def load_chapter_functions_checkpoint_envelope(
    session: Session, run_id: int
) -> dict[str, Any] | None:
    row = session.scalar(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == run_id,
            WholeBookCheckpoint.stage_code == CHAPTER_FUNCTIONS_STAGE_CODE,
            WholeBookCheckpoint.checkpoint_key == CHAPTER_FUNCTIONS_RESULT_CHECKPOINT_KEY,
        )
    )
    if row is None:
        return None
    try:
        data = json.loads(row.checkpoint_payload_json or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _encode_cursor(chapter_order: int) -> str:
    raw = json.dumps({"chapter_order": int(chapter_order)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str | None) -> int | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        return int(data.get("chapter_order"))
    except Exception:  # noqa: BLE001
        return None


def _filter_chapters(
    chapters: list[dict[str, Any]],
    *,
    function: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    out = list(chapters)
    if function:
        needle = str(function).strip().lower().replace("-", "_")
        filtered = []
        for ch in out:
            primary = str(ch.get("primary_function") or "").lower()
            secondary = [str(x).lower() for x in (ch.get("secondary_functions") or [])]
            if primary == needle or needle in secondary:
                filtered.append(ch)
        out = filtered
    if status:
        st = str(status).strip().lower()
        filtered = []
        for ch in out:
            summary = ch.get("observed_summary") if isinstance(ch.get("observed_summary"), dict) else {}
            if str(summary.get("status") or "").lower() == st:
                filtered.append(ch)
        out = filtered
    return out


def _paginate(
    chapters: list[dict[str, Any]],
    *,
    limit: int,
    cursor: str | None,
    offset: int | None,
) -> tuple[list[dict[str, Any]], str | None]:
    ordered = sorted(chapters, key=lambda c: int(c.get("chapter_order") or 0))
    start = 0
    if cursor:
        after = _decode_cursor(cursor)
        if after is not None:
            start = next(
                (i for i, c in enumerate(ordered) if int(c.get("chapter_order") or 0) > after),
                len(ordered),
            )
    elif offset is not None and offset > 0:
        start = int(offset)
    page = ordered[start : start + limit]
    next_cursor = None
    if start + limit < len(ordered) and page:
        next_cursor = _encode_cursor(int(page[-1].get("chapter_order") or 0))
    return page, next_cursor


def get_run_chapter_functions_product_v1(
    session: Session,
    run_id: int,
    *,
    limit: int = DEFAULT_PAGE_LIMIT,
    cursor: str | None = None,
    offset: int | None = None,
    function: str | None = None,
    status: str | None = None,
    chapter_id: str | int | None = None,
) -> dict[str, Any] | None:
    """Product envelope for GET /api/v1/whole-book/runs/{run_id}/chapter-functions."""

    try:
        run = get_run(session, run_id)
    except Exception:  # noqa: BLE001
        return None

    if run.status == "cancelled":
        return {
            "result_status": "canceled",
            "contract_version": "v2",
            "coverage_scope": None,
            "chapter_functions": None,
            "items": [],
            "next_cursor": None,
            "total_chapters": 0,
            "failure_code": None,
            "source_revision": {
                "run_id": run.id,
                "snapshot_id": run.snapshot_id,
                "book_id": run.book_id,
            },
            "evidence_references": [],
            "fixture_test_data": True,
        }

    envelope = load_chapter_functions_checkpoint_envelope(session, run_id)
    if envelope is None:
        if run.status == "failed" and str(run.failure_code or "").startswith("CHAPTER_FN_"):
            return {
                "result_status": "failed",
                "contract_version": "v2",
                "coverage_scope": None,
                "chapter_functions": None,
                "items": [],
                "next_cursor": None,
                "total_chapters": 0,
                "failure_code": run.failure_code,
                "source_revision": {
                    "run_id": run.id,
                    "snapshot_id": run.snapshot_id,
                    "book_id": run.book_id,
                },
                "evidence_references": [],
            }
        return None

    cf = envelope.get("chapter_functions")
    if cf is not None and not isinstance(cf, dict):
        return {
            "result_status": "failed",
            "contract_version": "v2",
            "coverage_scope": None,
            "chapter_functions": None,
            "items": [],
            "next_cursor": None,
            "total_chapters": 0,
            "failure_code": "CHAPTER_FN_UNSUPPORTED_VERSION",
            "source_revision": envelope.get("source_revision")
            or {
                "run_id": run.id,
                "snapshot_id": run.snapshot_id,
                "book_id": run.book_id,
            },
            "evidence_references": [],
        }

    contract_ver = str(
        (cf or {}).get("contract_version") or envelope.get("contract_version") or ""
    ).lower()
    if cf is not None and contract_ver and contract_ver not in {"v2", "2.0.0"}:
        return {
            "result_status": "failed",
            "contract_version": contract_ver,
            "coverage_scope": None,
            "chapter_functions": None,
            "items": [],
            "next_cursor": None,
            "total_chapters": 0,
            "failure_code": "CHAPTER_FN_UNSUPPORTED_VERSION",
            "source_revision": envelope.get("source_revision"),
            "evidence_references": [],
        }

    result_status = str(envelope.get("result_status") or "completed")
    product_status = str(envelope.get("product_result_status") or result_status)
    if product_status == "insufficient":
        result_status = "completed"
    if product_status == "conflict":
        result_status = "conflict"
    if result_status == "failed":
        return {
            "result_status": "failed",
            "contract_version": envelope.get("contract_version") or "v2",
            "coverage_scope": envelope.get("coverage_scope"),
            "chapter_functions": cf,
            "items": [],
            "next_cursor": None,
            "total_chapters": 0,
            "failure_code": envelope.get("failure_code"),
            "source_revision": envelope.get("source_revision")
            or {
                "run_id": run.id,
                "snapshot_id": run.snapshot_id,
                "book_id": run.book_id,
            },
            "evidence_references": list(envelope.get("evidence_references") or []),
            "fixture_test_data": bool(envelope.get("fixture_test_data")),
        }

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
            if meta.get("whole_book_run_id") == run_id and meta.get("chapter_id") is not None:
                result_status = "conflict"
                break

    chapters = list((cf or {}).get("chapters") or []) if isinstance(cf, dict) else []
    if chapter_id is not None:
        target = str(chapter_id)
        chapters = [c for c in chapters if str(c.get("chapter_id")) == target]
        if not chapters:
            return None  # single-chapter 404 (not module absent)
    chapters = _filter_chapters(chapters, function=function, status=status)
    total = len(chapters)
    page_limit = max(1, min(int(limit or DEFAULT_PAGE_LIMIT), MAX_PAGE_LIMIT))
    items, next_cursor = _paginate(
        chapters, limit=page_limit, cursor=cursor, offset=offset
    )

    return {
        "result_status": result_status,
        "contract_version": envelope.get("contract_version") or "v2",
        "schema_version": envelope.get("schema_version") or "2.0.0",
        "coverage_scope": envelope.get("coverage_scope")
        or (cf or {}).get("coverage_scope")
        if isinstance(cf, dict)
        else envelope.get("coverage_scope"),
        "chapter_functions": cf,
        "items": items,
        "next_cursor": next_cursor,
        "total_chapters": total,
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
        "batch_count": envelope.get("batch_count"),
        "max_chapters_per_batch": envelope.get("max_chapters_per_batch"),
    }


def get_lab_chapter_functions_v1_from_v2(session: Session, run_id: int) -> dict[str, Any] | None:
    """Lab adapter payload: items derived from canonical V2."""

    product = get_run_chapter_functions_product_v1(
        session, run_id, limit=MAX_PAGE_LIMIT, cursor=None
    )
    if product is None:
        return None
    cf = product.get("chapter_functions")
    if not isinstance(cf, dict):
        return None
    return {
        "items": lab_v1_items_from_chapter_functions_v2(cf),
        "contract_version": "v1",
        "adapted_from": "ChapterFunctionsResultV2",
        "coverage_scope": cf.get("coverage_scope"),
        "result_status": product.get("result_status"),
    }
