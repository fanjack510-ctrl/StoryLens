"""Pro Whole-Book Insights API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.services.whole_book_insights_errors import WholeBookInsightsError
from app.narrative_core.services.whole_book_insights_service import compute_whole_book_insights

router = APIRouter(prefix="/api/v1", tags=["pro-whole-book-insights"])


@router.get("/books/{book_id}/pro/whole-book-insights")
def get_whole_book_insights(book_id: int, session: Session = Depends(get_db)) -> dict:
    try:
        return compute_whole_book_insights(session, book_id)
    except WholeBookInsightsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error_code": exc.code.value,
                "message": exc.message,
                "details": exc.details,
            },
        ) from exc
