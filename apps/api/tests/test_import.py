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
