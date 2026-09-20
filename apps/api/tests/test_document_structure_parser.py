from __future__ import annotations

from pathlib import Path

from app.domain.document_structure import (
    ParagraphRecord,
    UnitType,
    parse_document_structure,
    records_from_text,
)
from app.domain.ingestion import detect_chapters


def parse(text: str):
    return parse_document_structure(records_from_text(text))


def headings(count: int = 5) -> str:
    return "\n\n".join(f"第{i}章 标题{i}\n正文{i}。" for i in range(1, count + 1))


def test_c01_explicit_toc_entries_are_not_body_boundaries() -> None:
    text = "目录\n第1章 开始\n第2章 继续\n第3章 转折\n第4章 收束\n\n" + headings(4)
    result = parse(text)
    assert len(result.toc_regions) == 1
    assert [u.title for u in result.analyzable_units] == [
        "第1章 标题1", "第2章 标题2", "第3章 标题3", "第4章 标题4"
    ]


def test_c02_implicit_dense_toc_is_detected() -> None:
    toc = "\n".join(f"第{i}章 标题{i}" for i in range(1, 6))
    result = parse(toc + "\n\n" + headings(5))
    assert any(not region.explicit for region in result.toc_regions)
    assert len(result.analyzable_units) == 5


def test_c03_c07_non_numbered_units_are_classified() -> None:
    text = (
        "前言\n前置正文。\n\n引言 主问题\n引言正文。\n\n第一章 开始\n正文。\n\n"
        "后记 之后\n后记正文。\n\n附录A 术语\n附录正文。\n\n注释\n注释正文。\n\n"
        "致谢\n致谢正文。\n\n参考文献\n文献正文。"
    )
    result = parse(text)
    assert [u.unit_type for u in result.units] == [
        UnitType.FRONTMATTER, UnitType.INTRODUCTION, UnitType.CHAPTER,
        UnitType.AFTERWORD, UnitType.APPENDIX, UnitType.NOTES,
        UnitType.ACKNOWLEDGEMENTS, UnitType.REFERENCES,
    ]
    assert [u.analyzable for u in result.units][-3:] == [False, False, False]


def test_c08_chapter_mention_inside_prose_does_not_split() -> None:
    result = parse("正文第一段。\n见第4章可知，这只是正文中的引用。\n正文第三段。")
    assert len(result.units) == 1
    assert len(result.units[0].paragraphs) == 3


def test_c09_c11_heading_formats_remain_compatible() -> None:
    for text in (
        "\n\n".join(f"Chapter {i}: Title {i}\nBody {i}." for i in range(1, 4)),
        "\n\n".join(f"第{i}章 标题{i}\n正文。" for i in range(1, 4)),
        "\n\n".join(f"第{i}卷 卷名{i}\n正文。" for i in range(1, 4)),
        "\n\n".join(f"{i}. 标题{i}\n正文。" for i in range(1, 4)),
    ):
        assert len(parse(text).analyzable_units) == 3


def test_c12_sequence_restart_marks_the_first_dense_cluster_as_toc() -> None:
    toc = "\n".join(f"第{i}章 标题{i}" for i in range(1, 9))
    body = headings(8)
    result = parse(toc + "\n\n" + body)
    assert len(result.analyzable_units) == 8
    assert result.toc_regions


def test_c13_afterword_prevents_an_oversized_last_chapter() -> None:
    body = "正文很长。" * 6000
    result = parse("第一章 开始\n短正文。\n第二章 最后一章\n" + body + "\n【后记】\n后记正文。")
    assert [u.unit_type for u in result.units][-1] == UnitType.AFTERWORD
    assert result.units[-1].paragraphs == ["后记正文。"]
    assert "repair" in result.units[-1].detection_source
    assert "STRUCTURE_BOUNDARY_REPAIRED" in result.warnings


def test_c14_declared_docx_heading_style_outranks_plain_text() -> None:
    records = [
        ParagraphRecord(0, "第1章 目录项", "第1章 目录项", source_type="docx"),
        ParagraphRecord(1, "第1章 正文", "第1章 正文", source_type="docx", style_name="章节标题"),
        ParagraphRecord(2, "正文。", "正文。", source_type="docx"),
    ]
    result = parse_document_structure(records)
    adopted = [item for item in result.candidates if item.adopted]
    assert len(adopted) == 1 and adopted[0].style_signal
    assert result.analyzable_units[0].title == "第1章 正文"


def test_structure_units_keep_pages_ordinals_counts_and_detection_evidence() -> None:
    records = [
        ParagraphRecord(0, "Introduction", "Introduction", source_type="docx", page_number=2, style_name="Title"),
        ParagraphRecord(1, "Body.", "Body.", source_type="docx", page_number=3),
    ]
    unit = parse_document_structure(records).units[0]
    assert (unit.id, unit.ordinal, unit.start_page, unit.end_page) == ("U0001", 1, 2, 3)
    assert unit.char_count == len("Body.")
    assert unit.detection_source == ("style",)


def test_document_title_style_is_frontmatter_not_an_analyzable_chapter() -> None:
    records = [
        ParagraphRecord(0, "Book title", "Book title", source_type="docx", style_name="Title"),
        ParagraphRecord(1, "第一章 开始", "第一章 开始", source_type="docx", style_name="章节标题"),
        ParagraphRecord(2, "正文。", "正文。", source_type="docx"),
    ]
    result = parse_document_structure(records)
    assert [unit.unit_type for unit in result.units] == [UnitType.FRONTMATTER, UnitType.CHAPTER]
    assert len(result.analyzable_units) == 1


def test_c15_txt_fallback_uses_document_level_sequence() -> None:
    result = detect_chapters(headings(4))
    assert len(result.chapters) == 4
    assert all(item.adopted for item in result.candidates)


def test_c16_short_book_is_not_toc_and_figure_is_not_chapter() -> None:
    result = parse("第一章 开始\n图1-1 结构示意\n正文。\n第二章 结束\n正文。")
    assert not result.toc_regions
    assert len(result.analyzable_units) == 2
    assert all(item.normalized_text != "图1-1 结构示意" for item in result.candidates)


def test_heading_only_structure_unit_is_not_projected_as_a_legacy_chapter() -> None:
    result = detect_chapters("第一章 开始\n正文。\n第二章 空标题")
    assert [unit.title for unit in result.structure.units] == ["第一章 开始", "第二章 空标题"]
    assert result.structure.units[-1].paragraphs == []
    assert [chapter.title for chapter in result.chapters] == ["第一章 开始"]


def test_life_3_0_fixture_has_ten_analyzable_units_and_backmatter() -> None:
    fixture = Path(__file__).parent / "fixtures" / "life_3_0_structure_excerpt.txt"
    result = parse(fixture.read_text(encoding="utf-8"))
    assert [unit.unit_type for unit in result.analyzable_units] == [
        UnitType.INTRODUCTION,
        *([UnitType.CHAPTER] * 8),
        UnitType.AFTERWORD,
    ]
    assert sum(unit.unit_type == UnitType.CHAPTER for unit in result.units) == 8
    assert any(unit.unit_type == UnitType.NOTES for unit in result.units)
    assert any(unit.unit_type == UnitType.ACKNOWLEDGEMENTS for unit in result.units)
    assert len(result.toc_regions) == 1
    body_text = [paragraph for unit in result.units for paragraph in unit.paragraphs]
    assert len(body_text) == len(set(body_text))
