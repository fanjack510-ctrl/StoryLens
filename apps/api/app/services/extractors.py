from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document
from ebooklib import ITEM_DOCUMENT, epub

from app.domain.document_structure import ParagraphRecord, normalize_heading, records_from_text


class InvalidFileTypeError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    pass


class ScannedDocumentError(ValueError):
    """PDF 里没有文字层——是一沓图片，不是一本书。

    这一条必须单独抛，不能并进 EmptyDocumentError：两者对用户的意义完全不同。「文件里没有
    可导入的文本」听起来像文件坏了；而扫描件是好文件，只是还需要一步 OCR。把它们混成一句，
    用户会去换文件，而不是去做该做的那件事。
    """


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    encoding: str
    bom: str
    newline: str
    byte_count: int
    #: PDF 的逐页文本。专著的结构识别要靠页边界（页眉重复、章首目录），拼成一整个字符串
    #: 之后这些信息就没了。其他格式为 None。
    pages: tuple[str, ...] | None = None
    #: Paragraph-level source evidence. DOCX keeps declared styles; plain formats keep line and
    #: page positions. Structure parsing consumes this instead of flattening everything first.
    paragraphs: tuple[ParagraphRecord, ...] | None = None


def extract_text(filename: str, content: bytes) -> str:
    return extract_document(filename, content).text


def extract_document(filename: str, content: bytes) -> ExtractedDocument:
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        text, encoding, bom = _decode_txt(content)
    elif suffix == ".docx":
        docx = Document(BytesIO(content))
        raw_paragraphs = list(docx.paragraphs)
        text = "\n".join(paragraph.text for paragraph in raw_paragraphs)
        encoding, bom = "docx/xml", "none"
    elif suffix == ".epub":
        text = _extract_epub(content)
        encoding, bom = "epub/html", "none"
    elif suffix == ".pdf":
        pages = _extract_pdf_pages(content)
        text = "\n".join(pages)
        if not text.strip():
            raise ScannedDocumentError(
                "这个 PDF 没有文字层（整本是扫描图片），需要先做 OCR 才能导入。"
            )
        newline = "CRLF" if "\r\n" in text else ("CR" if "\r" in text else "LF")
        records: list[ParagraphRecord] = []
        index = 0
        for page_number, page in enumerate(pages, start=1):
            page_records = records_from_text(page, source_type="pdf")
            for record in page_records:
                records.append(ParagraphRecord(
                    **{**record.__dict__, "index": index, "page_number": page_number}
                ))
                index += 1
        return ExtractedDocument(
            text, "pdf/text", "none", newline, len(content), tuple(pages), tuple(records)
        )
    else:
        raise InvalidFileTypeError("仅支持 TXT、DOCX、EPUB、PDF")
    if not text.strip():
        raise EmptyDocumentError("文件中没有可导入的文本")
    newline = "CRLF" if "\r\n" in text else ("CR" if "\r" in text else "LF")
    if suffix == ".docx":
        records = tuple(_docx_records(raw_paragraphs))
    else:
        records = tuple(records_from_text(text, source_type=suffix.lstrip(".") or "text"))
    return ExtractedDocument(text, encoding, bom, newline, len(content), paragraphs=records)


def _docx_records(paragraphs: list) -> list[ParagraphRecord]:
    """Keep Word paragraph structure without guessing headings from font size alone."""
    records: list[ParagraphRecord] = []
    for index, paragraph in enumerate(paragraphs):
        raw = paragraph.text or ""
        normalized = normalize_heading(raw)
        style_name = getattr(getattr(paragraph, "style", None), "name", "") or None
        outline_level = None
        ppr = getattr(getattr(paragraph, "_p", None), "pPr", None)
        outline = getattr(ppr, "outlineLvl", None) if ppr is not None else None
        if outline is not None:
            try:
                outline_level = int(outline.val)
            except (TypeError, ValueError):
                outline_level = None
        sizes = [
            float(run.font.size.pt)
            for run in paragraph.runs
            if getattr(run.font, "size", None) is not None
        ]
        bold_values = [run.bold for run in paragraph.runs if run.text and run.bold is not None]
        alignment = str(paragraph.alignment) if paragraph.alignment is not None else None
        records.append(ParagraphRecord(
            index=index,
            raw_text=raw,
            normalized_text=normalized,
            source_type="docx",
            style_name=style_name,
            outline_level=outline_level,
            font_size=max(sizes) if sizes else None,
            bold=all(bold_values) if bold_values else None,
            alignment=alignment,
            line_count=max(1, raw.count("\n") + 1),
            char_count=len(normalized),
            preceding_blank=index == 0 or not (paragraphs[index - 1].text or "").strip(),
            following_blank=index == len(paragraphs) - 1 or not (paragraphs[index + 1].text or "").strip(),
        ))
    return records


def _extract_pdf_pages(content: bytes) -> list[str]:
    """逐页取文字。页边界要留着——专著的结构就藏在页眉和章首目录里，
    拼成一整个字符串之后就再也分不出来了。"""
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:  # noqa: BLE001 — pypdf 的异常层次很杂，一律翻译成人话
        # 后缀是 .pdf 不等于内容是 PDF。不接住这里，用户拿到的是
        # `PdfStreamError: Stream has ended unexpectedly` —— 一句他无从下手的话。
        raise InvalidFileTypeError("这个文件不是有效的 PDF，或者已经损坏") from exc
    out: list[str] = []
    for page in reader.pages:
        try:
            out.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 — 单页解析失败不该让整本书都导不进来
            out.append("")
    return out


def _decode_txt(content: bytes) -> tuple[str, str, str]:
    bom_candidates = (
        (b"\xef\xbb\xbf", "utf-8-sig", "UTF-8"),
        (b"\xff\xfe", "utf-16-le", "UTF-16-LE"),
        (b"\xfe\xff", "utf-16-be", "UTF-16-BE"),
    )
    for marker, encoding, label in bom_candidates:
        if content.startswith(marker):
            text = content.decode(encoding)
            return text.lstrip("\ufeff"), encoding, label
    if b"\x00" in content[:4096]:
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                text = content.decode(encoding)
                if text.count("\ufffd") == 0:
                    return text.lstrip("\ufeff"), encoding, "none"
            except UnicodeDecodeError:
                continue
    for encoding in ("utf-8", "gb18030"):
        try:
            text = content.decode(encoding)
            if "\ufffd" in text:
                continue
            return text, encoding, "none"
        except UnicodeDecodeError:
            continue
    raise ValueError("TXT 文件编码无法可靠识别，请转换为 UTF-8、GB18030 或 UTF-16")


def _extract_epub(content: bytes) -> str:
    book = epub.read_epub(BytesIO(content))
    sections: list[str] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        # EbookLib exposes the generated EPUB navigation page as ITEM_DOCUMENT too. Its
        # link labels repeat chapter headings without body text. Navigation is metadata,
        # not readable book content.
        if isinstance(item, epub.EpubNav):
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        sections.append(soup.get_text("\n"))
    return "\n".join(sections)
