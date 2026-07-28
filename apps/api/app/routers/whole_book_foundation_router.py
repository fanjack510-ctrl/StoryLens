"""Whole-book foundation APIs — Snapshot, Run, Windowing (Wave B diagnostics)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.services.whole_book_foundation_errors import WholeBookFoundationError
from app.narrative_core.services.whole_book_run_v1_service import (
    cancel_whole_book_run_v1,
    create_whole_book_run_v1,
    get_run,
    list_runs_for_book,
    list_stages,
    pause_whole_book_run_v1,
    resume_whole_book_run_v1,
    run_to_dict,
    stage_to_dict,
    start_whole_book_run_v1,
)
from app.narrative_core.services.whole_book_snapshot_v1_service import (
    chapter_to_dict,
    create_or_reuse_book_snapshot_v1,
    get_snapshot,
    list_chapters,
    list_paragraphs,
    list_snapshots_for_book,
    to_metadata_dict,
)
from app.narrative_core.services.whole_book_windowing_v1_service import (
    calculate_window_coverage_v1,
    generate_whole_book_windows_v1,
    list_checkpoints,
    list_windows,
    window_to_dict,
)

router = APIRouter(prefix="/api/v1", tags=["whole-book-foundation"])


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: int = Field(gt=0)
    mode: str = "whole_book_native"
    client_request_id: str = Field(min_length=1, max_length=128)
    result_origin: str = "fixture"


def _raise_foundation(exc: WholeBookFoundationError) -> None:
    raise HTTPException(status_code=400, detail={"error_code": exc.code, "message": exc.message})


@router.post("/books/{book_id}/whole-book/snapshots")
def create_snapshot(book_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        result = create_or_reuse_book_snapshot_v1(db, book_id)
        db.commit()
        db.refresh(result["snapshot"])
        return {
            "snapshot": to_metadata_dict(result["snapshot"]),
            "reused": result["reused"],
        }
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


@router.get("/books/{book_id}/whole-book/snapshots")
def list_book_snapshots(book_id: int, db: Session = Depends(get_db)) -> dict:
    rows = list_snapshots_for_book(db, book_id)
    return {"snapshots": [to_metadata_dict(row) for row in rows]}


@router.get("/whole-book/snapshots/{snapshot_id}")
def get_snapshot_detail(snapshot_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        snapshot = get_snapshot(db, snapshot_id)
        return {"snapshot": to_metadata_dict(snapshot)}
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.get("/whole-book/snapshots/{snapshot_id}/chapters")
def get_snapshot_chapters(snapshot_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        chapters = list_chapters(db, snapshot_id)
        return {"chapters": [chapter_to_dict(ch) for ch in chapters]}
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.get("/whole-book/snapshots/{snapshot_id}/paragraphs")
def get_snapshot_paragraphs(
    snapshot_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    chapter_index: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    try:
        items, total = list_paragraphs(
            db, snapshot_id, offset=offset, limit=limit, chapter_index=chapter_index
        )
        return {"paragraphs": items, "total": total, "offset": offset, "limit": limit}
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.post("/books/{book_id}/whole-book/runs")
def create_run(book_id: int, body: CreateRunRequest, db: Session = Depends(get_db)) -> dict:
    try:
        run = create_whole_book_run_v1(
            db,
            book_id,
            body.snapshot_id,
            body.mode,
            body.client_request_id,
            body.result_origin,
        )
        db.commit()
        db.refresh(run)
        return {"run": run_to_dict(run)}
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_MODE", "message": str(exc)}) from exc


@router.get("/books/{book_id}/whole-book/runs")
def list_book_runs(book_id: int, db: Session = Depends(get_db)) -> dict:
    rows = list_runs_for_book(db, book_id)
    return {"runs": [run_to_dict(row) for row in rows]}


@router.get("/whole-book/runs/{run_id}")
def get_run_detail(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        run = get_run(db, run_id)
        return {"run": run_to_dict(run)}
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.get("/whole-book/runs/{run_id}/stages")
def get_run_stages(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        stages = list_stages(db, run_id)
        return {"stages": [stage_to_dict(s) for s in stages]}
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.post("/whole-book/runs/{run_id}/start")
def start_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        run = start_whole_book_run_v1(db, run_id)
        db.commit()
        db.refresh(run)
        return {"run": run_to_dict(run)}
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


@router.post("/whole-book/runs/{run_id}/pause")
def pause_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        run = pause_whole_book_run_v1(db, run_id)
        db.commit()
        db.refresh(run)
        return {"run": run_to_dict(run)}
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


@router.post("/whole-book/runs/{run_id}/resume")
def resume_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        run = resume_whole_book_run_v1(db, run_id)
        db.commit()
        db.refresh(run)
        return {"run": run_to_dict(run)}
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


@router.post("/whole-book/runs/{run_id}/cancel")
def cancel_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        run = cancel_whole_book_run_v1(db, run_id)
        db.commit()
        db.refresh(run)
        return {"run": run_to_dict(run)}
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


@router.post("/whole-book/runs/{run_id}/windows/generate")
def generate_windows(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        result = generate_whole_book_windows_v1(db, run_id)
        db.commit()
        return result
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


@router.get("/whole-book/runs/{run_id}/windows")
def get_windows(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        windows = list_windows(db, run_id)
        return {"windows": [window_to_dict(w) for w in windows]}
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.get("/whole-book/runs/{run_id}/window-coverage")
def get_window_coverage(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        run = get_run(db, run_id)
        windows = list_windows(db, run_id)
        if run.snapshot_id is None:
            raise WholeBookFoundationError("WHOLE_BOOK_SNAPSHOT_NOT_FOUND", "run has no snapshot")
        coverage = calculate_window_coverage_v1(
            db, snapshot_id=run.snapshot_id, run_id=run_id, windows=windows
        )
        return {"coverage": coverage}
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.get("/whole-book/runs/{run_id}/checkpoints")
def get_checkpoints(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return {"checkpoints": list_checkpoints(db, run_id)}
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise
