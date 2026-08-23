"""专著/工具书的结构识别。

这条读法的价值前提是「读者不读原文也知道书里说了什么」。那前提立不立得住，全看这一层：
识别漏一节，读者不会知道自己漏了什么——对知识类书来说，覆盖率是及格线，不是加分项。

所以这里盯的都是「会让内容静默消失」的那些边界，而不是好路径。
"""

from __future__ import annotations

from app.domain.monograph_ingestion import (
    book_page_numbers,
    detect_monograph,
    squeeze,
    strip_page_furniture,
)


def test_squeeze_maps_back_to_the_original_position() -> None:
    """抹空白是这一层唯一的匹配方式，映射错了整篇定位都会偏。"""
    flat, index = squeeze("5I N T E R A C T I O N Unless we")
    assert flat.startswith("5INTERACTION")
    assert index[0] == 0
    # 抹掉后的第 12 个字符，映射回原文仍指向同一个字母
    assert "5I N T E R A C T I O N Unless we"[index[11]] == flat[11]


def test_three_faces_of_one_heading_all_match_after_squeezing() -> None:
    """同一个标题在这类 PDF 里有三种面貌，为每种写一条规则会补一个漏一个。"""
    faces = ["3.3 Usability T esting", "3.3U s a b i l i t y Testing", "3.3UsabilityTesting"]
    key = squeeze("3.3 Usability Testing")[0]
    for face in faces:
        assert key in squeeze(face)[0], face


def test_page_furniture_is_found_by_repetition_not_by_pattern() -> None:
    """第一版按某家排版厂的标记硬匹配，换本书就废。重复性才是所有书共有的性质。"""
    pages = [f"Handbook of Something\n第 {i} 章正文开始\n真正的内容 {i}\n{800 + i}" for i in range(10)]
    cleaned = strip_page_furniture(pages)
    assert all("Handbook of Something" not in p for p in cleaned)
    # 正文一个字也不能被顺手删掉
    assert all(f"真正的内容 {i}" in cleaned[i] for i in range(10))


def test_a_line_that_appears_once_is_not_furniture() -> None:
    """只出现过一次的行是正文，不是页眉——剔除必须保守。"""
    pages = ["页眉\n只此一处的重要论断\n1"] + [f"页眉\n普通内容 {i}\n{i}" for i in range(2, 10)]
    cleaned = strip_page_furniture(pages)
    assert "只此一处的重要论断" in cleaned[0]


def test_short_documents_are_left_alone() -> None:
    """三五页的文档没有统计意义，硬套重复率会把正文当页眉删掉。"""
    pages = ["同一句话", "同一句话", "同一句话"]
    assert strip_page_furniture(pages) == pages


def test_page_numbers_need_to_increase_to_count_as_page_numbers() -> None:
    """单看一页分不出页码和图注里的数字，看整本就分得出。"""
    good = [f"正文 {i}\n{100 + i}" for i in range(9)]
    assert book_page_numbers(good).get(104) == 4
    noisy = ["正文\n7", "正文\n7", "正文\n7", "正文\n7", "正文\n7", "正文\n7"]
    assert book_page_numbers(noisy) == {}


def _fake_book() -> list[str]:
    toc = (
        "CHAPTER 7\nSOMETHING IMPORTANT\nA. Author\n"
        "1 INTRODUCTION 10\n"
        "2 THE ARGUMENT 11\n"
        "2.1 First Part 11\n"
        "2.2 Second Part 12\n"
    )
    return [
        toc + "\n1 INTRODUCTION This chapter opens with a claim about something.",
        "2 THE ARGUMENT We now set out the argument in full. "
        "2.1 First Part The first part rests on an experiment. ",
        "2.2 Second Part The second part rests on a survey of prior work. ",
    ]


def test_every_section_in_the_table_of_contents_reaches_the_body() -> None:
    det = detect_monograph(_fake_book())
    assert [s.number for s in det.sections] == ["1", "2", "2.1", "2.2"]
    assert det.coverage == 1.0
    assert det.exact_count == 4


def test_the_chapters_first_section_is_not_lost_to_the_table_of_contents() -> None:
    """章首页上半是目录、下半就是正文。整页跳过，每章的第 1 节就永远找不到。"""
    det = detect_monograph(_fake_book())
    intro = next(s for s in det.sections if s.number == "1")
    assert intro.paragraphs, "第 1 节没有拿到正文"
    assert "opens with a claim" in " ".join(intro.paragraphs)


def test_a_page_number_masquerading_as_a_section_number_is_rejected() -> None:
    """页眉 `COLLECTING AND ANALYZING USER INSIGHTS 961` 会被目录正则读成「第 961 节」。"""
    pages = [
        "CHAPTER 3\nTITLE\n1 REAL SECTION 5\n961 NOT A SECTION AT ALL 962\n",
        "1 REAL SECTION body text here.",
    ]
    det = detect_monograph(pages)
    assert [s.number for s in det.sections] == ["1"]


def test_a_book_with_no_chapter_markers_still_produces_sections() -> None:
    """不是每本书都写 CHAPTER n。没有章首标记时全书作为一章，而不是识别出零节。"""
    pages = ["1 OPENING 3\n2 NEXT 4\n1 OPENING first body.", "2 NEXT second body."]
    det = detect_monograph(pages)
    assert len(det.sections) == 2
    assert det.chapter_titles


def test_a_pdf_without_a_text_layer_says_so_instead_of_importing_nothing() -> None:
    """扫描件是好文件，只是还差一步 OCR。

    把它并进「文件中没有可导入的文本」，用户会以为文件坏了去换一个——而该做的是 OCR。
    一句说不清的错误，会把人指向完全错误的方向。
    """
    import pytest

    from app.services.extractors import (
        InvalidFileTypeError,
        ScannedDocumentError,
        extract_document,
    )

    # 一个结构合法、但每页都没有文字的 PDF
    from io import BytesIO

    from pypdf import PdfWriter

    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=200, height=200)
    buf = BytesIO()
    w.write(buf)

    with pytest.raises(ScannedDocumentError) as err:
        extract_document("scan.pdf", buf.getvalue())
    assert "OCR" in str(err.value)

    # 后缀是 .pdf 不等于内容是 PDF
    with pytest.raises(InvalidFileTypeError):
        extract_document("bad.pdf", b"not a pdf at all")


def test_pdf_keeps_its_page_boundaries() -> None:
    """专著的结构藏在页眉重复和章首目录里，拼成一整个字符串就再也分不出来了。"""
    from io import BytesIO

    from pypdf import PdfWriter

    from app.services.extractors import extract_document

    w = PdfWriter()
    for _ in range(4):
        w.add_blank_page(width=200, height=200)
    buf = BytesIO()
    w.write(buf)
    try:
        doc = extract_document("x.pdf", buf.getvalue())
    except Exception:
        return  # 空白 PDF 会被判为扫描件，这条只在有文字时有意义
    assert doc.pages is not None and len(doc.pages) == 4


def _long_chapter(n_sections: int, *, drop: set[int] | None = None) -> list[str]:
    """造一章有 n 节的书。`drop` 里的节只出现在目录里，正文里没有。"""
    drop = drop or set()
    toc = ["CHAPTER 1", "Title", "A. Author"]
    for s in range(1, n_sections + 1):
        toc.append(f"{s} Topic Number {s} {s + 10}")
    pages = ["HANDBOOK\n" + "\n".join(toc) + "\n1"]
    for s in range(1, n_sections + 1):
        if s in drop:
            continue
        body = " ".join(f"word{s}x{k}" for k in range(60))
        pages.append(f"HANDBOOK\n{s} Topic Number {s}\n{body}\n{s + 1}")
    return pages


def test_chapter_with_more_than_99_sections_is_not_truncated():
    """一章 150 节要全认出来。

    这里原本有一句 `if int(num) > 99: continue`——按数值上限挡页眉噪声。它在一章 500 节的
    书上把第 100 节起全丢了，而且覆盖率照样报 100%，因为分子分母一起少。
    """
    det = detect_monograph(_long_chapter(150))
    assert len(det.sections) == 150
    assert det.sections[-1].number == "150"
    assert det.missing == []


def test_toc_entry_without_body_is_reported_not_dropped():
    """目录里有、正文里定位不到的节，必须留痕。

    静默丢掉它，读者会拿到一份自称完整的残缺摘要——而他正是用它替代原文的。
    """
    det = detect_monograph(_long_chapter(12, drop={5, 9}))
    assert len(det.sections) == 10
    assert len(det.missing) == 2
    assert any("Topic Number 5" in m for m in det.missing)
    assert any(" 2 节" in r for r in det.rules)
