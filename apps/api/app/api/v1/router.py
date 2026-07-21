from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Book, Chapter, Paragraph
from app.db.session import get_db
from app.schemas.book import BookResponse, ChapterResponse, ImportResponse, ParagraphPage, ReparseConfirm
from app.services.book_service import (
    DuplicateBookError,
    ReparseProtectedError,
    import_book,
    preview_book,
    reparse_book,
    reparse_preview,
    reparse_with_file,
    reparse_with_file_preview,
)
from app.services.book_delete import (
    BookDeleteFailedError,
    BookHasActiveTasksError,
    BookNotFoundError,
    delete_book,
)
from app.services.extractors import EmptyDocumentError, InvalidFileTypeError

router = APIRouter(prefix="/api/v1")


def error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error_code": code, "message": message, "details": {}},
    )


@router.post("/books/import", response_model=ImportResponse, status_code=201)
async def upload_book(
    file: UploadFile = File(...), session: Session = Depends(get_db)
) -> ImportResponse:
    filename = file.filename or ""
    try:
        book = import_book(session, filename, await file.read())
    except InvalidFileTypeError as exc:
        raise error(415, "INVALID_FILE_TYPE", str(exc)) from exc
    except EmptyDocumentError as exc:
        raise error(422, "EMPTY_DOCUMENT", str(exc)) from exc
    except DuplicateBookError as exc:
        raise error(409, "DUPLICATE_BOOK", str(exc)) from exc
    except ValueError as exc:
        raise error(422, "INVALID_DOCUMENT", str(exc)) from exc
    chapter_count = (
        session.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == book.id))
        or 0
    )
    paragraph_count = (
        session.scalar(
            select(func.count()).select_from(Paragraph).where(Paragraph.book_id == book.id)
        )
        or 0
    )
    return ImportResponse(
        book_id=book.id,
        status=book.import_status,
        chapter_count=chapter_count,
        paragraph_count=paragraph_count,
        warning=book.import_warning,
    )


@router.post("/books/chapter-detection/preview")
async def chapter_detection_preview(file: UploadFile = File(...)) -> dict[str, object]:
    try:
        _, _, diagnostics = preview_book(file.filename or "", await file.read())
        return diagnostics
    except InvalidFileTypeError as exc:
        raise error(415, "INVALID_FILE_TYPE", str(exc)) from exc
    except (EmptyDocumentError, ValueError) as exc:
        raise error(422, "INVALID_DOCUMENT", str(exc)) from exc


@router.get("/books", response_model=list[BookResponse])
def list_books(session: Session = Depends(get_db)) -> list[Book]:
    return list(session.scalars(select(Book).order_by(Book.id)))


@router.get("/books/{book_id}", response_model=BookResponse)
def get_book(book_id: int, session: Session = Depends(get_db)) -> Book:
    book = session.get(Book, book_id)
    if book is None:
        raise error(404, "BOOK_NOT_FOUND", "书籍不存在")
    return book


@router.delete("/books/{book_id}", status_code=204)
def delete_book_endpoint(book_id: int, session: Session = Depends(get_db)) -> None:
    try:
        delete_book(session, book_id)
    except BookNotFoundError as exc:
        raise error(404, "BOOK_NOT_FOUND", "书籍不存在") from exc
    except BookHasActiveTasksError as exc:
        raise error(
            409,
            "BOOK_HAS_ACTIVE_TASKS",
            "这本书还有正在运行的分析任务，请先停止任务后再删除。",
        ) from exc
    except BookDeleteFailedError as exc:
        raise error(500, "BOOK_DELETE_FAILED", "删除失败，书籍和分析数据均未发生变化。") from exc


@router.get("/books/{book_id}/import-diagnostics")
def import_diagnostics(book_id: int, session: Session = Depends(get_db)) -> dict[str, object]:
    book = session.get(Book, book_id)
    if book is None:
        raise error(404, "BOOK_NOT_FOUND", "书籍不存在")
    import json
    return json.loads(book.import_diagnostics_json or "{}")


@router.post("/books/{book_id}/reparse-preview")
def book_reparse_preview(book_id: int, session: Session = Depends(get_db)) -> dict[str, object]:
    book = session.get(Book, book_id)
    if book is None:
        raise error(404, "BOOK_NOT_FOUND", "书籍不存在")
    try:
        return reparse_preview(session, book)
    except ValueError as exc:
        raise error(409, "SOURCE_CONTENT_UNAVAILABLE", str(exc)) from exc


@router.post("/books/{book_id}/reparse-with-file-preview")
async def book_reparse_with_file_preview(
    book_id: int, file: UploadFile = File(...), parsing_options: str | None = Form(None),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    del parsing_options
    book = session.get(Book, book_id)
    if book is None:
        raise error(404, "BOOK_NOT_FOUND", "书籍不存在")
    try:
        return reparse_with_file_preview(session, book, file.filename or "", await file.read())
    except (InvalidFileTypeError, EmptyDocumentError, ValueError) as exc:
        raise error(422, "INVALID_DOCUMENT", str(exc)) from exc


@router.post("/books/{book_id}/reparse-with-file")
async def book_reparse_with_file(
    book_id: int, file: UploadFile = File(...), confirm: bool = Form(False),
    strategy: str = Form(...), confirm_different_file: bool = Form(False),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    if not confirm:
        raise error(422, "REPARSE_CONFIRMATION_REQUIRED", "必须显式确认重解析")
    book = session.get(Book, book_id)
    if book is None:
        raise error(404, "BOOK_NOT_FOUND", "书籍不存在")
    try:
        result = reparse_with_file(session, book, file.filename or "", await file.read(), strategy,
                                   confirm_different_file)
        return {"book_id": result.id, "strategy": strategy, "revision_of_book_id": result.revision_of_book_id}
    except ReparseProtectedError as exc:
        raise error(409, "REPARSE_HISTORY_PROTECTED", str(exc)) from exc
    except ValueError as exc:
        raise error(422, "REPARSE_FILE_MISMATCH", str(exc)) from exc


@router.post("/books/{book_id}/reparse")
def book_reparse(book_id: int, value: ReparseConfirm, session: Session = Depends(get_db)) -> dict[str, object]:
    if not value.confirm:
        raise error(422, "REPARSE_CONFIRMATION_REQUIRED", "重新识别必须显式确认")
    book = session.get(Book, book_id)
    if book is None:
        raise error(404, "BOOK_NOT_FOUND", "书籍不存在")
    try:
        return reparse_book(session, book)
    except ReparseProtectedError as exc:
        raise error(409, "REPARSE_HISTORY_PROTECTED", str(exc)) from exc
    except ValueError as exc:
        raise error(409, "SOURCE_CONTENT_UNAVAILABLE", str(exc)) from exc


@router.get("/books/{book_id}/chapters", response_model=list[ChapterResponse])
def list_chapters(book_id: int, session: Session = Depends(get_db)) -> list[Chapter]:
    if session.get(Book, book_id) is None:
        raise error(404, "BOOK_NOT_FOUND", "书籍不存在")
    return list(
        session.scalars(
            select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index)
        )
    )


@router.get("/chapters/{chapter_id}/paragraphs", response_model=None)
def list_paragraphs(
    chapter_id: int, offset: int | None = None, limit: int | None = None,
    paragraph_id: str | None = None, session: Session = Depends(get_db)
) -> ParagraphPage | list[Paragraph]:
    if session.get(Chapter, chapter_id) is None:
        raise error(404, "CHAPTER_NOT_FOUND", "章节不存在")
    total = session.scalar(select(func.count()).select_from(Paragraph).where(Paragraph.chapter_id == chapter_id)) or 0
    legacy = offset is None and limit is None and paragraph_id is None
    effective_limit = min(max(limit or 200, 1), 500)
    effective_offset = max(offset or 0, 0)
    if paragraph_id:
        target = session.get(Paragraph, paragraph_id)
        if target is None or target.chapter_id != chapter_id:
            raise error(404, "PARAGRAPH_NOT_FOUND", "目标段落不属于该章节")
        effective_offset = ((target.paragraph_index - 1) // effective_limit) * effective_limit
    items = list(
        session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter_id)
            .order_by(Paragraph.paragraph_index)
            .offset(0 if legacy else effective_offset)
            .limit(total if legacy else effective_limit)
        )
    )
    if legacy:
        return items
    return ParagraphPage(items=items, offset=effective_offset, limit=effective_limit, total=total,
                         has_more=effective_offset + len(items) < total)
