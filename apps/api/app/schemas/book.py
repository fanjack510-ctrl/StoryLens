from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: str | None
    source_file_name: str
    source_file_hash: str
    import_status: str
    language: str
    created_at: datetime
    revision_of_book_id: int | None
    revision_number: int


class ChapterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    chapter_index: int
    title: str
    start_paragraph_id: str | None
    end_paragraph_id: str | None
    word_count: int
    section_type: str
    chapter_number_raw: str | None
    chapter_number_normalized: int | None
    chapter_unit: str | None
    chapter_title: str
    display_title: str
    source_title_line: str


class ParagraphResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    book_id: int
    chapter_id: int
    paragraph_index: int
    raw_text: str
    normalized_text: str
    char_start: int
    char_end: int
    source_page: int | None


class ImportResponse(BaseModel):
    book_id: int
    status: str
    chapter_count: int
    paragraph_count: int
    warning: str | None = None


class ParagraphPage(BaseModel):
    items: list[ParagraphResponse]
    offset: int
    limit: int
    total: int
    has_more: bool


class ReparseConfirm(BaseModel):
    confirm: bool = False


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict[str, str] = Field(default_factory=dict)
