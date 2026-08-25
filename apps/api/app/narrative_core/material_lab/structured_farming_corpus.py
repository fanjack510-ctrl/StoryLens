"""Deterministic reader for the structured ancient-farming DOCX corpus.

These files are editorial reference guides rather than novels.  Their five
fields are already explicit, so running a language model would add cost and
risk without adding information.  The parser therefore reads Word paragraph
styles directly from OOXML, validates every item with Pydantic, and gives each
source paragraph a stable evidence id.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from pydantic import BaseModel, ConfigDict, Field, model_validator


PIPELINE_VERSION = "structured-farming-docx-v1"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}
_SECTION_RE = re.compile(r"^(\d{2})\s+(.+?)\s*$")
_ITEM_RE = re.compile(r"^(\d{2})\s+(.+?)\s*$")


class FarmingSectionMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    section_label: str
    category_key: str
    subcategory_key: str


SECTION_MAPPINGS: dict[int, FarmingSectionMapping] = {
    1: FarmingSectionMapping(section_label="农家人物", category_key="daily", subcategory_key="household"),
    2: FarmingSectionMapping(section_label="村庄结构", category_key="daily", subcategory_key="village"),
    3: FarmingSectionMapping(section_label="房屋院落", category_key="daily", subcategory_key="village"),
    4: FarmingSectionMapping(section_label="土地制度", category_key="soil_water", subcategory_key="land_tenure"),
    5: FarmingSectionMapping(section_label="农作物", category_key="crop_cultivation", subcategory_key="crop"),
    6: FarmingSectionMapping(section_label="十二月农事", category_key="weather_season", subcategory_key="farm_timing"),
    7: FarmingSectionMapping(section_label="野菜山货", category_key="skill", subcategory_key="gathering"),
    8: FarmingSectionMapping(section_label="家禽家畜", category_key="livestock_processing", subcategory_key="livestock"),
    9: FarmingSectionMapping(section_label="捕鱼打猎", category_key="skill", subcategory_key="gathering"),
    10: FarmingSectionMapping(section_label="农具", category_key="skill", subcategory_key="tools"),
    11: FarmingSectionMapping(section_label="饮食", category_key="daily", subcategory_key="food"),
    12: FarmingSectionMapping(section_label="储粮腌制", category_key="livestock_processing", subcategory_key="storage"),
    13: FarmingSectionMapping(section_label="赶集摆摊", category_key="business", subcategory_key="market"),
    14: FarmingSectionMapping(section_label="物价收入", category_key="business", subcategory_key="prices"),
    15: FarmingSectionMapping(section_label="家庭副业", category_key="business", subcategory_key="side_business"),
    16: FarmingSectionMapping(section_label="手工制作", category_key="skill", subcategory_key="craft"),
    17: FarmingSectionMapping(section_label="婚嫁", category_key="daily", subcategory_key="custom"),
    18: FarmingSectionMapping(section_label="生育养娃", category_key="daily", subcategory_key="custom"),
    19: FarmingSectionMapping(section_label="分家继承", category_key="daily", subcategory_key="household"),
    20: FarmingSectionMapping(section_label="宗族邻里", category_key="daily", subcategory_key="household"),
    21: FarmingSectionMapping(section_label="灾荒逃荒", category_key="weather_season", subcategory_key="disaster"),
    22: FarmingSectionMapping(section_label="医疗草药", category_key="skill", subcategory_key="knowledge"),
    23: FarmingSectionMapping(section_label="节庆民俗", category_key="daily", subcategory_key="custom"),
    24: FarmingSectionMapping(section_label="发家致富路线", category_key="business", subcategory_key="expand"),
}
EXCLUDED_SECTIONS = {25: "种田剧情事件库属于剧情模板，不是纯知识"}


class StructuredFarmingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_path: str
    source_title: str = Field(min_length=1, max_length=255)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    section_number: int = Field(ge=1, le=99)
    section_label: str = Field(min_length=1, max_length=64)
    item_number: int = Field(ge=1, le=99)
    title: str = Field(min_length=1, max_length=200)
    applicable: str = Field(min_length=2, max_length=120)
    life_basis: str = Field(min_length=8, max_length=500)
    writing_example: str = Field(min_length=4, max_length=500)
    pitfall: str = Field(min_length=4, max_length=500)
    reference_direction: str = Field(min_length=1, max_length=200)
    applicable_paragraph: int = Field(ge=1)
    basis_paragraph: int = Field(ge=1)
    example_paragraph: int = Field(ge=1)
    pitfall_paragraph: int = Field(ge=1)
    reference_paragraph: int = Field(ge=1)
    category_key: str
    subcategory_key: str

    @model_validator(mode="after")
    def validate_mapping(self) -> "StructuredFarmingEntry":
        mapping = SECTION_MAPPINGS.get(self.section_number)
        if mapping is None:
            raise ValueError(f"section {self.section_number} is not importable knowledge")
        if (self.category_key, self.subcategory_key) != (
            mapping.category_key,
            mapping.subcategory_key,
        ):
            raise ValueError("category mapping does not match fixed section mapping")
        return self

    @property
    def evidence_prefix(self) -> str:
        return (
            f"D-{self.source_fingerprint[:10]}-S{self.section_number:02d}"
            f"-I{self.item_number:02d}"
        )


class StructuredFarmingCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entries: list[StructuredFarmingEntry]
    excluded_count: int = Field(ge=0)
    source_count: int = Field(ge=1)


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _paragraphs(path: Path) -> Iterable[tuple[int, str, str]]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    for index, paragraph in enumerate(root.findall(".//w:body/w:p", NS), 1):
        text = "".join(
            node.text or "" for node in paragraph.findall(".//w:t", NS)
        ).strip()
        if not text:
            continue
        style_node = paragraph.find("./w:pPr/w:pStyle", NS)
        style = (
            style_node.get(f"{{{WORD_NS}}}val", "")
            if style_node is not None
            else ""
        )
        yield index, style, text


def _source_title(path: Path, paragraph_rows: list[tuple[int, str, str]]) -> str:
    volume = next(
        (text.split("｜", 1)[0] for _, _, text in paragraph_rows if "册｜" in text),
        path.stem,
    )
    return f"古代种田文写作素材库·{volume}"


def parse_structured_farming_docx(path: Path) -> tuple[list[StructuredFarmingEntry], int]:
    rows = list(_paragraphs(path))
    fingerprint = _file_fingerprint(path)
    source_title = _source_title(path, rows)
    section_number = 0
    section_label = ""
    current: dict[str, object] | None = None
    entries: list[StructuredFarmingEntry] = []
    excluded = 0

    def finish() -> None:
        nonlocal current, excluded
        if current is None:
            return
        if section_number in EXCLUDED_SECTIONS:
            excluded += 1
            current = None
            return
        mapping = SECTION_MAPPINGS.get(section_number)
        if mapping is None:
            raise ValueError(f"unsupported knowledge section {section_number}: {section_label}")
        current.update({
            "source_path": str(path),
            "source_title": source_title,
            "source_fingerprint": fingerprint,
            "section_number": section_number,
            "section_label": mapping.section_label,
            "category_key": mapping.category_key,
            "subcategory_key": mapping.subcategory_key,
        })
        entries.append(StructuredFarmingEntry.model_validate(current))
        current = None

    field_names = {
        "适用：": ("applicable", "applicable_paragraph"),
        "生活依据：": ("life_basis", "basis_paragraph"),
        "可直接写：": ("writing_example", "example_paragraph"),
        "避坑：": ("pitfall", "pitfall_paragraph"),
        "依据方向：": ("reference_direction", "reference_paragraph"),
    }
    for paragraph_index, style, text in rows:
        if style == "Heading1":
            match = _SECTION_RE.match(text)
            if match:
                finish()
                section_number = int(match.group(1))
                section_label = match.group(2).strip()
            continue
        if style == "Heading3":
            finish()
            match = _ITEM_RE.match(text)
            if not match or not section_number:
                raise ValueError(f"orphan item heading in {path.name}: {text}")
            current = {
                "item_number": int(match.group(1)),
                "title": match.group(2).strip(),
            }
            continue
        if current is None:
            continue
        for prefix, (field, index_field) in field_names.items():
            if text.startswith(prefix):
                current[field] = text.removeprefix(prefix).strip()
                current[index_field] = paragraph_index
                break
    finish()
    return entries, excluded


def parse_structured_farming_directory(root: Path) -> StructuredFarmingCorpus:
    paths = sorted(root.glob("*.docx"))
    if not paths:
        raise ValueError(f"no DOCX files found in {root}")
    entries: list[StructuredFarmingEntry] = []
    excluded = 0
    for path in paths:
        parsed, skipped = parse_structured_farming_docx(path)
        entries.extend(parsed)
        excluded += skipped
    identities = {
        (row.source_fingerprint, row.section_number, row.item_number)
        for row in entries
    }
    if len(identities) != len(entries):
        raise ValueError("duplicate structured farming entries")
    return StructuredFarmingCorpus(
        entries=entries,
        excluded_count=excluded,
        source_count=len(paths),
    )


def corpus_fingerprint(corpus: StructuredFarmingCorpus) -> str:
    digest = hashlib.sha256(PIPELINE_VERSION.encode("utf-8"))
    for entry in sorted(
        corpus.entries,
        key=lambda row: (row.source_fingerprint, row.section_number, row.item_number),
    ):
        digest.update(
            f"{entry.source_fingerprint}|{entry.section_number}|{entry.item_number}|"
            f"{entry.life_basis}".encode("utf-8")
        )
    return digest.hexdigest()
