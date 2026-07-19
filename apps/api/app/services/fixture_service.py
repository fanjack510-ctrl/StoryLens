import hashlib
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Book, Chapter, Paragraph


def fixture_source_hash(fixture_name: str, fixture_version: str, content: str) -> str:
    normalized = unicodedata.normalize("NFC", content).replace("\r\n", "\n").strip()
    payload = "\n".join((fixture_name.strip(), fixture_version.strip(), normalized))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_or_create_fixture_book(
    session: Session,
    *,
    fixture_name: str,
    fixture_version: str,
    title: str,
    paragraphs: list[str],
    source_file_name: str,
) -> tuple[Book, bool]:
    normalized_paragraphs = [unicodedata.normalize("NFC", item).strip() for item in paragraphs]
    content = "\n".join((title, *normalized_paragraphs))
    digest = fixture_source_hash(fixture_name, fixture_version, content)
    existing = session.scalar(select(Book).where(Book.source_file_hash == digest))
    if existing is not None:
        return existing, False
    book = Book(
        title=title,
        source_file_name=source_file_name,
        source_file_hash=digest,
        fixture_name=fixture_name,
        fixture_version=fixture_version,
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title=title,
        word_count=sum(len(item) for item in normalized_paragraphs),
    )
    session.add(chapter)
    session.flush()
    for index, text in enumerate(normalized_paragraphs, 1):
        paragraph_id = f"B{book.id:04d}-C0001-P{index:04d}"
        session.add(
            Paragraph(
                id=paragraph_id,
                book_id=book.id,
                chapter_id=chapter.id,
                paragraph_index=index,
                raw_text=text,
                normalized_text=text,
                char_start=0,
                char_end=len(text),
            )
        )
        chapter.start_paragraph_id = chapter.start_paragraph_id or paragraph_id
        chapter.end_paragraph_id = paragraph_id
    session.flush()
    return book, True
