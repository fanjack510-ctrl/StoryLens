from fastapi.testclient import TestClient

from app.domain.ingestion import split_chapters


SAMPLE = """序言第一段

第一章 初见

这是第一段。

这是第二段。

第二章 转折

这是第三段。
"""


def test_chapter_splitting() -> None:
    chapters = split_chapters(SAMPLE)
    assert [chapter.title for chapter in chapters] == ["正文", "第一章 初见", "第二章 转折"]
    assert [len(chapter.paragraphs) for chapter in chapters] == [1, 2, 1]


def test_txt_import_and_queries(client: TestClient) -> None:
    response = client.post(
        "/api/v1/books/import",
        files={"file": ("示例.txt", SAMPLE.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201
    result = response.json()
    assert result["chapter_count"] == 3
    assert result["paragraph_count"] == 4

    book_id = result["book_id"]
    books = client.get("/api/v1/books").json()
    assert books[0]["title"] == "示例"
    assert client.get(f"/api/v1/books/{book_id}").status_code == 200

    chapters = client.get(f"/api/v1/books/{book_id}/chapters").json()
    second_chapter = chapters[1]
    paragraphs = client.get(f"/api/v1/chapters/{second_chapter['id']}/paragraphs").json()
    assert [item["paragraph_index"] for item in paragraphs] == [1, 2]
    assert [item["id"] for item in paragraphs] == [
        f"B{book_id:04d}-C0002-P0001",
        f"B{book_id:04d}-C0002-P0002",
    ]
    assert second_chapter["start_paragraph_id"] == paragraphs[0]["id"]
    assert second_chapter["end_paragraph_id"] == paragraphs[-1]["id"]


def test_invalid_file_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/books/import",
        files={"file": ("bad.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 415
    assert response.json()["error_code"] == "INVALID_FILE_TYPE"


def _diagnose(text: str) -> dict:
    """Import diagnostics for a body of text, without touching the database."""
    from app.services.book_service import preview_book

    return preview_book("sample.txt", text.encode("utf-8"))[2]


def test_one_chapter_holding_the_whole_book_is_flagged() -> None:
    """The case that slipped through every earlier rule.

    《碧血洗银枪》 imported as two chapters with 99.5% of its 151,935 characters in one of them,
    and raised no warning at all: each criterion keyed on "one chapter or fewer", and two is
    more than one. Everything above ingestion is sized in chapters, so the pacing curve, the
    per-chapter table and the act structure all collapsed onto that chapter — and the report
    then said so about the book rather than about the split.
    """
    body = "。".join("这是正文的一段话" for _ in range(9_000))
    text = "第一章 开头\n\n短短的一段。\n\n第二章 正文\n\n" + body
    diagnostics = _diagnose(text)

    assert diagnostics["final_chapter_count"] == 2
    assert diagnostics["warning"] == "CHAPTER_DETECTION_SUSPECT"
    assert "ONE_CHAPTER_DOMINATES" in diagnostics["suspect_reasons"]
    assert "OVERSIZED_CHAPTER" in diagnostics["suspect_reasons"]
    assert diagnostics["max_chapter_share"] > 0.9


def test_a_book_split_evenly_raises_nothing() -> None:
    # The rule has to stay quiet on ordinary books, or the warning becomes noise and is ignored
    # exactly when it matters. Checked against the local library: this criterion flags the five
    # books whose split is wrong and none of the ten whose split is right.
    parts = [f"第{i}章 标题\n\n" + "。".join("这一章写了一些事情" for _ in range(40)) for i in range(1, 21)]
    diagnostics = _diagnose("\n\n".join(parts))

    assert diagnostics["final_chapter_count"] == 20
    assert diagnostics["warning"] is None
    assert diagnostics["suspect_reasons"] == []


def test_the_diagnostics_carry_the_formats_a_user_can_check_against() -> None:
    """The repair we ask for is the cheap one: the person holding the file fixes the file.

    That only works if we say what we recognise, so the list travels with the diagnostics rather
    than living in the client where it would drift from the patterns.
    """
    from app.domain.ingestion import SUPPORTED_CHAPTER_FORMATS

    diagnostics = _diagnose("整本书只有这一段话，没有任何章节标记。")

    assert diagnostics["supported_chapter_formats"] == list(SUPPORTED_CHAPTER_FORMATS)
    assert any("第1章" in item for item in diagnostics["supported_chapter_formats"])
    assert "SINGLE_CHAPTER" in diagnostics["suspect_reasons"]
