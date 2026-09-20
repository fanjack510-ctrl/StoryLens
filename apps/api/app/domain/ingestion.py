import re
from dataclasses import dataclass, field
from typing import Final

from app.domain.document_structure import (
    DocumentStructure,
    HeadingCandidate,
    ParagraphRecord,
    UnitType,
    parse_document_structure,
    records_from_text,
)

NUMBER = r"[0-9０-９零〇一二三四五六七八九十百千万两]+"
CHAPTER_PATTERN = re.compile(
    rf"^\s*第\s*(?P<number>{NUMBER})\s*(?P<unit>[章回节])\s*"
    r"(?P<separator>[:：、.\-—]?)\s*(?P<title>.*?)\s*$"
)

#: Formats other than 「第N章」 that Chinese web-novel TXT dumps actually use. Measured on
#: the library: 「第N章」 alone detected 0 chapters in 碧血洗银枪, 1 in 剩女遇见爱情 and 4 in
#: 黑白道 — books of 1,763 / 4,070 / 4,387 paragraphs. A book that arrives as one giant
#: "chapter" cannot be analysed by anything downstream, so a missed format is not a cosmetic
#:問題: it silently disables the product for that book.
#:
#: Each alternative is deliberately anchored and bounded. A loose rule is worse than a
#: missing one — matching a line of prose would cut a chapter in the middle of a sentence.
ALT_CHAPTER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Chapter1 标题 / CHAPTER 12: Title  （剩女遇见爱情）
    (
        "latin",
        re.compile(
            r"^\s*(?:[Cc][Hh][Aa][Pp][Tt][Ee][Rr]|CHAPTER)\s*(?P<number>\d{1,4})\s*"
            r"(?P<separator>[:：、.\-—]?)\s*(?P<title>.*?)\s*$"
        ),
    ),
    # 12.标题 / 3、标题 — a leading ordinal with a separator, title required so that
    # 「2008.」 in prose or a bare number line does not qualify.  （黑白道）
    (
        "ordinal",
        re.compile(
            r"^\s*(?P<number>\d{1,4})\s*(?P<separator>[、.．:：])\s*(?P<title>\S.{0,60}?)\s*$"
        ),
    ),
    # 卷/部/篇 used as the only division level — accepted when nothing finer exists.
    (
        "volume",
        re.compile(
            rf"^\s*第\s*(?P<number>{NUMBER})\s*(?P<unit_alt>[卷部篇集])\s*"
            r"(?P<separator>[:：、.\-—]?)\s*(?P<title>.*?)\s*$"
        ),
    ),
    # A bare numeral alone on its line.  （一梦如初）
    #
    # Last, and the only pattern that carries an extra guard: a line that is nothing but a
    # number is also what a year, a quantity or a list item looks like, so the regex alone
    # would cut books in the middle of a sentence. The guard is `_counts_like_chapters`, and
    # without it this entry must not be enabled.
    ("bare", re.compile(r"^\s*(?P<number>\d{1,4})\s*$")),
)

#: The formats this module recognises, in the words a user would use to check their own file.
#:
#: Shown to the user when detection looks wrong, because that is the cheaper repair: the person
#: holding the file can see in one glance whether it is marked up this way, and the system
#: cannot. Measured on the library — one book arrived as 206 chapters of which one held 1.69
#: million characters, and nothing downstream could tell that from a book with a long chapter.
#:
#: Kept beside the patterns so the two cannot drift. Adding a pattern means adding a line here.
SUPPORTED_CHAPTER_FORMATS: tuple[str, ...] = (
    "第1章 标题　／　第一回　／　第1节",
    "Chapter 1 标题　／　CHAPTER 12: Title",
    "1、标题　／　12.标题",
    "第1卷　／　第1部　／　第1篇　／　第1集",
    "单独一行的数字：1  2  3 …（需连续递增，可在番外处重新计数）",
)

#: A chapter this large is not a chapter. Every layer above ingestion is sized in chapters, so
#: one oversized chapter is not a cosmetic problem — the pacing curve, the per-chapter table and
#: the act structure all collapse onto it, and the report says so about the book rather than
#: about the split.
OVERSIZED_CHAPTER_CHARS: Final[int] = 50_000

#: One chapter holding this much of the whole book means the rest were not found. Measured:
#: 《碧血洗银枪》 arrived as 2 chapters with 99.5% of the text in one of them and raised no
#: warning at all, because every criterion keyed on "one chapter or fewer".
DOMINANT_CHAPTER_SHARE: Final[float] = 0.5

#: A detection is believed only if it produces enough chapters to be a real division of the
#: book. Below this a fallback format is tried instead of shipping a one-chapter "book".
MIN_BELIEVABLE_CHAPTERS = 4
VOLUME_PATTERN = re.compile(rf"^\s*第\s*{NUMBER}\s*[卷部篇]\s*.*$")
SPECIAL_PATTERN = re.compile(
    r"^\s*(正文|正文开始|内容简介|简介|前言|序言|楔子|后记|尾声|番外(?:\s*.*)?)\s*$"
)
METADATA_PATTERN = re.compile(r"^[-—=_*·\s]{3,}章节内容开始[-—=_*·\s]{3,}$")


@dataclass(frozen=True)
class ParsedChapter:
    title: str
    paragraphs: list[str]
    unit_type: str = UnitType.CHAPTER.value
    analyzable: bool = True


ChapterCandidate = HeadingCandidate


@dataclass
class ChapterDetection:
    chapters: list[ParsedChapter]
    candidates: list[ChapterCandidate]
    rules: list[str] = field(default_factory=list)
    structure: DocumentStructure | None = None


def normalize_paragraph(text: str) -> str:
    return re.sub(r"[ \t\u3000]+", " ", text.strip())


def _number_value(value: str) -> int | None:
    value = value.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if value.isdigit():
        return int(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = section = number = 0
    for char in value:
        if char in digits:
            number = digits[char]
        elif char in units:
            unit = units[char]
            if unit == 10000:
                total += (section + number) * unit
                section = number = 0
            else:
                section += (number or 1) * unit
                number = 0
        else:
            return None
    return total + section + number


def chapter_title_metadata(source: str) -> dict[str, object]:
    match = CHAPTER_PATTERN.fullmatch(source)
    if match:
        raw, unit, title = match.group("number"), match.group("unit"), match.group("title")
        normalized = _number_value(raw)
        return {"section_type": "chapter", "chapter_number_raw": raw,
                "chapter_number_normalized": normalized, "chapter_unit": unit,
                "chapter_title": title, "display_title": f"第{raw}{unit}｜{title}" if title else f"第{raw}{unit}",
                "source_title_line": normalize_paragraph(source)}
    normalized = normalize_paragraph(source)
    compact = normalized.replace("\u3000", " ")
    if re.fullmatch(r"(?:引言|绪论)(?:\s+.*)?", compact):
        # Introduction is a first-class structural type in the parser, but maps to the
        # established analyzable chapter contract so all existing analysis pipelines include it.
        kind = "chapter"
    elif re.fullmatch(r"(?:前言|序言|中文版序|推荐序.*)", compact):
        kind = "front_matter"
    elif VOLUME_PATTERN.fullmatch(normalized):
        kind = "volume"
    elif normalized.startswith("番外"):
        kind = "extra"
    elif re.fullmatch(r"(?:后记|尾声)(?:\s+.*)?", compact):
        kind = "afterword"
    elif re.fullmatch(r"附录.*", compact):
        kind = "appendix"
    elif re.fullmatch(r"(?:注释|注解|尾注)(?:\s+.*)?", compact):
        kind = "notes"
    elif re.fullmatch(r"致谢(?:\s+.*)?", compact):
        kind = "acknowledgements"
    elif re.fullmatch(r"参考文献(?:\s+.*)?", compact):
        kind = "references"
    elif normalized == "正文":
        kind = "front_matter"
        normalized = "前置内容"
    else:
        kind = "body_fallback"
    return {"section_type": kind, "chapter_number_raw": None,
            "chapter_number_normalized": None, "chapter_unit": None,
            "chapter_title": normalized, "display_title": normalized,
            "source_title_line": source}


#: How many steps in a bare-numeral run may fail to advance before the run is disbelieved.
#: One in ten, so a single missing or duplicated marker does not disqualify a real book.
_BARE_RUN_TOLERANCE = 0.1


def _counts_like_chapters(candidates: list["ChapterCandidate"]) -> bool:
    """Do these bare numerals actually count, the way chapter markers do?

    A line holding nothing but a number is indistinguishable, by shape, from a year, a price or
    a list item. What separates a chapter marker from those is not how it looks but what it does
    next: it goes up by one. 《一梦如初》 numbers its nineteen sections 1…19 and then restarts at
    1 for 番外一, which is why a restart counts as a legal step — but only a couple of them, or
    "restart" would excuse any sequence at all.

    Without this the pattern is worse than not having it: a stray numeral would cut a chapter in
    the middle of a sentence, and the reader would have no way to tell that is what happened.
    """
    numbers = [c.number for c in candidates if c.number is not None]
    if len(numbers) < MIN_BELIEVABLE_CHAPTERS or len(numbers) != len(candidates):
        return False
    if numbers[0] > 2:
        return False
    steps = list(zip(numbers, numbers[1:]))
    restarts = sum(1 for previous, current in steps if current == 1 and previous > 1)
    if restarts > 2:
        return False
    advances = sum(1 for previous, current in steps if current == previous + 1)
    return advances + restarts >= len(steps) - max(1, int(len(steps) * _BARE_RUN_TOLERANCE))


def detect_chapters(
    text: str, *, records: list[ParagraphRecord] | tuple[ParagraphRecord, ...] | None = None
) -> ChapterDetection:
    """Parse the complete document and project its units onto the legacy chapter contract."""
    paragraph_records = list(records) if records is not None else records_from_text(text)
    structure = parse_document_structure(paragraph_records)
    chapters = [
        ParsedChapter(
            title=unit.title,
            paragraphs=unit.paragraphs,
            unit_type=unit.unit_type,
            analyzable=unit.analyzable,
        )
        for unit in structure.units
        # Keep heading-only units in the rich structure for diagnostics, but never project
        # them into the legacy Chapter table: that contract requires real paragraph anchors.
        if unit.paragraphs
    ]
    return ChapterDetection(
        chapters=chapters,
        candidates=structure.candidates,
        rules=structure.parsing_rules,
        structure=structure,
    )


def split_chapters(text: str) -> list[ParsedChapter]:
    return detect_chapters(text).chapters
