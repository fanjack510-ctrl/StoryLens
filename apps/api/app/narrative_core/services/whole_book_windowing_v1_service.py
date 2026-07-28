"""Deterministic cross-chapter windowing v1 (WB-1.3) — no Provider calls."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    BookSnapshot,
    BookSnapshotParagraph,
    WholeBookCheckpoint,
    WholeBookRun,
    WholeBookRunStageRow,
    WholeBookWindow,
    utc_now,
)
from app.narrative_core.contracts.whole_book_contract_v1 import (
    WHOLE_BOOK_CONTRACT_VERSION,
    WholeBookStageStatus,
    WholeBookUnitStatus,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run
from app.narrative_core.services.whole_book_snapshot_v1_service import get_snapshot_paragraph_text
from app.services.whole_book_source_fingerprint import (
    canonical_json_bytes,
    estimate_paragraph_tokens_v1,
    sha256_utf8,
)

WINDOWING_VERSION = "whole_book_windowing_v1"
TARGET_INPUT_TOKENS = 18000
HARD_MAX_INPUT_TOKENS = 22000
OVERLAP_TARGET_TOKENS = 1440
FORWARD_OVERLAP = 0


def _load_paragraphs(session: Session, snapshot_id: int) -> list[BookSnapshotParagraph]:
    return list(
        session.scalars(
            select(BookSnapshotParagraph)
            .where(BookSnapshotParagraph.snapshot_id == snapshot_id)
            .options(selectinload(BookSnapshotParagraph.snapshot_chapter))
            .order_by(BookSnapshotParagraph.global_paragraph_index.asc())
        ).all()
    )


def _paragraph_tokens(session: Session, paragraph: BookSnapshotParagraph) -> int:
    text = get_snapshot_paragraph_text(session, paragraph.id)
    return estimate_paragraph_tokens_v1(text)


def whole_book_windowing_v1(
    session: Session,
    paragraphs: list[BookSnapshotParagraph],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Pure windowing algorithm — returns window specs + warnings."""
    warnings: list[str] = []
    if not paragraphs:
        return [], warnings

    items: list[tuple[int, BookSnapshotParagraph, int]] = []
    for para in sorted(paragraphs, key=lambda p: int(p.global_paragraph_index or 0)):
        gidx = int(para.global_paragraph_index or 0)
        items.append((gidx, para, _paragraph_tokens(session, para)))

    token_by_global = {g: tok for g, _p, tok in items}
    cores: list[tuple[int, int]] = []
    i = 0
    n = len(items)
    while i < n:
        start_i = i
        total = 0
        while i < n:
            gidx, _para, tok = items[i]
            if i == start_i and tok > TARGET_INPUT_TOKENS:
                if tok > HARD_MAX_INPUT_TOKENS:
                    warnings.append("oversized_paragraph_window")
                cores.append((gidx, gidx))
                i += 1
                break
            if total + tok > TARGET_INPUT_TOKENS and i > start_i:
                break
            total += tok
            i += 1
        else:
            cores.append((items[start_i][0], items[i - 1][0]))
            continue
        if i > start_i:
            cores.append((items[start_i][0], items[i - 1][0]))

    by_global = {int(p.global_paragraph_index or 0): p for p in paragraphs}
    windows: list[dict[str, Any]] = []
    for window_index, (core_start, core_end) in enumerate(cores):
        overlap_before = 0
        first_global = core_start
        if window_index > 0:
            _prev_start, prev_core_end = cores[window_index - 1]
            overlap_globals: list[int] = []
            overlap_tokens = 0
            for g in range(prev_core_end, cores[window_index - 1][0] - 1, -1):
                tok = token_by_global[g]
                if overlap_tokens + tok > OVERLAP_TARGET_TOKENS:
                    break
                core_tokens = sum(token_by_global[x] for x in range(core_start, core_end + 1))
                if overlap_tokens + tok + core_tokens > HARD_MAX_INPUT_TOKENS:
                    break
                overlap_globals.insert(0, g)
                overlap_tokens += tok
            if overlap_globals:
                overlap_before = len(overlap_globals)
                first_global = overlap_globals[0]

        para_rows = [
            by_global[g]
            for g in range(first_global, core_end + 1)
            if g in by_global
        ]
        token_estimate = sum(_paragraph_tokens(session, p) for p in para_rows)
        chapter_orders = [
            int(p.snapshot_chapter.chapter_order)
            for p in para_rows
            if p.snapshot_chapter is not None
        ]
        chapter_start = min(chapter_orders) if chapter_orders else 0
        chapter_end = max(chapter_orders) if chapter_orders else 0
        char_count = sum(len(get_snapshot_paragraph_text(session, p.id)) for p in para_rows)
        windows.append(
            {
                "window_index": window_index,
                "first_global_paragraph_index": first_global,
                "last_global_paragraph_index": core_end,
                "core_start_global_paragraph_index": core_start,
                "overlap_before_paragraphs": overlap_before,
                "overlap_after_paragraphs": FORWARD_OVERLAP,
                "paragraph_rows": para_rows,
                "paragraph_count": max(core_end - first_global + 1, 1),
                "character_count": max(char_count, 1),
                "token_estimate": token_estimate,
                "chapter_start_index": chapter_start,
                "chapter_end_index": chapter_end,
            }
        )
    return windows, warnings


def _window_hash(snapshot_id: int, window_index: int, para_rows: list[BookSnapshotParagraph]) -> str:
    payload = {
        "version": WINDOWING_VERSION,
        "snapshot_id": snapshot_id,
        "window_index": window_index,
        "paragraphs": [
            {
                "snapshot_paragraph_id": p.id,
                "global_paragraph_index": int(p.global_paragraph_index or 0),
                "text_hash": p.content_hash,
            }
            for p in para_rows
        ],
    }
    return sha256_utf8(canonical_json_bytes(payload).decode("utf-8"))


def _window_idempotency_key(
    *,
    snapshot_id: int,
    window_index: int,
    first_global: int,
    last_global: int,
    window_hash: str,
) -> str:
    payload = (
        f"{snapshot_id}|{WHOLE_BOOK_CONTRACT_VERSION}|{window_index}|"
        f"{first_global}|{last_global}|{window_hash}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def calculate_window_coverage_v1(
    session: Session,
    *,
    snapshot_id: int,
    run_id: int,
    windows: list[WholeBookWindow],
) -> dict[str, Any]:
    paragraphs = _load_paragraphs(session, snapshot_id)
    total = len(paragraphs)
    if total == 0:
        return {
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "total_paragraphs": 0,
            "covered_unique_paragraphs": 0,
            "duplicated_paragraphs": 0,
            "uncovered_paragraphs": 0,
            "coverage_ratio": 1.0,
            "order_valid": True,
            "first_global_paragraph_index": None,
            "last_global_paragraph_index": None,
        }

    covered: set[int] = set()
    duplicated = 0
    paragraph_sum = 0
    order_valid = True
    expected_index = 0
    for window in sorted(windows, key=lambda w: w.window_index):
        if window.window_index != expected_index:
            order_valid = False
        expected_index += 1
        for g in range(window.first_global_paragraph_index, window.last_global_paragraph_index + 1):
            if g in covered:
                duplicated += 1
            else:
                covered.add(g)
            paragraph_sum += 1

    unique = len(covered)
    uncovered = total - unique
    ratio = 1.0 if total == 0 else unique / total
    return {
        "snapshot_id": snapshot_id,
        "run_id": run_id,
        "total_paragraphs": total,
        "covered_unique_paragraphs": unique,
        "duplicated_paragraphs": paragraph_sum - unique,
        "uncovered_paragraphs": uncovered,
        "coverage_ratio": ratio,
        "order_valid": order_valid and uncovered == 0,
        "first_global_paragraph_index": min(covered) if covered else None,
        "last_global_paragraph_index": max(covered) if covered else None,
    }


def _window_set_hash(windows: list[WholeBookWindow]) -> str:
    payload = [
        {
            "window_index": w.window_index,
            "first_global_paragraph_index": w.first_global_paragraph_index,
            "last_global_paragraph_index": w.last_global_paragraph_index,
            "window_hash": w.window_hash,
        }
        for w in sorted(windows, key=lambda item: item.window_index)
    ]
    return sha256_utf8(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def window_to_dict(window: WholeBookWindow) -> dict[str, Any]:
    return {
        "window_id": window.id,
        "run_id": window.run_id,
        "snapshot_id": window.snapshot_id,
        "window_index": window.window_index,
        "first_global_paragraph_index": window.first_global_paragraph_index,
        "last_global_paragraph_index": window.last_global_paragraph_index,
        "chapter_start_index": window.chapter_start_index,
        "chapter_end_index": window.chapter_end_index,
        "paragraph_count": window.paragraph_count,
        "character_count": window.character_count,
        "token_estimate": window.token_estimate,
        "overlap_before_paragraphs": window.overlap_before_paragraphs,
        "overlap_after_paragraphs": window.overlap_after_paragraphs,
        "window_hash": window.window_hash,
        "idempotency_key": window.idempotency_key,
        "status": window.status,
    }


def list_windows(session: Session, run_id: int) -> list[WholeBookWindow]:
    get_run(session, run_id)
    return list(
        session.scalars(
            select(WholeBookWindow)
            .where(WholeBookWindow.run_id == run_id)
            .order_by(WholeBookWindow.window_index.asc())
        ).all()
    )


def list_checkpoints(session: Session, run_id: int) -> list[dict[str, Any]]:
    get_run(session, run_id)
    rows = session.scalars(
        select(WholeBookCheckpoint)
        .where(WholeBookCheckpoint.run_id == run_id)
        .order_by(WholeBookCheckpoint.sequence_no.asc())
    ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row.checkpoint_payload_json or "{}")
        out.append(
            {
                "checkpoint_id": row.id,
                "run_id": row.run_id,
                "stage_code": row.stage_code,
                "checkpoint_key": row.checkpoint_key,
                "sequence_no": row.sequence_no,
                "payload_hash": row.payload_hash,
                "checkpoint_payload": payload,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return out


def generate_whole_book_windows_v1(session: Session, run_id: int) -> dict[str, Any]:
    run = get_run(session, run_id)
    if run.snapshot_id is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"run {run_id} has no snapshot",
        )
    snapshot = session.get(BookSnapshot, run.snapshot_id)
    if snapshot is None or snapshot.snapshot_status != "completed":
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_COMPLETED,
            f"snapshot not completed for run {run_id}",
        )

    existing = list_windows(session, run_id)
    paragraphs = _load_paragraphs(session, snapshot.id)
    specs, warnings = whole_book_windowing_v1(session, paragraphs)
    computed_hashes: list[str] = []
    for spec in specs:
        computed_hashes.append(
            _window_hash(snapshot.id, spec["window_index"], spec["paragraph_rows"])
        )

    if existing:
        if len(existing) != len(specs):
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_WINDOW_SET_CONFLICT,
                "existing window count differs from recomputed set",
            )
        for row, spec, expected_hash in zip(
            sorted(existing, key=lambda w: w.window_index),
            specs,
            computed_hashes,
            strict=True,
        ):
            if row.window_hash != expected_hash:
                raise WholeBookFoundationError(
                    WholeBookFoundationErrorCode.WHOLE_BOOK_WINDOW_SET_CONFLICT,
                    f"window {row.window_index} hash mismatch",
                )
        coverage = calculate_window_coverage_v1(
            session, snapshot_id=snapshot.id, run_id=run_id, windows=existing
        )
        return {
            "run_id": run_id,
            "snapshot_id": snapshot.id,
            "reused": True,
            "windowing_version": WINDOWING_VERSION,
            "windows": [window_to_dict(w) for w in existing],
            "coverage": coverage,
            "warnings": warnings,
        }

    now = utc_now()
    stage = session.scalar(
        select(WholeBookRunStageRow).where(
            WholeBookRunStageRow.run_id == run_id,
            WholeBookRunStageRow.stage_code == "windowing",
        )
    )
    if stage is not None:
        stage.status = WholeBookStageStatus.running.value
        stage.started_at = stage.started_at or now
        stage.progress_total = max(stage.progress_total, len(specs) or 1)
        session.flush()

    created: list[WholeBookWindow] = []
    for spec in specs:
        para_rows = spec["paragraph_rows"]
        wh = _window_hash(snapshot.id, spec["window_index"], para_rows)
        idem = _window_idempotency_key(
            snapshot_id=snapshot.id,
            window_index=spec["window_index"],
            first_global=spec["first_global_paragraph_index"],
            last_global=spec["last_global_paragraph_index"],
            window_hash=wh,
        )
        row = WholeBookWindow(
            run_id=run_id,
            snapshot_id=snapshot.id,
            window_index=spec["window_index"],
            first_global_paragraph_index=spec["first_global_paragraph_index"],
            last_global_paragraph_index=spec["last_global_paragraph_index"],
            chapter_start_index=spec["chapter_start_index"],
            chapter_end_index=spec["chapter_end_index"],
            paragraph_count=max(spec["paragraph_count"], 1),
            character_count=max(spec["character_count"], 1),
            token_estimate=spec["token_estimate"],
            overlap_before_paragraphs=spec["overlap_before_paragraphs"],
            overlap_after_paragraphs=spec["overlap_after_paragraphs"],
            window_hash=wh,
            idempotency_key=idem,
            status=WholeBookUnitStatus.pending.value,
        )
        session.add(row)
        created.append(row)
    session.flush()

    coverage = calculate_window_coverage_v1(
        session, snapshot_id=snapshot.id, run_id=run_id, windows=created
    )
    manifest = {
        "windowing_version": WINDOWING_VERSION,
        "target_input_tokens": TARGET_INPUT_TOKENS,
        "hard_max_input_tokens": HARD_MAX_INPUT_TOKENS,
        "overlap_target_tokens": OVERLAP_TARGET_TOKENS,
        "snapshot_content_hash": snapshot.content_hash,
        "window_count": len(created),
        "coverage_ratio": coverage["coverage_ratio"],
        "duplicated_paragraphs": coverage["duplicated_paragraphs"],
        "uncovered_paragraphs": coverage["uncovered_paragraphs"],
        "order_valid": coverage["order_valid"],
        "window_set_hash": _window_set_hash(created),
    }
    session.add(
        WholeBookCheckpoint(
            run_id=run_id,
            stage_code="windowing",
            checkpoint_key="windowing_manifest",
            sequence_no=0,
            payload_hash=sha256_utf8(json.dumps(manifest, sort_keys=True)),
            checkpoint_payload_json=json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            created_at=datetime.now(timezone.utc),
        )
    )

    if stage is not None:
        stage.status = WholeBookStageStatus.completed.value
        stage.progress_current = len(created) or 1
        stage.progress_total = len(created) or 1
        stage.completed_at = datetime.now(timezone.utc)
    run.current_stage_code = "extract_entities_events"
    session.flush()

    return {
        "run_id": run_id,
        "snapshot_id": snapshot.id,
        "reused": False,
        "windowing_version": WINDOWING_VERSION,
        "windows": [window_to_dict(w) for w in created],
        "coverage": coverage,
        "warnings": warnings,
    }
