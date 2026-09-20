"""Whole-document structure parsing for imported books.

The parser deliberately keeps heading *candidates* separate from accepted unit boundaries.
A line can look exactly like ``第 3 章`` and still be a table-of-contents entry; only the
document-level evidence (style, duplicate occurrence, density and numbering sequence) decides
whether it becomes a boundary.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from itertools import pairwise

NUMBER = r"[0-9０-９零〇一二三四五六七八九十百千万两]+"
_HEADING_STYLE = re.compile(r"^(?:(?:Heading|标题)\s*\d*|章节标题|Title)$", re.IGNORECASE)
_FIGURE_TABLE = re.compile(r"^(?:图|表)\s*\d+(?:[-－.]\d+)+")
_NUMBERED = re.compile(
    rf"^第\s*(?P<number>{NUMBER})\s*(?P<unit>章|回|节)\s*"
    r"(?P<separator>[:：、.．\-—]?)\s*(?P<title>.*)$"
)
_NUMBERED_SECTION = re.compile(
    rf"^第\s*(?P<number>{NUMBER})\s*(?P<unit>卷|部|篇|集|编)\s*"
    r"(?P<separator>[:：、.．\-—]?)\s*(?P<title>.*)$"
)
_ENGLISH = re.compile(
    r"^(?:CHAPTER|Chapter)\s*(?P<number>\d{1,4}|[IVXLC]+)\s*"
    r"(?P<separator>[:：、.．\-—]?)\s*(?P<title>.*)$"
)
_ORDINAL = re.compile(r"^(?P<number>\d{1,4})\s*(?P<separator>[、.．:：])\s*(?P<title>\S.{0,80})$")
_BARE_NUMBER = re.compile(r"^(?P<number>\d{1,4})$")
_METADATA_BOUNDARY = re.compile(r"^[-—=_*·\s]{3,}章节内容开始[-—=_*·\s]{3,}$")
_SPECIAL: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:引言|绪论|Introduction)(?:[\s　:：]+.*)?$", re.IGNORECASE), "INTRODUCTION"),
    (re.compile(r"^(?:前言|序言|中文版序|推荐序(?:[一二三四五六七八九十0-9]+)?)(?:[\s　:：]+.*)?$"), "PREFACE"),
    (re.compile(r"^(?:后\s*记|尾声|结语)(?:[\s　:：]+.*)?$"), "AFTERWORD"),
    (re.compile(r"^(?:附录|Appendix)(?:[A-ZＡ-Ｚ0-9一二三四五六七八九十]+)?(?:[\s　:：]+.*)?$", re.IGNORECASE), "APPENDIX"),
    (re.compile(r"^(?:注释|注解|尾注|Notes)(?:[\s　:：]+.*)?$", re.IGNORECASE), "NOTES"),
    (re.compile(r"^(?:致谢|Acknowledgements?)(?:[\s　:：]+.*)?$", re.IGNORECASE), "ACKNOWLEDGEMENTS"),
    (re.compile(r"^(?:参考文献|References?)(?:[\s　:：]+.*)?$", re.IGNORECASE), "REFERENCES"),
)


class HeadingType(StrEnum):
    NUMBERED_CHAPTER = "NUMBERED_CHAPTER"
    ENGLISH_CHAPTER = "ENGLISH_CHAPTER"
    NUMBERED_SECTION = "NUMBERED_SECTION"
    INTRODUCTION = "INTRODUCTION"
    PREFACE = "PREFACE"
    AFTERWORD = "AFTERWORD"
    APPENDIX = "APPENDIX"
    NOTES = "NOTES"
    ACKNOWLEDGEMENTS = "ACKNOWLEDGEMENTS"
    REFERENCES = "REFERENCES"
    OTHER = "OTHER"


class UnitType(StrEnum):
    FRONTMATTER = "FRONTMATTER"
    INTRODUCTION = "INTRODUCTION"
    CHAPTER = "CHAPTER"
    AFTERWORD = "AFTERWORD"
    APPENDIX = "APPENDIX"
    NOTES = "NOTES"
    ACKNOWLEDGEMENTS = "ACKNOWLEDGEMENTS"
    REFERENCES = "REFERENCES"


ANALYZABLE_UNIT_TYPES = frozenset({UnitType.INTRODUCTION, UnitType.CHAPTER, UnitType.AFTERWORD})


@dataclass(frozen=True)
class ParagraphRecord:
    index: int
    raw_text: str
    normalized_text: str
    source_type: str = "text"
    page_number: int | None = None
    style_name: str | None = None
    outline_level: int | None = None
    font_size: float | None = None
    bold: bool | None = None
    alignment: str | None = None
    line_count: int = 1
    char_count: int = 0
    preceding_blank: bool = False
    following_blank: bool = False


@dataclass
class HeadingCandidate:
    paragraph_index: int
    raw_text: str
    normalized_text: str
    heading_type: str
    chapter_number_raw: str | None = None
    chapter_number_normalized: int | None = None
    title_text: str = ""
    style_signal: bool = False
    position_score: float = 0.0
    sequence_score: float = 0.0
    toc_score: float = 0.0
    confidence: float = 0.0
    is_toc_candidate: bool = False
    is_body_candidate: bool = False
    rejection_reason: str | None = None
    flags: list[str] = field(default_factory=list)

    # Compatibility with the diagnostics contract used since 1.2.x.
    @property
    def line_number(self) -> int:
        return self.paragraph_index + 1

    @property
    def text(self) -> str:
        return self.normalized_text

    @property
    def number_text(self) -> str | None:
        return self.chapter_number_raw

    @property
    def number(self) -> int | None:
        return self.chapter_number_normalized

    @property
    def unit(self) -> str:
        match = _NUMBERED.fullmatch(self.normalized_text) or _NUMBERED_SECTION.fullmatch(self.normalized_text)
        return str(match.group("unit")) if match else self.heading_type.lower()

    @property
    def title(self) -> str:
        return self.title_text

    @property
    def preceding_blank(self) -> bool:
        return "preceding_blank" in self.flags

    @property
    def following_blank(self) -> bool:
        return "following_blank" in self.flags

    @property
    def starts_at_line_start(self) -> bool:
        return True

    @property
    def format_key(self) -> str:
        return self.heading_type.lower()

    @property
    def score(self) -> int:
        return round(self.confidence * 10)

    @property
    def adopted(self) -> bool:
        return self.is_body_candidate and not self.is_toc_candidate

    def public(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "paragraph_index": self.paragraph_index,
            "text": self.text,
            "number_text": self.number_text,
            "number": self.number,
            "unit": self.unit,
            "title": self.title,
            "format_key": self.format_key,
            "score": self.score,
            "adopted": self.adopted,
            "heading_type": self.heading_type,
            "style_signal": self.style_signal,
            "position_score": self.position_score,
            "sequence_score": self.sequence_score,
            "toc_score": self.toc_score,
            "confidence": self.confidence,
            "is_toc_candidate": self.is_toc_candidate,
            "is_body_candidate": self.is_body_candidate,
            "rejection_reason": self.rejection_reason,
            "flags": list(self.flags),
        }


@dataclass(frozen=True)
class TocRegion:
    start_index: int
    end_index: int
    explicit: bool
    reason: str


@dataclass
class StructureUnit:
    unit_type: str
    title: str
    paragraphs: list[str]
    start_index: int
    end_index: int
    source_heading_index: int | None
    analyzable: bool
    confidence: float
    id: str = ""
    ordinal: int = 0
    chapter_number: int | None = None
    start_page: int | None = None
    end_page: int | None = None
    char_count: int = 0
    detection_source: tuple[str, ...] = ()


@dataclass
class DocumentStructure:
    units: list[StructureUnit]
    candidates: list[HeadingCandidate]
    toc_regions: list[TocRegion]
    warnings: list[str]
    confidence: float
    parsing_rules: list[str]

    @property
    def analyzable_units(self) -> list[StructureUnit]:
        return [unit for unit in self.units if unit.analyzable]


def normalize_heading(text: str) -> str:
    text = text.strip().replace("\u3000", " ")
    return re.sub(r"\s+", " ", text)


def _number_value(value: str | None) -> int | None:
    if not value:
        return None
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


def records_from_text(text: str, *, source_type: str = "text") -> list[ParagraphRecord]:
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    records: list[ParagraphRecord] = []
    for index, raw in enumerate(raw_lines):
        normalized = normalize_heading(raw)
        records.append(
            ParagraphRecord(
                index=index,
                raw_text=raw,
                normalized_text=normalized,
                source_type=source_type,
                line_count=max(1, raw.count("\n") + 1),
                char_count=len(normalized),
                preceding_blank=index == 0 or not raw_lines[index - 1].strip(),
                following_blank=index == len(raw_lines) - 1 or not raw_lines[index + 1].strip(),
            )
        )
    return records


def _candidate(record: ParagraphRecord) -> HeadingCandidate | None:
    text = record.normalized_text
    if not text or len(text) > 120 or _FIGURE_TABLE.match(text):
        return None
    match = _NUMBERED.fullmatch(text)
    heading_type = HeadingType.NUMBERED_CHAPTER
    if not match:
        match = _ENGLISH.fullmatch(text)
        heading_type = HeadingType.ENGLISH_CHAPTER
    if not match:
        match = _NUMBERED_SECTION.fullmatch(text)
        heading_type = HeadingType.NUMBERED_SECTION
    if not match:
        match = _ORDINAL.fullmatch(text)
        heading_type = HeadingType.NUMBERED_SECTION
        if match and (len(text) > 60 or text.endswith(("。", "！", "？", ".", "!", "?", "；", ";"))):
            # A numbered claim or list item is prose. Compatibility with ``1. 标题`` is kept,
            # but sentence-shaped enumerations never become book boundaries.
            match = None
    if not match:
        match = _BARE_NUMBER.fullmatch(text)
        heading_type = HeadingType.NUMBERED_SECTION

    number_raw: str | None = None
    title = ""
    if match:
        number_raw = match.groupdict().get("number")
        title = (match.groupdict().get("title") or "").strip()
    else:
        heading_type = HeadingType.OTHER
        for pattern, kind in _SPECIAL:
            if pattern.fullmatch(text):
                heading_type = HeadingType(kind)
                title = text
                break
        if heading_type == HeadingType.OTHER and not (
            record.style_name and _HEADING_STYLE.search(record.style_name)
        ):
            return None
        title = text

    style_signal = bool(record.style_name and _HEADING_STYLE.search(record.style_name))
    flags: list[str] = []
    if record.preceding_blank:
        flags.append("preceding_blank")
    if record.following_blank:
        flags.append("following_blank")
    if style_signal:
        flags.append("declared_heading_style")
    if record.style_name and record.style_name.casefold() == "title":
        flags.append("document_title_style")
    confidence = 0.38
    if style_signal:
        confidence += 0.42
    if heading_type in {
        HeadingType.NUMBERED_CHAPTER,
        HeadingType.ENGLISH_CHAPTER,
        HeadingType.INTRODUCTION,
        HeadingType.AFTERWORD,
        HeadingType.APPENDIX,
        HeadingType.NOTES,
        HeadingType.ACKNOWLEDGEMENTS,
        HeadingType.REFERENCES,
    }:
        confidence += 0.12
    if record.preceding_blank or record.following_blank:
        confidence += 0.05
    return HeadingCandidate(
        paragraph_index=record.index,
        raw_text=record.raw_text,
        normalized_text=text,
        heading_type=heading_type.value,
        chapter_number_raw=number_raw,
        chapter_number_normalized=_number_value(number_raw),
        title_text=title,
        style_signal=style_signal,
        position_score=0.05 if record.index < 50 else 0.0,
        confidence=min(1.0, confidence),
        flags=flags,
    )


def _sequence_quality(items: list[HeadingCandidate]) -> float:
    numbers = [item.chapter_number_normalized for item in items if item.chapter_number_normalized is not None]
    if len(numbers) < 2:
        return 0.0
    good = sum(current == previous + 1 for previous, current in pairwise(numbers))
    return good / max(1, len(numbers) - 1)


def _mark_toc(records: list[ParagraphRecord], candidates: list[HeadingCandidate]) -> list[TocRegion]:
    regions: list[TocRegion] = []
    by_index = {item.paragraph_index: item for item in candidates}

    # Explicit 目录/目次: stop at the first declared heading or sustained prose.
    for record in records:
        if re.sub(r"\s+", "", record.normalized_text) not in {"目录", "目次"}:
            continue
        end = record.index
        prose_run = 0
        seen_numbers: list[int] = []
        seen_headings: set[str] = set()
        for follow in records[record.index + 1:]:
            candidate = by_index.get(follow.index)
            if candidate and candidate.style_signal:
                break
            if candidate:
                heading_key = normalize_heading(candidate.normalized_text).casefold()
                if heading_key in seen_headings and len(seen_headings) >= 4:
                    break
                number = candidate.chapter_number_normalized
                if number == 1 and seen_numbers and seen_numbers[-1] > 1 and len(seen_numbers) >= 4:
                    break
                end = follow.index
                seen_headings.add(heading_key)
                if number is not None:
                    seen_numbers.append(number)
                prose_run = 0
                continue
            if not follow.normalized_text:
                continue
            if follow.char_count > 120:
                prose_run += 1
            else:
                prose_run = 0
            if prose_run >= 2:
                break
            end = follow.index
        if end > record.index:
            regions.append(TocRegion(record.index, end, True, "explicit_toc_heading"))

    # Implicit TOC: a dense, mostly sequential cluster with little prose. Two headings are a
    # short book, not a TOC, so the floor is deliberately four.
    numbered = [item for item in candidates if item.chapter_number_normalized is not None]
    for start in range(len(numbered)):
        cluster = [numbered[start]]
        for item in numbered[start + 1:]:
            if item.paragraph_index - cluster[-1].paragraph_index > 2:
                break
            if (
                item.chapter_number_normalized == 1
                and cluster[-1].chapter_number_normalized not in {None, 1}
                and len(cluster) >= 4
            ):
                break
            cluster.append(item)
        if len(cluster) < 4 or _sequence_quality(cluster) < 0.66:
            continue
        lo, hi = cluster[0].paragraph_index, cluster[-1].paragraph_index
        if any(region.start_index <= lo <= region.end_index for region in regions):
            continue
        prose_chars = sum(
            rec.char_count for rec in records[lo:hi + 1]
            if rec.index not in by_index
        )
        normalized = {normalize_heading(item.normalized_text).casefold() for item in cluster}
        later = {
            normalize_heading(item.normalized_text).casefold()
            for item in candidates
            if item.paragraph_index > hi
        }
        duplicate_ratio = len(normalized & later) / len(normalized)
        if prose_chars <= max(20, len(cluster) * 3) and (
            duplicate_ratio >= 0.5
            or (prose_chars == 0 and lo < max(80, len(records) // 8))
        ):
            regions.append(TocRegion(lo, hi, False, "dense_sequential_heading_cluster"))

    for candidate in candidates:
        for region in regions:
            if region.start_index <= candidate.paragraph_index <= region.end_index:
                candidate.is_toc_candidate = True
                candidate.toc_score = 1.0 if region.explicit else 0.8
                candidate.flags.append("toc_region")
                candidate.rejection_reason = "目录条目，不作为正文边界"
                break
    return sorted(regions, key=lambda item: item.start_index)


def _resolve_candidates(candidates: list[HeadingCandidate]) -> None:
    body = [item for item in candidates if not item.is_toc_candidate]
    numbered = [item for item in body if item.chapter_number_normalized is not None]
    quality = _sequence_quality(numbered)
    has_primary_numbered = sum(
        item.heading_type in {HeadingType.NUMBERED_CHAPTER.value, HeadingType.ENGLISH_CHAPTER.value}
        for item in body
    ) >= 2
    seen: dict[str, HeadingCandidate] = {}
    previous_number: int | None = None
    for item in body:
        key = normalize_heading(item.normalized_text).casefold()
        prior = seen.get(key)
        if prior and prior.style_signal and not item.style_signal:
            item.rejection_reason = "正文标题已出现，后续重复项不是新边界"
            item.flags.append("duplicate_after_body_heading")
            continue
        seen[key] = item

        kind = HeadingType(item.heading_type)
        semantic = kind not in {
            HeadingType.NUMBERED_CHAPTER,
            HeadingType.ENGLISH_CHAPTER,
            HeadingType.NUMBERED_SECTION,
            HeadingType.OTHER,
        }
        accept = item.style_signal or semantic
        if kind in {HeadingType.NUMBERED_CHAPTER, HeadingType.ENGLISH_CHAPTER}:
            accept = item.style_signal or (
                len(numbered) >= 2 and quality >= 0.55
            ) or item.preceding_blank or item.following_blank
        if kind == HeadingType.NUMBERED_SECTION:
            accept = item.style_signal or (
                not has_primary_numbered
                and len(numbered) >= 2
                and quality >= 0.55
                and (numbered[0].chapter_number_normalized or 0) <= 2
            )
        if kind == HeadingType.OTHER:
            accept = item.style_signal
        if item.chapter_number_normalized is not None:
            if previous_number is None or item.chapter_number_normalized in {1, previous_number + 1}:
                item.sequence_score = 1.0
            elif item.chapter_number_normalized == previous_number:
                item.sequence_score = 0.4
                if not item.style_signal:
                    accept = False
                    item.flags.append("duplicate_chapter_number")
            else:
                item.sequence_score = 0.0
                item.flags.append("sequence_discontinuity")
                if not item.style_signal and kind == HeadingType.NUMBERED_SECTION:
                    accept = False
            if accept:
                previous_number = item.chapter_number_normalized
        item.is_body_candidate = accept
        if accept:
            item.confidence = min(1.0, item.confidence + 0.1 * item.sequence_score)
        elif not item.rejection_reason:
            item.rejection_reason = "缺少样式或连续章节序列证据"


def _unit_type(candidate: HeadingCandidate) -> UnitType:
    kind = HeadingType(candidate.heading_type)
    if kind == HeadingType.INTRODUCTION:
        return UnitType.INTRODUCTION
    if kind == HeadingType.AFTERWORD:
        return UnitType.AFTERWORD
    if kind == HeadingType.APPENDIX:
        return UnitType.APPENDIX
    if kind == HeadingType.NOTES:
        return UnitType.NOTES
    if kind == HeadingType.ACKNOWLEDGEMENTS:
        return UnitType.ACKNOWLEDGEMENTS
    if kind == HeadingType.REFERENCES:
        return UnitType.REFERENCES
    if kind == HeadingType.PREFACE:
        return UnitType.FRONTMATTER
    if kind == HeadingType.OTHER and "document_title_style" in candidate.flags:
        return UnitType.FRONTMATTER
    return UnitType.CHAPTER


def _in_toc(index: int, regions: Iterable[TocRegion]) -> bool:
    return any(region.start_index <= index <= region.end_index for region in regions)


def _build_units(
    records: list[ParagraphRecord], candidates: list[HeadingCandidate], toc_regions: list[TocRegion]
) -> list[StructureUnit]:
    boundaries = sorted((item for item in candidates if item.adopted), key=lambda item: item.paragraph_index)
    units: list[StructureUnit] = []

    def content(start: int, end: int) -> list[str]:
        return [
            record.normalized_text
            for record in records[start:end]
            if record.normalized_text
            and not _METADATA_BOUNDARY.fullmatch(record.normalized_text)
            and not _in_toc(record.index, toc_regions)
        ]

    first = boundaries[0].paragraph_index if boundaries else len(records)
    front = content(0, first)
    if front:
        units.append(StructureUnit(
            unit_type=UnitType.FRONTMATTER.value,
            title="前置内容",
            paragraphs=front,
            start_index=0,
            end_index=max(0, first - 1),
            source_heading_index=None,
            analyzable=False,
            confidence=0.9,
            start_page=records[0].page_number if records else None,
            end_page=records[first - 1].page_number if first else None,
            char_count=sum(len(item) for item in front),
            detection_source=("document_position",),
        ))
    for index, boundary in enumerate(boundaries):
        stop = boundaries[index + 1].paragraph_index if index + 1 < len(boundaries) else len(records)
        unit_type = _unit_type(boundary)
        body = content(boundary.paragraph_index + 1, stop)
        title = boundary.normalized_text
        sources = ["style" if boundary.style_signal else "regex"]
        if boundary.sequence_score:
            sources.append("sequence")
        if "anomaly_repair" in boundary.flags:
            sources.append("repair")
        units.append(StructureUnit(
            unit_type=unit_type.value,
            title=title,
            paragraphs=body,
            start_index=boundary.paragraph_index,
            end_index=max(boundary.paragraph_index, stop - 1),
            source_heading_index=boundary.paragraph_index,
            analyzable=unit_type in ANALYZABLE_UNIT_TYPES,
            confidence=boundary.confidence,
            chapter_number=boundary.chapter_number_normalized,
            start_page=records[boundary.paragraph_index].page_number,
            end_page=records[max(boundary.paragraph_index, stop - 1)].page_number,
            char_count=sum(len(item) for item in body),
            detection_source=tuple(sources),
        ))
    if not units:
        body = content(0, len(records))
        if body:
            units.append(StructureUnit(
                UnitType.CHAPTER.value,
                "正文",
                body,
                0,
                len(records) - 1,
                None,
                True,
                0.35,
                start_page=records[0].page_number if records else None,
                end_page=records[-1].page_number if records else None,
                char_count=sum(len(item) for item in body),
                detection_source=("fallback",),
            ))
    result = [unit for unit in units if unit.paragraphs or unit.source_heading_index is not None]
    for ordinal, unit in enumerate(result, start=1):
        unit.id = f"U{ordinal:04d}"
        unit.ordinal = ordinal
    return result


def _oversized_units(units: list[StructureUnit]) -> list[StructureUnit]:
    populated = [unit for unit in units if unit.paragraphs and unit.analyzable]
    oversized: list[StructureUnit] = []
    for unit in populated:
        peer_sizes = [item.char_count for item in populated if item is not unit]
        if not peer_sizes:
            continue
        baseline = statistics.median(peer_sizes)
        if unit.char_count > max(25_000, baseline * 3):
            oversized.append(unit)
    return oversized


def _repair_missing_boundaries(
    records: list[ParagraphRecord],
    units: list[StructureUnit],
    candidates: list[HeadingCandidate],
    toc_regions: list[TocRegion],
) -> tuple[list[StructureUnit], bool]:
    """Rescan oversized analyzable units for conservatively decorated back-matter headings.

    Normal candidate extraction intentionally requires an entire clean heading paragraph. During
    anomaly repair we permit common isolated decorations such as ``【后记】`` or ``——致谢——``, but
    only inside an already abnormal unit and only for semantic back-matter types. This keeps the
    second pass useful without turning prose mentions into boundaries.
    """
    backmatter = {
        HeadingType.AFTERWORD.value,
        HeadingType.APPENDIX.value,
        HeadingType.NOTES.value,
        HeadingType.ACKNOWLEDGEMENTS.value,
        HeadingType.REFERENCES.value,
    }
    existing = {item.paragraph_index for item in candidates}
    repaired = False
    for unit in _oversized_units(units):
        for record in records[unit.start_index + 1:unit.end_index + 1]:
            if record.index in existing or _in_toc(record.index, toc_regions):
                continue
            cleaned = record.normalized_text.strip("【】[]<>《》—-_=*· \t")
            if cleaned == record.normalized_text or not cleaned:
                continue
            candidate = _candidate(replace(
                record,
                raw_text=cleaned,
                normalized_text=cleaned,
                char_count=len(cleaned),
            ))
            if candidate is None or candidate.heading_type not in backmatter:
                continue
            candidate.is_body_candidate = True
            candidate.confidence = max(candidate.confidence, 0.85)
            candidate.flags.extend(("anomaly_repair", "decorated_backmatter_heading"))
            candidates.append(candidate)
            existing.add(record.index)
            repaired = True
    if repaired:
        return _build_units(records, candidates, toc_regions), True
    return units, False


def _validate_structure(
    units: list[StructureUnit], candidates: list[HeadingCandidate], *, repaired: bool
) -> list[str]:
    warnings: list[str] = []
    if repaired:
        warnings.append("STRUCTURE_BOUNDARY_REPAIRED")
    for unit in _oversized_units(units):
        warnings.append(f"OVERSIZED_STRUCTURE_UNIT:{unit.title}")
    if any(item.adopted and "sequence_discontinuity" in item.flags for item in candidates):
        warnings.append("CHAPTER_SEQUENCE_DISCONTINUITY")
    return warnings


def parse_document_structure(records: list[ParagraphRecord]) -> DocumentStructure:
    candidates = [candidate for record in records if (candidate := _candidate(record)) is not None]
    toc_regions = _mark_toc(records, candidates)
    _resolve_candidates(candidates)
    units = _build_units(records, candidates, toc_regions)
    units, repaired = _repair_missing_boundaries(records, units, candidates, toc_regions)
    warnings = _validate_structure(units, candidates, repaired=repaired)
    adopted = [item for item in candidates if item.adopted]
    confidence = (
        sum(item.confidence for item in adopted) / len(adopted)
        if adopted else 0.35
    )
    rules = [
        "paragraph-normalizer-v1",
        "heading-candidate-extractor-v1",
        "toc-detector-v1",
        "heading-classifier-v1",
        "chapter-sequence-resolver-v1",
        "boundary-builder-v1",
        "structure-validator-v1",
        "anomaly-repair-v1",
    ]
    return DocumentStructure(units, candidates, toc_regions, warnings, round(confidence, 4), rules)
