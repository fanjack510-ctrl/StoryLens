import hashlib
import json
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.narrative_core.short_form.dispatch import (
    SHORT_FORM_HARD_MAX_CHARS,
    is_short_form,
    short_form_allowed,
)
from app.db.models import AnalysisRun, Book, Chapter, Paragraph, ReparseAudit
from app.domain.ingestion import (
    DOMINANT_CHAPTER_SHARE,
    OVERSIZED_CHAPTER_CHARS,
    SUPPORTED_CHAPTER_FORMATS,
    ChapterDetection,
    chapter_title_metadata,
    detect_chapters,
)
from app.services.extractors import ExtractedDocument, extract_document


class DuplicateBookError(ValueError):
    pass


class ReparseProtectedError(ValueError):
    pass


def _diagnostics(document: ExtractedDocument, detection: ChapterDetection) -> dict[str, object]:
    lines = document.text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chapters = detection.chapters
    maximum_chars = max((sum(map(len, item.paragraphs)) for item in chapters), default=0)
    maximum_paragraphs = max((len(item.paragraphs) for item in chapters), default=0)
    # Why it looks wrong, not just that it does. The import screen shows these to the user
    # along with the formats we recognise, because the person holding the file can tell in one
    # glance whether it is marked up that way and this code cannot.
    total_chars = sum(sum(map(len, item.paragraphs)) for item in chapters)
    dominant_share = (maximum_chars / total_chars) if total_chars else 0.0
    suspect_reasons: list[str] = []
    if len(chapters) <= 1:
        suspect_reasons.append("SINGLE_CHAPTER")
    if maximum_chars > OVERSIZED_CHAPTER_CHARS:
        suspect_reasons.append("OVERSIZED_CHAPTER")
    if len(chapters) > 1 and dominant_share > DOMINANT_CHAPTER_SHARE:
        # 《碧血洗银枪》 arrived as two chapters with 99.5% of the book in one of them and raised
        # no warning, because every earlier rule keyed on "one chapter or fewer".
        suspect_reasons.append("ONE_CHAPTER_DOMINATES")
    if maximum_paragraphs > 2_000:
        suspect_reasons.append("CHAPTER_TOO_MANY_PARAGRAPHS")
    if len(detection.candidates) >= 5 and len(chapters) <= 1:
        suspect_reasons.append("MARKERS_FOUND_BUT_NOT_ADOPTED")
    suspect = bool(suspect_reasons)
    adopted = [item for item in detection.candidates if item.adopted]
    rejected = [item for item in detection.candidates if not item.adopted]
    numbers = [item.number for item in adopted if item.number is not None]
    repeated = len(numbers) - len(set(numbers))
    jumps = sum(b > a + 1 for a, b in zip(numbers, numbers[1:]))
    reversed_count = sum(b < a for a, b in zip(numbers, numbers[1:]))
    formats = [item.format_key for item in adopted]
    front_matter = chapters[:1] if chapters and chapters[0].title == "正文" else []
    reason_counts: dict[str, int] = {}
    for item in rejected:
        reason = item.rejection_reason or "low_score"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "encoding": document.encoding,
        "bom": document.bom,
        "newline": document.newline,
        "byte_count": document.byte_count,
        "character_count": len(document.text),
        "total_lines": len(lines),
        "non_empty_lines": sum(bool(line.strip()) for line in lines),
        "candidate_count": len(detection.candidates),
        "adopted_candidate_count": len(adopted),
        "rejected_candidate_count": len(rejected),
        "rejection_reason_counts": reason_counts,
        "duplicate_number_count": repeated,
        "numbering_jump_count": jumps,
        "numbering_reverse_count": reversed_count,
        "format_change_lines": [adopted[i].line_number for i in range(1, len(adopted)) if formats[i] != formats[i - 1]][:100],
        "suspicious_ad_title_count": sum("下载" in item.text or "网址" in item.text for item in rejected),
        "front_matter_count": len(front_matter),
        "front_matter_paragraph_count": sum(len(item.paragraphs) for item in front_matter),
        "final_chapter_count": len(chapters),
        "rules": detection.rules,
        "single_chapter_fallback": len(chapters) == 1 and chapters[0].title == "正文",
        "max_chapter_characters": maximum_chars,
        "max_chapter_paragraphs": maximum_paragraphs,
        # Which pipeline this file looks like it wants. Offered as the import panel's default
        # answer, not as the decision — the person holding the file overrides it with one
        # click, and their answer is what gets stored. Computed here so the rule has one home.
        "suggested_analysis_form": (
            "short"
            if is_short_form(character_count=total_chars, chapter_count=len(chapters))
            else "long"
        ),
        # Whether 短篇 may be picked for this file at all, decided before it is imported so
        # the panel never offers an option the import would drop.
        "short_form_allowed": short_form_allowed(total_chars),
        "hard_max_chars": SHORT_FORM_HARD_MAX_CHARS,
        "warning": "CHAPTER_DETECTION_SUSPECT" if suspect else None,
        "suspect_reasons": suspect_reasons,
        "max_chapter_share": round(dominant_share, 4),
        "supported_chapter_formats": list(SUPPORTED_CHAPTER_FORMATS),
        "recommended_to_import": not suspect,
        "chapter_titles": [item.title for item in chapters[:20]],
        "unadopted_candidates": [item.public() for item in rejected[:200]],
        "candidates": [item.public() for item in detection.candidates[:200]],
    }


def preview_book(filename: str, content: bytes) -> tuple[ExtractedDocument, ChapterDetection, dict[str, object]]:
    document = extract_document(filename, content)
    detection = detect_chapters(document.text)
    if not detection.chapters:
        raise ValueError("未找到可导入的段落")
    return document, detection, _diagnostics(document, detection)


def _write_chapters(session: Session, book: Book, detection: ChapterDetection) -> None:
    absolute_offset = 0
    for chapter_index, parsed in enumerate(detection.chapters, start=1):
        metadata = chapter_title_metadata(parsed.title)
        chapter = Chapter(book_id=book.id, chapter_index=chapter_index, title=parsed.title,
                          word_count=sum(len(item) for item in parsed.paragraphs), **metadata)
        session.add(chapter)
        session.flush()
        ids: list[str] = []
        for paragraph_index, raw_text in enumerate(parsed.paragraphs, start=1):
            paragraph_id = f"B{book.id:04d}-C{chapter_index:04d}-P{paragraph_index:04d}"
            ids.append(paragraph_id)
            session.add(Paragraph(id=paragraph_id, book_id=book.id, chapter_id=chapter.id,
                                  paragraph_index=paragraph_index, raw_text=raw_text,
                                  normalized_text=raw_text, char_start=absolute_offset,
                                  char_end=absolute_offset + len(raw_text)))
            absolute_offset += len(raw_text) + 1
        chapter.start_paragraph_id, chapter.end_paragraph_id = ids[0], ids[-1]


def import_book(session: Session, filename: str, content: bytes) -> Book:
    digest = hashlib.sha256(content).hexdigest()
    if session.scalar(select(Book).where(Book.source_file_hash == digest)):
        raise DuplicateBookError("该文件已导入")
    _, detection, diagnostics = preview_book(filename, content)
    book = Book(title=Path(filename).stem, source_file_name=filename, source_file_hash=digest,
                import_status="imported", source_content=content,
                import_diagnostics_json=json.dumps(diagnostics, ensure_ascii=False),
                import_warning=diagnostics["warning"])
    session.add(book)
    session.flush()
    _write_chapters(session, book, detection)
    session.commit()
    session.refresh(book)
    return book


def reparse_preview(session: Session, book: Book) -> dict[str, object]:
    if not book.source_content:
        raise ValueError("旧导入记录没有保存源文件，请通过章节识别预览重新选择原文件")
    _, _, diagnostics = preview_book(book.source_file_name, book.source_content)
    diagnostics["old_chapter_count"] = session.scalar(
        select(func.count()).select_from(Chapter).where(Chapter.book_id == book.id)
    ) or 0
    return diagnostics


def reparse_book(session: Session, book: Book) -> dict[str, object]:
    chapter_ids = list(session.scalars(select(Chapter.id).where(Chapter.book_id == book.id)))
    succeeded = session.scalar(select(AnalysisRun.id).where(
        AnalysisRun.subject_id.in_([str(item) for item in chapter_ids]), AnalysisRun.status == "succeeded"
    ))
    if succeeded:
        raise ReparseProtectedError("书籍存在成功分析历史，禁止破坏性重新识别")
    if not book.source_content:
        raise ValueError("旧导入记录没有保存源文件")
    _, detection, diagnostics = preview_book(book.source_file_name, book.source_content)
    try:
        session.execute(delete(AnalysisRun).where(
            AnalysisRun.subject_id.in_([str(item) for item in chapter_ids])
        ))
        session.execute(delete(Chapter).where(Chapter.book_id == book.id))
        session.flush()
        _write_chapters(session, book, detection)
        book.import_diagnostics_json = json.dumps(diagnostics, ensure_ascii=False)
        book.import_warning = diagnostics["warning"]
        session.commit()
    except Exception:
        session.rollback()
        raise
    return diagnostics


def reparse_with_file_preview(session: Session, book: Book, filename: str, content: bytes) -> dict[str, object]:
    _, detection, diagnostics = preview_book(filename, content)
    old_chapters = session.scalar(select(func.count()).select_from(Chapter).where(Chapter.book_id == book.id)) or 0
    old_paragraphs = session.scalar(select(func.count()).select_from(Paragraph).where(Paragraph.book_id == book.id)) or 0
    new_hash = hashlib.sha256(content).hexdigest()
    chapter_ids = list(session.scalars(select(Chapter.id).where(Chapter.book_id == book.id)))
    has_success = session.scalar(select(AnalysisRun.id).where(
        AnalysisRun.subject_id.in_([str(item) for item in chapter_ids]), AnalysisRun.status == "succeeded")) is not None
    titles = [chapter_title_metadata(item.title)["display_title"] for item in detection.chapters]
    formal = [item for item in detection.chapters if chapter_title_metadata(item.title)["section_type"] == "chapter"]
    result = dict(diagnostics)
    result.update({"book_id": book.id, "original_file_hash": book.source_file_hash,
                   "uploaded_file_hash": new_hash, "hash_match": new_hash == book.source_file_hash,
                   "old_chapter_count": old_chapters, "new_chapter_count": len(detection.chapters),
                   "old_paragraph_count": old_paragraphs,
                   "new_paragraph_count": sum(len(item.paragraphs) for item in detection.chapters),
                   "has_succeeded_runs": has_success,
                   "formal_chapter_count": len(formal), "front_matter_count": int(bool(detection.chapters and detection.chapters[0].title == "正文")),
                   "chapter_titles": titles[:20], "middle_sample_titles": titles[max(0, len(titles)//2-2):len(titles)//2+3],
                   "ending_sample_titles": titles[-10:],
                   "recommended_action": "replace_in_place" if new_hash == book.source_file_hash else "create_revision"})
    return result


def reparse_with_file(session: Session, book: Book, filename: str, content: bytes, strategy: str,
                      confirm_different_file: bool = False) -> Book:
    preview = reparse_with_file_preview(session, book, filename, content)
    new_hash = str(preview["uploaded_file_hash"])
    chapter_ids = list(session.scalars(select(Chapter.id).where(Chapter.book_id == book.id)))
    has_success = session.scalar(select(AnalysisRun.id).where(
        AnalysisRun.subject_id.in_([str(item) for item in chapter_ids]), AnalysisRun.status == "succeeded")) is not None
    if strategy == "replace_in_place":
        if has_success:
            raise ReparseProtectedError("书籍存在成功分析历史，只能创建修订版")
        if new_hash != book.source_file_hash and not confirm_different_file:
            raise ValueError("上传文件Hash不同，需要二次确认")
        _, detection, diagnostics = preview_book(filename, content)
        try:
            session.execute(delete(AnalysisRun).where(AnalysisRun.subject_id.in_([str(item) for item in chapter_ids])))
            session.execute(delete(Chapter).where(Chapter.book_id == book.id))
            session.flush()
            old_hash = book.source_file_hash
            book.source_file_hash, book.source_file_name, book.source_content = new_hash, filename, content
            book.import_diagnostics_json = json.dumps(diagnostics, ensure_ascii=False)
            _write_chapters(session, book, detection)
            session.add(ReparseAudit(book_id=book.id, strategy=strategy,
                                     old_chapter_count=int(preview["old_chapter_count"]), new_chapter_count=len(detection.chapters),
                                     old_file_hash=old_hash, new_file_hash=new_hash, parsing_rule_version="numbered-scored-v2"))
            session.commit()
            return book
        except Exception:
            session.rollback()
            raise
    if strategy != "create_revision":
        raise ValueError("不支持的重解析策略")
    _, detection, diagnostics = preview_book(filename, content)
    stored_hash = new_hash if new_hash != book.source_file_hash else hashlib.sha256(f"{new_hash}:revision:{book.id}:{book.revision_number + 1}".encode()).hexdigest()
    revision = Book(title=f"{book.title}（修订版）", source_file_name=filename, source_file_hash=stored_hash,
                    import_status="imported", source_content=content,
                    import_diagnostics_json=json.dumps(diagnostics, ensure_ascii=False),
                    import_warning=diagnostics["warning"], revision_of_book_id=book.id,
                    revision_number=book.revision_number + 1)
    session.add(revision)
    session.flush()
    _write_chapters(session, revision, detection)
    session.add(ReparseAudit(book_id=revision.id, strategy=strategy,
                             old_chapter_count=int(preview["old_chapter_count"]), new_chapter_count=len(detection.chapters),
                             old_file_hash=book.source_file_hash, new_file_hash=new_hash, parsing_rule_version="numbered-scored-v2"))
    session.commit()
    return revision
