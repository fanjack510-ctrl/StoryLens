"""素材库的读写口。

素材库跑本地确定性引擎（provider='local'）：不调云端模型、不要密钥、不联网。
基础资料库免费，所以这个文件里没有 Pro 门——组合器/导出/跨书统计将来各自把门。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.material_lab.service import (
    MaterialLabError,
    book_summary,
    genre_options,
    list_materials,
    list_patterns,
    rescore_library,
    run_material_lab,
    suggest_genre,
)

router = APIRouter(prefix="/api/v1/material-lab", tags=["material-lab"])


def _fail(exc: MaterialLabError) -> None:
    status = 404 if exc.code.endswith("NOT_FOUND") else 400
    raise HTTPException(
        status_code=status, detail={"error_code": exc.code, "message": exc.message}
    )


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: 留空 = 让引擎从文本猜（结果里带 genre_source='auto' 和置信度）。
    genre_slug: str | None = None


@router.get("/genres")
def get_genres() -> dict:
    return {"items": genre_options()}


@router.get("/books/{book_id}/genre-suggestion")
def get_genre_suggestion(book_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return suggest_genre(db, book_id)
    except MaterialLabError as exc:
        _fail(exc)
        raise


@router.post("/books/{book_id}/run")
def post_run(book_id: int, body: RunRequest, db: Session = Depends(get_db)) -> dict:
    try:
        result = run_material_lab(db, book_id, genre_slug=body.genre_slug)
        db.commit()
    except MaterialLabError as exc:
        db.rollback()
        _fail(exc)
        raise
    return result


@router.get("/books/{book_id}/summary")
def get_book_summary(book_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return book_summary(db, book_id)
    except MaterialLabError as exc:
        _fail(exc)
        raise


@router.get("/materials")
def get_materials(
    db: Session = Depends(get_db),
    book_id: int | None = None,
    material_type: str | None = None,
    category_key: str | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    primary_only: bool = False,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return list_materials(
        db, book_id=book_id, material_type=material_type, category_key=category_key,
        min_score=min_score, primary_only=primary_only, q=q, limit=limit, offset=offset,
    )


@router.get("/patterns")
def get_patterns(
    db: Session = Depends(get_db),
    genre_slug: str | None = None,
    category_key: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return list_patterns(
        db, genre_slug=genre_slug, category_key=category_key, limit=limit, offset=offset
    )


@router.post("/rescore")
def post_rescore(db: Session = Depends(get_db)) -> dict:
    """多本书陆续入库后拉平频次型子分。本地计算，免费。"""
    updated = rescore_library(db)
    db.commit()
    return {"rescored": updated}
