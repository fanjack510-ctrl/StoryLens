from fastapi.testclient import TestClient

from app.domain.ingestion import detect_chapters, split_chapters


def test_no_separator_and_number_variants() -> None:
    text = """第一章没有分隔符的标题
原创正文段落一。
原创正文段落二。
第二章另一个标题
原创正文段落三。
第三章：冒号标题
正文。
第4章阿拉伯数字
正文。
第五章 标题
正文。
"""
    chapters = split_chapters(text)
    assert [item.title for item in chapters] == [
        "第一章没有分隔符的标题", "第二章另一个标题", "第三章：冒号标题", "第4章阿拉伯数字", "第五章 标题"
    ]


def test_large_chinese_and_hui_numbers() -> None:
    text = "第一百二十三章标题\n正文。\n第一百二十四回标题\n正文。\n第１２５节标题\n正文。"
    result = detect_chapters(text)
    assert len(result.chapters) == 3
    assert [item.number for item in result.candidates] == [123, 124, 125]


def test_body_phrase_is_not_isolated_heading_and_marker_filtered() -> None:
    text = "正文第一段。\n第七章内容其实在这里继续展开……\n正文第三段。\n------章节内容开始-------"
    chapters = split_chapters(text)
    assert len(chapters) == 1
    assert "第七章内容其实在这里继续展开……" in chapters[0].paragraphs
    assert not any("章节内容开始" in item for item in chapters[0].paragraphs)


def test_gb18030_preview_and_import_diagnostics(client: TestClient) -> None:
    source = "第一章没有空格\n原创段落。\n第二章继续前行\n原创段落。"
    encoded = source.encode("gb18030")
    preview = client.post("/api/v1/books/chapter-detection/preview", files={"file": ("原创.txt", encoded, "text/plain")})
    assert preview.status_code == 200
    assert preview.json()["encoding"] == "gb18030"
    assert preview.json()["final_chapter_count"] == 2
    imported = client.post("/api/v1/books/import", files={"file": ("原创.txt", encoded, "text/plain")}).json()
    diagnostic = client.get(f"/api/v1/books/{imported['book_id']}/import-diagnostics").json()
    assert diagnostic["candidate_count"] == 2


def test_utf8_sig_and_suspect_large_single_chapter(client: TestClient) -> None:
    source = ("原创正文，没有章节标题。\n" * 10_000).encode("utf-8-sig")
    result = client.post("/api/v1/books/chapter-detection/preview", files={"file": ("大文件.txt", source, "text/plain")}).json()
    assert result["encoding"] == "utf-8-sig"
    assert result["warning"] == "CHAPTER_DETECTION_SUSPECT"
    assert result["recommended_to_import"] is False


def test_pagination_evidence_page_and_reparse(client: TestClient) -> None:
    source = "第一章标题\n" + "\n".join(f"原创段落{i}。" for i in range(620)) + "\n第二章标题\n收束。"
    imported = client.post("/api/v1/books/import", files={"file": ("分页.txt", source.encode(), "text/plain")}).json()
    chapters = client.get(f"/api/v1/books/{imported['book_id']}/chapters").json()
    page = client.get(f"/api/v1/chapters/{chapters[0]['id']}/paragraphs?offset=0&limit=200").json()
    assert len(page["items"]) == 200 and page["total"] == 620 and page["has_more"]
    target = page["items"][0]["id"].replace("P0001", "P0550")
    located = client.get(f"/api/v1/chapters/{chapters[0]['id']}/paragraphs?limit=200&paragraph_id={target}").json()
    assert any(item["id"] == target for item in located["items"])
    preview = client.post(f"/api/v1/books/{imported['book_id']}/reparse-preview").json()
    assert preview["old_chapter_count"] == preview["final_chapter_count"] == 2
    assert client.post(f"/api/v1/books/{imported['book_id']}/reparse", json={"confirm": False}).status_code == 422
    assert client.post(f"/api/v1/books/{imported['book_id']}/reparse", json={"confirm": True}).status_code == 200
