import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import AnalysisRun, Book, Chapter, Paragraph, ReparseAudit
from app.db.session import get_db
from app.main import app


SOURCE = "书名：原创测试\n作者：测试者\n------章节内容开始-------\n第一章没有空格\n原创段落一。\n第二章继续\n原创段落二。"


def imported(client: TestClient) -> tuple[int, bytes]:
    content = SOURCE.encode("gb18030")
    result = client.post("/api/v1/books/import", files={"file": ("原创.txt", content, "text/plain")}).json()
    return result["book_id"], content


def client_session():
    generator = app.dependency_overrides[get_db]()
    return generator, next(generator)


def test_old_book_upload_preview_and_same_hash_replace(client: TestClient) -> None:
    book_id, content = imported(client)
    generator, session = client_session()
    book = session.get(Book, book_id)
    book.source_content = None
    session.commit()
    generator.close()
    preview = client.post(f"/api/v1/books/{book_id}/reparse-with-file-preview", files={"file": ("原创.txt", content, "text/plain")})
    assert preview.status_code == 200
    body = preview.json()
    assert body["hash_match"] is True and body["formal_chapter_count"] == 2
    assert body["front_matter_count"] == 1
    result = client.post(f"/api/v1/books/{book_id}/reparse-with-file", files={"file": ("原创.txt", content, "text/plain")}, data={"confirm": "true", "strategy": "replace_in_place"})
    assert result.status_code == 200 and result.json()["book_id"] == book_id
    chapters = client.get(f"/api/v1/books/{book_id}/chapters").json()
    assert chapters[0]["section_type"] == "front_matter" and chapters[0]["display_title"] == "前置内容"
    assert chapters[1]["chapter_number_normalized"] == 1
    assert chapters[1]["display_title"] == "第一章｜没有空格"


def test_different_hash_warning_and_confirmation(client: TestClient) -> None:
    book_id, content = imported(client)
    changed = content + "\n附加说明".encode("gb18030")
    preview = client.post(f"/api/v1/books/{book_id}/reparse-with-file-preview", files={"file": ("原创.txt", changed, "text/plain")}).json()
    assert preview["hash_match"] is False and preview["recommended_action"] == "create_revision"
    denied = client.post(f"/api/v1/books/{book_id}/reparse-with-file", files={"file": ("原创.txt", changed, "text/plain")}, data={"confirm": "true", "strategy": "replace_in_place"})
    assert denied.status_code == 422


def test_success_history_protection_and_revision(client: TestClient) -> None:
    book_id, content = imported(client)
    generator, session = client_session()
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book_id, Chapter.section_type == "chapter"))
    session.add(AnalysisRun(subject_id=str(chapter.id), provider="fake", model="fake", prompt_version="v1", schema_version="v1", input_hash="x"*64, status="succeeded"))
    session.commit()
    generator.close()
    denied = client.post(f"/api/v1/books/{book_id}/reparse-with-file", files={"file": ("原创.txt", content, "text/plain")}, data={"confirm": "true", "strategy": "replace_in_place"})
    assert denied.status_code == 409
    revision = client.post(f"/api/v1/books/{book_id}/reparse-with-file", files={"file": ("原创.txt", content, "text/plain")}, data={"confirm": "true", "strategy": "create_revision"})
    assert revision.status_code == 200 and revision.json()["book_id"] != book_id
    assert revision.json()["revision_of_book_id"] == book_id


def test_replace_cleans_failed_runs_and_audits(client: TestClient) -> None:
    book_id, content = imported(client)
    generator, session = client_session()
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book_id))
    session.add(AnalysisRun(subject_id=str(chapter.id), provider="fake", model="fake", prompt_version="v1", schema_version="v1", input_hash=hashlib.sha256(content).hexdigest(), status="failed"))
    session.commit()
    generator.close()
    response = client.post(f"/api/v1/books/{book_id}/reparse-with-file", files={"file": ("原创.txt", content, "text/plain")}, data={"confirm": "true", "strategy": "replace_in_place"})
    assert response.status_code == 200
    generator, session = client_session()
    assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 0
    assert session.scalar(select(func.count()).select_from(ReparseAudit)) == 1
    assert session.scalar(select(func.count()).select_from(Paragraph).where(Paragraph.book_id == book_id)) == 4
    generator.close()


def test_front_matter_cannot_be_analyzed(client: TestClient) -> None:
    book_id, _ = imported(client)
    chapter = client.get(f"/api/v1/books/{book_id}/chapters").json()[0]
    result = client.post(f"/api/v1/chapters/{chapter['id']}/analysis-runs", json={"provider_name": "fake"})
    assert result.status_code == 422 and result.json()["error_code"] == "FRONT_MATTER_ANALYSIS_DISABLED"
