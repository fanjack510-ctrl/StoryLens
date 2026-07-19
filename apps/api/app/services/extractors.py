from io import BytesIO
from pathlib import Path
from dataclasses import dataclass

from bs4 import BeautifulSoup
from docx import Document
from ebooklib import ITEM_DOCUMENT, epub


class InvalidFileTypeError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    encoding: str
    bom: str
    newline: str
    byte_count: int


def extract_text(filename: str, content: bytes) -> str:
    return extract_document(filename, content).text


def extract_document(filename: str, content: bytes) -> ExtractedDocument:
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        text, encoding, bom = _decode_txt(content)
    elif suffix == ".docx":
        text = "\n".join(paragraph.text for paragraph in Document(BytesIO(content)).paragraphs)
        encoding, bom = "docx/xml", "none"
    elif suffix == ".epub":
        text = _extract_epub(content)
        encoding, bom = "epub/html", "none"
    else:
        raise InvalidFileTypeError("仅支持 TXT、DOCX、EPUB")
    if not text.strip():
        raise EmptyDocumentError("文件中没有可导入的文本")
    newline = "CRLF" if "\r\n" in text else ("CR" if "\r" in text else "LF")
    return ExtractedDocument(text, encoding, bom, newline, len(content))


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
        soup = BeautifulSoup(item.get_content(), "html.parser")
        sections.append(soup.get_text("\n"))
    return "\n".join(sections)
