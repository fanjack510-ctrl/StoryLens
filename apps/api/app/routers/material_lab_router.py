"""创作知识库的读写口。

浏览、分类、检索既有知识保持免费；从用户已拆完的全书提取新素材、重新提取，
以及生成作品 Skill 是 Pro 的知识沉淀能力。权限在 API 边界强制执行，不能只靠前端标签。
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
    knowledge_library_summary,
    list_knowledge_sources,
    list_materials,
    list_patterns,
    rescore_library,
    run_material_lab,
    suggest_genre,
)
from app.narrative_core.material_lab.skill_generator import (
    BookSkillArtifact,
    build_book_skill,
)
from app.narrative_core.material_lab.legacy_import import (
    LegacyImportStatus,
    LegacyLibraryInspection,
    import_legacy_library,
    inspect_legacy_library,
    legacy_import_status,
)
from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository

router = APIRouter(prefix="/api/v1/material-lab", tags=["material-lab"])

_KNOWLEDGE_EXTRACTION_FEATURE = "knowledge_extraction"
_BOOK_SKILL_FEATURE = "book_skill_generation"


def _require_pro_feature(db: Session, feature_key: str, label: str) -> None:
    from app.services.entitlement import can_use_feature, commerce_config

    gate = can_use_feature(db, feature_key)
    if gate.get("enabled"):
        return
    commerce = commerce_config()
    raise HTTPException(
        status_code=403,
        detail={
            "error_code": "PRO_FEATURE_REQUIRED",
            "message": f"{label}是 StoryLens Pro 功能。可在爱发电购买授权，并在设置中输入授权码激活。",
            "details": {
                "feature_key": feature_key,
                "reason": gate.get("reason"),
                "afdian_product_url": str(commerce.get("afdian_product_url") or ""),
                "product_label": str(commerce.get("product_label") or "StoryLens Pro"),
            },
        },
    )


def _fail(exc: MaterialLabError) -> None:
    if exc.code in {
        "MATERIAL_LAB_SOURCE_NOT_FICTION",
        "MATERIAL_LAB_SOURCE_NOT_FULLY_DISSECTED",
        "MATERIAL_LAB_SKILL_RESULT_NOT_FOUND",
    }:
        status = 409
    elif exc.code.endswith("NOT_FOUND"):
        status = 404
    else:
        status = 400
    raise HTTPException(
        status_code=status, detail={"error_code": exc.code, "message": exc.message}
    )


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: 留空 = 让引擎从文本猜（结果里带 genre_source='auto' 和置信度）。
    genre_slug: str | None = None


class LegacyPathRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str


class LegacyImportRequest(LegacyPathRequest):
    expected_fingerprint: str
    confirm: bool = False


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
    """Compatibility endpoint; the product UI triggers extraction from /knowledge only."""
    _require_pro_feature(db, _KNOWLEDGE_EXTRACTION_FEATURE, "从全书提取素材")
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


@router.get("/library/summary")
def get_knowledge_library_summary(db: Session = Depends(get_db)) -> dict:
    return knowledge_library_summary(db)


@router.get("/library/sources")
def get_knowledge_sources(db: Session = Depends(get_db)) -> dict:
    return list_knowledge_sources(db)


@router.get("/library/legacy/status", response_model=LegacyImportStatus)
def get_legacy_import_status(db: Session = Depends(get_db)) -> LegacyImportStatus:
    return legacy_import_status(db)


@router.post("/library/legacy/inspect", response_model=LegacyLibraryInspection)
def post_legacy_library_inspect(body: LegacyPathRequest) -> LegacyLibraryInspection:
    try:
        return inspect_legacy_library(body.path)
    except MaterialLabError as exc:
        _fail(exc)
        raise


@router.post("/library/legacy/import", response_model=LegacyImportStatus)
def post_legacy_library_import(
    body: LegacyImportRequest, db: Session = Depends(get_db)
) -> LegacyImportStatus:
    if not body.confirm:
        _fail(MaterialLabError(
            "MATERIAL_LAB_LEGACY_CONFIRM_REQUIRED",
            "迁移前必须先检查旧库并明确确认",
        ))
    try:
        result = import_legacy_library(
            db, body.path, expected_fingerprint=body.expected_fingerprint
        )
        db.commit()
        return result
    except MaterialLabError as exc:
        db.rollback()
        _fail(exc)
        raise


@router.post("/library/sources/{book_id}/extract")
def post_library_source_extract(
    book_id: int, body: RunRequest, db: Session = Depends(get_db)
) -> dict:
    _require_pro_feature(db, _KNOWLEDGE_EXTRACTION_FEATURE, "从全书提取素材")
    try:
        result = run_material_lab(db, book_id, genre_slug=body.genre_slug)
        db.commit()
    except MaterialLabError as exc:
        db.rollback()
        _fail(exc)
        raise
    return result


@router.post("/library/skills/{book_id}", response_model=BookSkillArtifact)
def post_library_book_skill(book_id: int, db: Session = Depends(get_db)) -> BookSkillArtifact:
    """Generate a reusable SKILL.md from the newest completed full-book breakdown."""
    _require_pro_feature(db, _BOOK_SKILL_FEATURE, "生成作品 Skill")
    from app.narrative_core.material_lab.service import eligible_knowledge_source_runs

    run = eligible_knowledge_source_runs(db).get(int(book_id))
    if run is None:
        _fail(MaterialLabError(
            "MATERIAL_LAB_SOURCE_NOT_FULLY_DISSECTED",
            "只有已经完成全文拆文的小说才能生成作品机制 Skill",
        ))
    assert run is not None
    result = WholeBookV2Repository(db).load_result(int(run.id))
    if result is None:
        _fail(MaterialLabError(
            "MATERIAL_LAB_SKILL_RESULT_NOT_FOUND",
            "这次全文拆文没有可读取的正式报告，请先重新完成全书拆文",
        ))
    assert result is not None
    return build_book_skill(result, source_run_id=int(run.id))


@router.get("/materials")
def get_materials(
    db: Session = Depends(get_db),
    book_id: int | None = None,
    genre_slug: str | None = None,
    knowledge_role: str | None = Query(default=None, pattern="^(genre_example|domain_reference)$"),
    material_type: str | None = None,
    category_key: str | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    primary_only: bool = False,
    q: str | None = None,
    source_kind: str | None = Query(
        default=None, pattern="^(whole_book|legacy_import)$"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    try:
        return list_materials(
            db, book_id=book_id, genre_slug=genre_slug, knowledge_role=knowledge_role,
            material_type=material_type, category_key=category_key,
            min_score=min_score, primary_only=primary_only, q=q, limit=limit, offset=offset,
            source_kind=source_kind,
        )
    except MaterialLabError as exc:
        _fail(exc)
        raise


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
