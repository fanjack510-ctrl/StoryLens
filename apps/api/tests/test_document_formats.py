"""各种格式的大纲读取。

这条读法的前提是「读者不读原文也知道书里说了什么」。前提立不立得住，全看两件事：结构认不认
得出、内容会不会静默消失。所以这里盯的是这两条，而不是好路径。

一条贯穿的原则：**能直接读到结构的格式就别猜**。Word 的标题样式、Markdown 的 `#`、LaTeX 的
`\\section`、HTML 的 `<h2>`、ODT 的 outline-level 都是明写的，读一下就有，比从纯文本猜准得
多，也解释得清。
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.domain.document_outline import detect_headings, outline_from_headings
from app.services.document_formats import (
    UnsupportedFormatError,
    outline_from_bytes,
    outline_from_html,
    outline_from_latex,
    outline_from_markdown,
)


# --------------------------------------------------------------- 中文与英文


def test_chinese_numbering_is_recognised() -> None:
    """中文专著的编号习惯跟英文完全不同，只会认 `3.1 Title` 等于只支持英文书。"""
    lines = [
        "第一章 绪论",
        "本章讨论问题的由来。",
        "第二节 研究方法",
        "方法部分。",
        "一、文献综述",
        "综述内容。",
        "（二）实证分析",
        "分析内容。",
    ]
    heads = detect_headings(lines)
    assert [h[3] for h in heads] == ["绪论", "研究方法", "文献综述", "实证分析"]
    assert [h[1] for h in heads] == [1, 2, 2, 3]


def test_english_and_numeric_headings_are_recognised() -> None:
    lines = ["CHAPTER 3", "3.1 First Thing", "body", "3.1.2 Deeper", "more body", "§4 Later"]
    heads = detect_headings(lines)
    levels = {h[3]: h[1] for h in heads}
    assert levels["First Thing"] == 2
    assert levels["Deeper"] == 3


def test_a_paragraph_that_merely_starts_with_a_number_is_not_a_heading() -> None:
    """`1.2 的取值范围决定了……` 是正文。把它当标题，会把一节劈成两半。"""
    long_line = "1.2 的取值范围决定了后续所有推导的边界条件，因此必须先行确定下来。"
    assert detect_headings([long_line]) == []


def test_content_before_the_first_heading_is_kept() -> None:
    """封面、版权页、总目录都在第一个标题之前。丢掉的东西用户看不见，也就无从发现丢了。"""
    outline = outline_from_headings(["书名与版权信息", "第一章 开始", "正文"])
    assert outline.nodes[0].title == "前置内容"
    assert "书名与版权信息" in outline.nodes[0].paragraphs


def test_a_document_with_no_headings_becomes_one_section_not_zero() -> None:
    outline = outline_from_headings(["就是一段话。", "又一段。"])
    assert len(outline.nodes) == 1
    assert outline.nodes[0].word_count > 0


# ------------------------------------------------------------------- 各格式


def test_markdown_headings_are_read_not_guessed() -> None:
    md = "# 第一章\n开篇。\n## 1.1 小节\n内容。\n"
    outline = outline_from_markdown(md)
    assert outline.source == "declared"
    assert [n.level for n in outline.nodes] == [1, 2]
    assert outline.nodes[1].paragraphs == ["内容。"]


def test_latex_section_commands_give_the_structure() -> None:
    tex = (
        "\\documentclass{article}\n% 注释里的 \\section{不算} \n"
        "\\begin{document}\n"
        "\\section{Introduction}\nWe begin here.\n"
        "\\subsection{Prior \\emph{Work}}\nEarlier studies.\n"
        "\\end{document}\n"
    )
    outline = outline_from_latex(tex)
    assert outline.source == "declared"
    assert [n.level for n in outline.nodes] == [2, 3]
    # 标题里的嵌套花括号不能把标题截断
    assert "Prior" in outline.nodes[1].title and "Work" in outline.nodes[1].title
    assert "不算" not in " ".join(n.title for n in outline.nodes)


def test_html_headings_do_not_duplicate_their_container_text() -> None:
    html = "<h1>章</h1><div><p>第一段</p><p>第二段</p></div>"
    outline = outline_from_html(html)
    assert outline.nodes[0].paragraphs == ["第一段", "第二段"]


def test_docx_uses_style_names_including_the_chinese_ones() -> None:
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_paragraph("第一章 绪论", style="Heading 1")
    doc.add_paragraph("这是正文。")
    buf = io.BytesIO()
    doc.save(buf)
    outline = outline_from_bytes("a.docx", buf.getvalue())
    assert outline.source == "declared"
    assert outline.nodes[0].title == "第一章 绪论"
    assert outline.nodes[0].paragraphs == ["这是正文。"]


def test_odt_outline_levels_are_read() -> None:
    content = (
        '<?xml version="1.0"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        '<office:body><office:text>'
        '<text:h text:outline-level="1">第一章</text:h>'
        "<text:p>正文一段。</text:p>"
        "</office:text></office:body></office:document-content>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("content.xml", content)
    outline = outline_from_bytes("a.odt", buf.getvalue())
    assert outline.nodes[0].title == "第一章"
    assert outline.nodes[0].paragraphs == ["正文一段。"]


# --------------------------------------------------------------- 不支持的格式


def test_cnki_formats_say_what_to_do_instead_of_just_refusing() -> None:
    """「无法导入」会让用户反复换文件。说清楚该去下载 PDF，他一次就解决了。"""
    for suffix in (".caj", ".nh", ".kdh"):
        with pytest.raises(UnsupportedFormatError) as err:
            outline_from_bytes(f"paper{suffix}", b"x")
        assert "PDF" in str(err.value)


def test_ebook_formats_point_at_the_conversion() -> None:
    with pytest.raises(UnsupportedFormatError) as err:
        outline_from_bytes("book.mobi", b"x")
    assert "EPUB" in str(err.value)


def test_an_unknown_suffix_lists_what_is_supported() -> None:
    with pytest.raises(UnsupportedFormatError) as err:
        outline_from_bytes("x.pages", b"x")
    assert "DOCX" in str(err.value).upper()
