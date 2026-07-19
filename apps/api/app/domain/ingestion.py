import re
from dataclasses import asdict, dataclass, field


NUMBER = r"[0-9０-９零〇一二三四五六七八九十百千万两]+"
CHAPTER_PATTERN = re.compile(
    rf"^\s*第\s*(?P<number>{NUMBER})\s*(?P<unit>[章回节])\s*"
    r"(?P<separator>[:：、.\-—]?)\s*(?P<title>.*?)\s*$"
)
VOLUME_PATTERN = re.compile(rf"^\s*第\s*{NUMBER}\s*[卷部篇]\s*.*$")
SPECIAL_PATTERN = re.compile(
    r"^\s*(正文|正文开始|内容简介|简介|前言|序言|楔子|后记|尾声|番外(?:\s*.*)?)\s*$"
)
METADATA_PATTERN = re.compile(r"^[-—=_*·\s]{3,}章节内容开始[-—=_*·\s]{3,}$")


@dataclass(frozen=True)
class ParsedChapter:
    title: str
    paragraphs: list[str]


@dataclass
class ChapterCandidate:
    line_number: int
    text: str
    number_text: str | None
    number: int | None
    unit: str
    title: str
    preceding_blank: bool
    following_blank: bool
    starts_at_line_start: bool
    format_key: str
    score: int = 0
    adopted: bool = False
    rejection_reason: str | None = None

    def public(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ChapterDetection:
    chapters: list[ParsedChapter]
    candidates: list[ChapterCandidate]
    rules: list[str] = field(default_factory=list)


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
    if VOLUME_PATTERN.fullmatch(normalized):
        kind = "volume"
    elif normalized.startswith("番外"):
        kind = "extra"
    elif normalized in {"后记", "尾声"}:
        kind = "afterword"
    elif normalized == "正文":
        kind = "front_matter"
        normalized = "前置内容"
    else:
        kind = "body_fallback"
    return {"section_type": kind, "chapter_number_raw": None,
            "chapter_number_normalized": None, "chapter_unit": None,
            "chapter_title": normalized, "display_title": normalized,
            "source_title_line": source}


def detect_chapters(text: str) -> ChapterDetection:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    candidates: list[ChapterCandidate] = []
    for index, raw in enumerate(lines):
        normalized = normalize_paragraph(raw)
        if not normalized or len(normalized) > 120:
            continue
        match = CHAPTER_PATTERN.fullmatch(raw)
        if not match:
            continue
        separator = match.group("separator")
        title = match.group("title")
        candidates.append(
            ChapterCandidate(
                line_number=index + 1,
                text=normalized,
                number_text=match.group("number"),
                number=_number_value(match.group("number")),
                unit=match.group("unit"),
                title=title,
                preceding_blank=index == 0 or not lines[index - 1].strip(),
                following_blank=index == len(lines) - 1 or not lines[index + 1].strip(),
                starts_at_line_start=not raw[:1].isspace(),
                format_key=f"numbered:{match.group('unit')}:{bool(separator)}",
            )
        )

    formats: dict[str, int] = {}
    for item in candidates:
        formats[item.format_key] = formats.get(item.format_key, 0) + 1
    previous_number: int | None = None
    for item in candidates:
        score = 3
        score += int(item.starts_at_line_start)
        score += int(item.preceding_blank) + int(item.following_blank)
        score += 2 if formats[item.format_key] >= 2 else 0
        if previous_number is None or item.number in {previous_number, previous_number + 1}:
            score += 2
        if not item.title:
            score += 1
        item.score = score
        item.adopted = score >= 6 and (len(candidates) >= 2 or item.preceding_blank or item.following_blank)
        if item.adopted:
            previous_number = item.number
        else:
            item.rejection_reason = "候选孤立且缺少章节结构上下文"

    candidate_by_line = {item.line_number: item for item in candidates if item.adopted}
    chapters: list[ParsedChapter] = []
    title = "正文"
    paragraphs: list[str] = []

    def flush() -> None:
        nonlocal paragraphs
        if paragraphs:
            chapters.append(ParsedChapter(title=title, paragraphs=paragraphs))
            paragraphs = []

    for index, raw in enumerate(lines, start=1):
        normalized = normalize_paragraph(raw)
        if not normalized:
            continue
        if METADATA_PATTERN.fullmatch(normalized):
            continue
        candidate = candidate_by_line.get(index)
        is_special = bool(SPECIAL_PATTERN.fullmatch(normalized) or VOLUME_PATTERN.fullmatch(normalized))
        if candidate or (is_special and len(normalized) <= 120):
            flush()
            title = normalized
        else:
            paragraphs.append(normalized)
    flush()
    return ChapterDetection(
        chapters=chapters,
        candidates=candidates,
        rules=["numbered-scored-v2", "special-section-v1", "metadata-boundary-filter-v1"],
    )


def split_chapters(text: str) -> list[ParsedChapter]:
    return detect_chapters(text).chapters
