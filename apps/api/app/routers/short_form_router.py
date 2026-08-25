"""HTTP for 短篇精读.

Synchronous on purpose. A short piece is nine or ten provider calls — under two minutes — and
the alternative is a run table, a progress projection, a background worker and a recovery path,
all of which exist for the whole-book engine because *that* takes twenty minutes. Building them
here before anyone has run this twice would be inventing machinery for a problem not yet had.

The result is stored, though. A reading costs real money, and a page reload is not a reason to
pay again.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.short_form.dispatch import (
    SHORT_FORM_MAX_CHARS,
    SHORT_FORM_MAX_CHAPTERS,
    SHORT_FORM_SOFT_MAX_CHARS,
    book_analysis_form,
    book_is_short_form,
    book_short_form_allowed,
    segmentation_estimate,
    short_form_allowed,
    suggested_form,
    SHORT_FORM_HARD_MAX_CHARS,
    FORM_LONG,
    FORM_SHORT,
)
from app.narrative_core.short_form.prompts import GENRE_LENS
from app.narrative_core.short_form.service import analyse_short_form

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/books", tags=["short-form"])


class AnalyseRequest(BaseModel):
    genre: str = ""
    #: Ask again even though a reading is already stored. The client sends this only from an
    #: explicit "重新分析", because the default must never be to spend money twice.
    force: bool = False
    #: Cut the piece into scenes afresh rather than keeping the boundaries the last reading
    #: settled on. Off by default: re-reading is for a better reading, and re-cutting renumbers
    #: every segment, which invalidates every callback the previous reading wrote.
    resegment: bool = False


class PdfExportRequest(BaseModel):
    """The printable document is built by the desktop client that owns its layout."""

    html: str


def _stored(session: Session, book_id: int) -> dict[str, Any] | None:
    row = session.execute(
        text(
            "SELECT id, genre, provider_name, model_name, segments_planned, segments_resplit,"
            " provider_calls, input_tokens, output_tokens, result_json, created_at"
            " FROM short_form_results WHERE book_id = :book_id ORDER BY id DESC LIMIT 1"
        ),
        {"book_id": int(book_id)},
    ).mappings().first()
    if row is None:
        return None
    payload = dict(row)
    payload["result"] = json.loads(payload.pop("result_json") or "{}")
    payload["created_at"] = str(payload["created_at"])
    return payload


def _active_provider(session: Session) -> tuple[str, str]:
    """The provider this reading will use.

    The whole-book engine pins provider and model onto its run row and reads them back; a
    short-form reading has no run row, so it resolves the same settings directly. Kept here
    rather than in the pipeline so `run_short_form` stays free of the database.
    """
    from app.db.models import ProviderConfiguration
    from app.services.provider_runtime import get_active_cloud_provider

    name = get_active_cloud_provider(session)
    row = (
        session.query(ProviderConfiguration)
        .filter(ProviderConfiguration.provider_name == name)
        .one_or_none()
    )
    # `plus_model` is the same field the whole-book run pins at create, so the two readings of
    # one book are done by the same model unless the user changes it between them.
    model = str(getattr(row, "plus_model", "") or "").strip()
    if not model:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "PROVIDER_NOT_CONFIGURED",
                "message": "还没有配置可用的模型，请先到设置里完成 AI 服务配置。",
                "details": {"provider": name},
            },
        )
    return name, model


@router.get("/{book_id}/short-form/prepare")
def prepare(book_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Whether this book takes the short-form reading, and what is already known about it."""
    counts = db.execute(
        text(
            "SELECT COUNT(*), COALESCE(SUM(word_count), 0) FROM chapters WHERE book_id = :book_id"
        ),
        {"book_id": int(book_id)},
    ).first() or (0, 0)
    title = db.execute(
        text("SELECT title FROM books WHERE id = :book_id"), {"book_id": int(book_id)}
    ).scalar()
    if title is None:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "BOOK_NOT_FOUND", "message": "书籍不存在", "details": {}},
        )
    chapters, characters = int(counts[0] or 0), int(counts[1] or 0)
    return {
        "book_id": int(book_id),
        "book_title": str(title),
        "chapter_count": chapters,
        "character_count": characters,
        "is_short_form": book_is_short_form(db, int(book_id)),
        # What the reader chose, "" if they were never asked; and what the old inference would
        # have said, which is what the import panel offers as the default.
        "analysis_form": book_analysis_form(db, int(book_id)),
        "suggested_form": suggested_form(db, int(book_id)),
        # Whether 短篇 may be picked at all. Sent so the panel can disable the option and say
        # why, rather than offering something the server will refuse.
        "short_form_allowed": short_form_allowed(characters),
        "hard_max_chars": SHORT_FORM_HARD_MAX_CHARS,
        # Reported so the panel can warn before the most expensive call of the run, not
        # enforced — the reader's answer stands either way.
        "segmentation": segmentation_estimate(db, int(book_id)),
        "thresholds": {
            "max_chars": SHORT_FORM_MAX_CHARS,
            "soft_max_chars": SHORT_FORM_SOFT_MAX_CHARS,
            "max_chapters": SHORT_FORM_MAX_CHAPTERS,
        },
        "genres": list(GENRE_LENS.keys()),
        "latest": _stored(db, int(book_id)),
    }


@router.post("/{book_id}/short-form/analyse")
def analyse(
    book_id: int, body: AnalyseRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    if not book_is_short_form(db, int(book_id)):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "NOT_SHORT_FORM",
                "message": "这本书不走短篇精读，请用全书分析。",
                "details": {},
            },
        )
    existing = _stored(db, int(book_id))
    if existing and not body.force:
        # Returning the stored reading rather than silently making a second one: the caller
        # asked to analyse, and the honest answer is "this is already analysed".
        return {"reused": True, **existing}

    provider_name, model_name = _active_provider(db)
    report = analyse_short_form(
        db,
        int(book_id),
        genre=body.genre,
        provider_name=provider_name,
        model_name=model_name,
        resegment=body.resegment,
    )
    result = report.result
    if result is None or result.availability == "unavailable":
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "SHORT_FORM_EMPTY",
                "message": "没有产出任何分段，请检查这本书的正文是否为空。",
                "details": {"failures": report.failures},
            },
        )

    db.execute(
        text(
            "INSERT INTO short_form_results (book_id, genre, provider_name, model_name,"
            " segments_planned, segments_resplit, provider_calls, result_json)"
            " VALUES (:book_id, :genre, :provider, :model, :planned, :resplit, :calls, :json)"
        ),
        {
            "book_id": int(book_id),
            "genre": body.genre,
            "provider": provider_name,
            "model": model_name,
            "planned": report.segments_planned,
            "resplit": report.segments_resplit,
            "calls": report.provider_calls,
            "json": json.dumps(result.model_dump(), ensure_ascii=False),
        },
    )
    db.commit()
    # The callback counts are logged rather than stored because both checks *blank* the
    # field, so a reading with few callbacks looks exactly like a reading whose callbacks were
    # all thrown away — and only the second is a problem. Measured on 《面馆的最后一天》: one
    # run kept 15 of 16, the next kept 8, and nothing anywhere said which of the two it was.
    logger.info(
        "short_form_stored book_id=%s segments=%s calls=%s "
        "callbacks_written=%s dropped_bad_target=%s dropped_bad_content=%s",
        book_id, report.segments_planned, report.provider_calls,
        report.callbacks_written, report.callbacks_dropped_bad_target,
        report.callbacks_dropped_bad_content,
    )
    return {"reused": False, **(_stored(db, int(book_id)) or {})}


@router.post("/{book_id}/short-form/readings/{reading_id}/export-pdf")
def export_short_form_pdf(
    book_id: int,
    reading_id: int,
    body: PdfExportRequest,
    db: Session = Depends(get_db),
) -> Response:
    """Render one stored short-form worksheet with the shared Pro PDF pipeline."""
    exists = db.execute(
        text(
            "SELECT 1 FROM short_form_results"
            " WHERE id = :reading_id AND book_id = :book_id"
        ),
        {"reading_id": int(reading_id), "book_id": int(book_id)},
    ).scalar()
    if not exists:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "SHORT_FORM_RESULT_NOT_FOUND",
                "message": "找不到这份短篇拆稿，请刷新页面后重试。",
                "details": {"book_id": int(book_id), "reading_id": int(reading_id)},
            },
        )

    # Full-book, chapter and short-form PDF exports are one product and one renderer.
    from app.narrative_core.whole_book_v2.router import render_report_pdf

    return render_report_pdf(db, body.html)


class AnalysisFormRequest(BaseModel):
    #: "short" | "long". Changeable at any time: the book title taught this lesson the hard
    #: way — a value fixed at import with no way to correct it is wrong forever.
    form: str


@router.put("/{book_id}/analysis-form")
def set_analysis_form(
    book_id: int, body: AnalysisFormRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Record whether this work is read as one piece or as a book.

    Nothing is recomputed and nothing is discarded: a stored reading from the other pipeline
    stays where it is, because it was paid for and is still what it was.
    """
    form = str(body.form or "").strip()
    if form not in (FORM_SHORT, FORM_LONG):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_ANALYSIS_FORM",
                "message": "只能是 short 或 long。",
                "details": {"got": form},
            },
        )
    if form == FORM_SHORT and not book_short_form_allowed(db, int(book_id)):
        # Refused, not warned. Segmentation sends the whole piece in one call, so this would
        # spend the most expensive call of the run and then fail on context length.
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "SHORT_FORM_TOO_LONG",
                "message": (
                    f"超过 {SHORT_FORM_HARD_MAX_CHARS:,} 字的作品不能按短篇读："
                    "切段要把全文一次发给模型，装不下。"
                ),
                "details": {"hard_max_chars": SHORT_FORM_HARD_MAX_CHARS},
            },
        )
    updated = db.execute(
        text("UPDATE books SET analysis_form = :form WHERE id = :book_id"),
        {"form": form, "book_id": int(book_id)},
    ).rowcount
    if not updated:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "BOOK_NOT_FOUND", "message": "书籍不存在", "details": {}},
        )
    db.commit()
    return {
        "book_id": int(book_id),
        "analysis_form": form,
        "is_short_form": book_is_short_form(db, int(book_id)),
        "segmentation": segmentation_estimate(db, int(book_id)),
    }
