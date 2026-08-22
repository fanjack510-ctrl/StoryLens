"""Free whole-book product coordination APIs (WB-1.7 backend)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db, get_session_factory
from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    get_run_chapter_functions_product_v1,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_free_product_v1_service import (
    create_fixture_free_whole_book_analysis_v1,
    create_free_whole_book_analysis_v1,
    prepare_free_whole_book_analysis_v1,
    resume_failed_free_whole_book_analysis_v1,
)
from app.narrative_core.services.whole_book_minimal_read_v1_service import (
    get_run_overview,
)
from app.narrative_core.services.whole_book_product_capability_v1 import (
    AccessTier,
    require_capability_access,
)
from app.narrative_core.services.whole_book_structure_product_v1_service import (
    get_run_structure_product_v1,
)
from app.services.whole_book_free_background import schedule_free_whole_book_pipeline_background

router = APIRouter(prefix="/api/v1", tags=["whole-book-free-product"])

_NOT_FOUND_CODES = {
    WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_NOT_FOUND.value,
    WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_NOT_FOUND.value,
    WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND.value,
}


class CreateFreeRunRequest(BaseModel):
    """Formal free create — consent may be created inline from limits (CHG-062)."""

    model_config = ConfigDict(extra="forbid")
    estimate_id: int = Field(gt=0)
    consent_id: int | None = Field(default=None, gt=0)
    client_request_id: str = Field(min_length=1, max_length=128)
    max_provider_calls: int | None = Field(default=None, gt=0)
    max_input_tokens: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    max_cost_budget_cny: str | None = None
    auto_retry_enabled: bool = False
    #: Which reading to run: the diagnostic, or 拆文 (CHG-108). Defaults to the diagnostic, so
    #: every existing caller keeps the behaviour it has. The two share a snapshot, a planner and
    #: an extraction pass and differ only in the four bounded units above L1.
    analysis_mode: Literal["diagnostic", "story_breakdown", "comprehend"] = "diagnostic"
    # CHG-080 reanalysis
    reanalyse: bool = False
    force_full_reanalysis: bool = False
    previous_run_id: int | None = Field(default=None, gt=0)


class CreateFixtureFreeRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: str | None = Field(default=None, max_length=128)
    execute_pipeline: bool = True


class ResumeFailedFreeRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: int = Field(gt=0)


def _raise_foundation(exc: WholeBookFoundationError) -> None:
    status = 404 if exc.code in _NOT_FOUND_CODES else 400
    detail: dict = {"error_code": exc.code, "message": exc.message}
    if getattr(exc, "details", None):
        detail["details"] = exc.details
    raise HTTPException(
        status_code=status,
        detail=detail,
    )


def _prepare(book_id: int, db: Session, analysis_mode: str = "diagnostic") -> dict:
    try:
        result = prepare_free_whole_book_analysis_v1(db, book_id, analysis_mode=analysis_mode)
        db.commit()
        return result
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


def _create_fixture(book_id: int, body: CreateFixtureFreeRunRequest, db: Session) -> dict:
    try:
        result = create_fixture_free_whole_book_analysis_v1(
            db,
            book_id,
            client_request_id=body.client_request_id,
            execute_pipeline=body.execute_pipeline,
        )
        db.commit()
        return result
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


@router.get("/books/{book_id}/whole-book/free/prepare")
def prepare_free_analysis(
    book_id: int,
    analysis_mode: Literal["diagnostic", "story_breakdown", "comprehend"] = "diagnostic",
    db: Session = Depends(get_db),
) -> dict:
    """The panel prices the run the caller is about to start, which is not always the
    diagnostic: 拆文 makes four bounded calls where the diagnostic makes eight."""
    return _prepare(book_id, db, analysis_mode)


@router.get("/books/{book_id}/whole-book/prepare")
def prepare_free_analysis_product_alias(
    book_id: int,
    analysis_mode: Literal["diagnostic", "story_breakdown", "comprehend"] = "diagnostic",
    db: Session = Depends(get_db),
) -> dict:
    """Product-facing alias used by Wave D desktop client."""
    return _prepare(book_id, db, analysis_mode)


@router.post("/books/{book_id}/whole-book/free/create")
def create_free_analysis(
    book_id: int,
    body: CreateFreeRunRequest,
    db: Session = Depends(get_db),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> dict:
    # 确认门（10_ADAPTIVE_PROFILE_LAYER §4.3）：画像先于首次分析。此前画像只决定引擎选择，
    # 未确认的书静默走旧引擎——现在与单章入口同一道硬门。resume 与 fixture 入口不设门：
    # 恢复的是已付费的进度，fixture 是开发工具。
    from app.narrative_core.services.long_novel_pipeline_v1 import profile_confirmation_state

    # 「读懂」不过画像门。画像的五根轴是付费模式 / 读者 / 爽感引擎 / 人称 / 篇幅——全是网文
    # 的东西；那道门存在，是因为画像决定小说分析走哪个引擎、量哪几条类型轴，而读懂一条都不用。
    # 让人去确认「这本人因工程手册的爽感引擎是什么」，是在问一个没有答案的问题。
    profile_state = (
        "confirmed"
        if body.analysis_mode == "comprehend"
        else profile_confirmation_state(db, book_id)
    )
    if profile_state != "confirmed":
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "PROFILE_CONFIRMATION_REQUIRED",
                "message": "开始分析前，请先确认这本书的作品画像——画像决定分析按什么类型侧重进行。"
                + ("画像草稿已生成，确认即可。" if profile_state == "draft" else ""),
                "details": {"book_id": book_id, "profile_status": profile_state},
            },
        )
    try:
        consent_id = body.consent_id
        if consent_id is None:
            from decimal import Decimal

            from app.db.models import WholeBookCostEstimate
            from app.narrative_core.services.whole_book_consent_service import (
                create_whole_book_consent,
            )

            if not body.max_cost_budget_cny:
                raise WholeBookFoundationError(
                    WholeBookFoundationErrorCode.BUDGET_TOO_LOW,
                    "请填写最高费用预算后再开始分析",
                )
            # 拆文 exists only in the long-novel engine. The dispatcher drops the mode for a book
            # that engine will not take, so without this the user pays for a full run and is
            # handed a diagnostic they did not ask for — the worst way to fail, because the
            # result looks complete.
            if body.analysis_mode == "story_breakdown":
                from app.narrative_core.services.long_novel_pipeline_v1 import (
                    book_uses_long_novel_engine,
                )

                if not book_uses_long_novel_engine(db, book_id):
                    raise WholeBookFoundationError(
                        WholeBookFoundationErrorCode.WHOLE_BOOK_MODE_UNAVAILABLE,
                        "拆文需要先确认这本书的作品画像，并且书籍要能被切分成 4 章以上。",
                    )
            estimate = db.get(WholeBookCostEstimate, body.estimate_id)
            if estimate is None or estimate.book_id != book_id:
                raise WholeBookFoundationError(
                    WholeBookFoundationErrorCode.CONSENT_STALE,
                    "分析配置已经变化，请重新确认费用预估",
                )
            consent = create_whole_book_consent(
                db,
                book_id=book_id,
                estimate_id=body.estimate_id,
                user_budget_limit_cny=Decimal(str(body.max_cost_budget_cny)),
                max_provider_calls=body.max_provider_calls,
                max_input_tokens=body.max_input_tokens,
                max_output_tokens=body.max_output_tokens,
                auto_retry_enabled=bool(body.auto_retry_enabled),
                max_retries_per_unit=0,
            )
            consent_id = consent.id
        result = create_free_whole_book_analysis_v1(
            db,
            book_id,
            estimate_id=body.estimate_id,
            consent_id=int(consent_id),
            client_request_id=body.client_request_id,
            defer_execution=True,
            reanalyse=bool(body.reanalyse),
            force_full_reanalysis=bool(body.force_full_reanalysis),
            previous_run_id=body.previous_run_id,
        )
        db.commit()
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise

    if result.get("deferred_execution"):
        # CHG-081: dedicated daemon thread — not FastAPI BackgroundTasks — so
        # long Hierarchical work cannot block request teardown / starve health.
        schedule_free_whole_book_pipeline_background(
            session_factory,
            int(result["run_id"]),
            provider_config_id=result.get("provider_config_id"),
            force_full_reanalysis=bool(result.get("force_full_reanalysis")),
            previous_run_id=result.get("previous_run_id"),
            mode=body.analysis_mode,
        )
    return result


@router.get("/whole-book-runs/{run_id}/comprehend")
def read_comprehend_result(run_id: int, db: Session = Depends(get_db)) -> dict:
    """「读懂」的结果。

    单独一个口，不并进 v2：那份契约是给评测/拆文的（结构、节奏、人物、悬念），而这份产出是
    主张 / 依据 / 做法 / 术语 / 存疑。塞进同一个口，读的人会以为它们是同一种东西。
    """
    from app.narrative_core.services.comprehend_pipeline_v1 import load_comprehend_result

    payload = load_comprehend_result(db, int(run_id))
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "COMPREHEND_RESULT_NOT_FOUND",
                "message": "这次「读懂」还没有结果。分析可能仍在进行，或者这本书用的是别的读法。",
            },
        )
    return payload


@router.post("/books/{book_id}/whole-book/free/resume")
def resume_failed_free_analysis(
    book_id: int,
    body: ResumeFailedFreeRunRequest,
    db: Session = Depends(get_db),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> dict:
    """Resume a failed Hierarchical V2 run from same-run real_provider checkpoints."""
    try:
        result = resume_failed_free_whole_book_analysis_v1(
            db,
            book_id,
            run_id=int(body.run_id),
        )
        db.commit()
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise

    if result.get("deferred_execution"):
        schedule_free_whole_book_pipeline_background(
            session_factory,
            int(result["run_id"]),
            provider_config_id=result.get("provider_config_id"),
            force_full_reanalysis=False,
            previous_run_id=None,
        )
    return result


@router.post("/books/{book_id}/whole-book/free/create-fixture")
def create_fixture_free_analysis(
    book_id: int,
    body: CreateFixtureFreeRunRequest,
    db: Session = Depends(get_db),
) -> dict:
    return _create_fixture(book_id, body, db)


@router.post("/books/{book_id}/whole-book/runs/fixture")
def create_fixture_free_analysis_alias(
    book_id: int,
    body: CreateFixtureFreeRunRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Product-facing alias used by Wave D desktop client."""
    return _create_fixture(book_id, body, db)


@router.get("/whole-book/runs/{run_id}/overview-gated")
def gated_overview(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        require_capability_access("whole_book.overview", AccessTier.free)
        overview = get_run_overview(db, run_id)
        if overview is None:
            raise HTTPException(
                status_code=404,
                detail={"error_code": "OVERVIEW_NOT_FOUND", "message": "全书总览尚未生成"},
            )
        return {"overview": overview}
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.get("/whole-book/runs/{run_id}/structure")
def product_structure_result(run_id: int, db: Session = Depends(get_db)) -> dict:
    """Product StructureStagesResultV2 envelope (WB-2.1)."""

    try:
        require_capability_access("whole_book.structure", AccessTier.free)
        payload = get_run_structure_product_v1(db, run_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "STRUCTURE_RESULT_ABSENT",
                    "message": "故事结构结果尚未生成",
                },
            )
        return payload
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.get("/whole-book/runs/{run_id}/chapter-functions")
def product_chapter_functions_result(
    run_id: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    cursor: str | None = Query(default=None),
    offset: int | None = Query(default=None, ge=0),
    function: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> dict:
    """Product ChapterFunctionsResultV2 envelope (WB-2.2)."""

    try:
        require_capability_access("whole_book.chapter_functions", AccessTier.free)
        payload = get_run_chapter_functions_product_v1(
            db,
            run_id,
            limit=limit,
            cursor=cursor,
            offset=offset,
            function=function,
            status=status,
        )
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "CHAPTER_FUNCTIONS_RESULT_ABSENT",
                    "message": "章节功能结果尚未生成",
                },
            )
        return payload
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.get("/whole-book/runs/{run_id}/chapter-functions/{chapter_id}")
def product_chapter_functions_chapter_result(
    run_id: int,
    chapter_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Single-chapter ChapterFunctionsResultV2 item envelope."""

    try:
        require_capability_access("whole_book.chapter_functions", AccessTier.free)
        payload = get_run_chapter_functions_product_v1(
            db,
            run_id,
            limit=1,
            chapter_id=chapter_id,
        )
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "CHAPTER_FUNCTION_CHAPTER_NOT_FOUND",
                    "message": "该章节功能结果不存在",
                },
            )
        return payload
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise
