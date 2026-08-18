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
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.short_form.dispatch import (
    SHORT_FORM_MAX_CHARS,
    SHORT_FORM_MAX_CHAPTERS,
    SHORT_FORM_SOFT_MAX_CHARS,
    book_is_short_form,
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
    logger.info(
        "short_form_stored book_id=%s segments=%s calls=%s", book_id,
        report.segments_planned, report.provider_calls,
    )
    return {"reused": False, **(_stored(db, int(book_id)) or {})}
