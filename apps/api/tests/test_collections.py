"""书单：一组可以被反复回到的书。

共性视图和跨书检索要的第一件事是「哪些书」。没有书单，那个范围每次都要在书库里重新挑一遍，
而「上次那批」这句话根本无法表达。

这里钉的几条，都是「用起来会疼」的地方，不是 CRUD 本身能不能跑：
重复加入不该报错、删书单不能连书一起删、书单里的书要和书库长一样。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Book


def _book(session: Session, title: str, digest: str) -> int:
    row = Book(
        title=title,
        source_file_name=f"{title}.txt",
        source_file_hash=digest,
        import_status="imported",
    )
    session.add(row)
    session.flush()
    return int(row.id)


def _seed(client: TestClient) -> list[int]:
    from app.db.session import get_db

    gen = client.app.dependency_overrides[get_db]()
    session = next(gen)
    ids = [_book(session, f"书{i}", f"h{i}" * 8) for i in range(1, 4)]
    session.commit()
    return ids


def test_a_collection_starts_empty_and_keeps_its_reason(client: TestClient) -> None:
    """书单要有名字，也该能记下当初为什么圈这批书。

    几周后回到一个叫「第一批」的书单，那句 note 是唯一能说明当初标准的东西。
    """
    resp = client.post(
        "/api/v1/collections", json={"name": "2026 秋·扫榜", "note": "看开头怎么抓人"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "2026 秋·扫榜"
    assert body["note"] == "看开头怎么抓人"
    assert body["book_count"] == 0


def test_a_collection_must_have_a_name(client: TestClient) -> None:
    resp = client.post("/api/v1/collections", json={"name": "   "})
    assert resp.status_code == 400
    assert resp.json().get("error_code") or resp.json()["detail"]["error_code"] == "COLLECTION_NAME_REQUIRED"


def test_adding_the_same_book_twice_is_not_an_error(client: TestClient) -> None:
    """挑着挑着忘了加过没有，是常规动作。

    把重复加入当成错误，用户会以为操作失败了，然后再点一次——而真正的结果（书已经在里面）
    从头到尾都是对的。
    """
    ids = _seed(client)
    cid = client.post("/api/v1/collections", json={"name": "一批"}).json()["id"]

    first = client.post(f"/api/v1/collections/{cid}/books", json={"book_ids": ids})
    assert first.status_code == 200
    assert first.json() == {"added": 3, "book_count": 3}

    again = client.post(f"/api/v1/collections/{cid}/books", json={"book_ids": [ids[0]]})
    assert again.status_code == 200
    assert again.json() == {"added": 0, "book_count": 3}


def test_adding_a_book_that_is_not_there_says_so(client: TestClient) -> None:
    cid = client.post("/api/v1/collections", json={"name": "一批"}).json()["id"]
    resp = client.post(f"/api/v1/collections/{cid}/books", json={"book_ids": [99999]})
    assert resp.status_code == 404
    assert resp.json().get("error_code") or resp.json()["detail"]["error_code"] == "BOOK_NOT_FOUND"


def test_the_books_in_a_collection_look_like_the_books_in_the_library(
    client: TestClient,
) -> None:
    """同样的类型标、同样的分析状态。

    走两套渲染，两边迟早会不一致——而「这本跑完没有」在书单里问得只会更频繁：
    书单存在的理由就是一次看一批。
    """
    ids = _seed(client)
    cid = client.post("/api/v1/collections", json={"name": "一批"}).json()["id"]
    client.post(f"/api/v1/collections/{cid}/books", json={"book_ids": ids})

    detail = client.get(f"/api/v1/collections/{cid}").json()
    library = client.get("/api/v1/books/library").json()
    shape = {"id", "title", "kind_label", "analysis_state", "analysis_state_label"}
    assert detail["books"], "书单里应该有书"
    assert shape <= set(detail["books"][0])
    if library:
        rows = library["items"] if isinstance(library, dict) else library
        if rows:
            assert shape <= set(rows[0])


def test_the_order_books_were_added_in_is_kept(client: TestClient) -> None:
    """扫榜排出来的次序本身是结论的一部分，不能按 id 重排。"""
    ids = _seed(client)
    cid = client.post("/api/v1/collections", json={"name": "一批"}).json()["id"]
    reversed_ids = list(reversed(ids))
    client.post(f"/api/v1/collections/{cid}/books", json={"book_ids": reversed_ids})

    detail = client.get(f"/api/v1/collections/{cid}").json()
    assert [b["id"] for b in detail["books"]] == reversed_ids


def test_deleting_a_collection_does_not_delete_the_books(client: TestClient) -> None:
    """删书单不删书。

    书是导入进来的资产，书单只是一种看法；删掉一种看法不该让资料跟着消失。
    这一条如果错了，用户会在整理书架的时候丢掉原稿。
    """
    ids = _seed(client)
    cid = client.post("/api/v1/collections", json={"name": "一批"}).json()["id"]
    client.post(f"/api/v1/collections/{cid}/books", json={"book_ids": ids})

    assert client.delete(f"/api/v1/collections/{cid}").status_code == 200
    assert client.get(f"/api/v1/collections/{cid}").status_code == 404

    from app.db.session import get_db

    session = next(client.app.dependency_overrides[get_db]())
    from app.db.models import CollectionBook

    assert session.query(Book).count() == len(ids), "书被一起删掉了"
    # 关联行也不能留：孤儿行会让下一个同 id 的书单凭空多出几本书。
    assert session.query(CollectionBook).count() == 0


def test_removing_one_book_leaves_the_rest(client: TestClient) -> None:
    ids = _seed(client)
    cid = client.post("/api/v1/collections", json={"name": "一批"}).json()["id"]
    client.post(f"/api/v1/collections/{cid}/books", json={"book_ids": ids})

    resp = client.delete(f"/api/v1/collections/{cid}/books/{ids[0]}")
    assert resp.status_code == 200
    assert resp.json()["book_count"] == 2
    detail = client.get(f"/api/v1/collections/{cid}").json()
    assert [b["id"] for b in detail["books"]] == ids[1:]


def test_the_collection_you_just_touched_comes_first(client: TestClient) -> None:
    """正在用的书单应该在手边，而它是刚被加过书的那个。"""
    ids = _seed(client)
    first = client.post("/api/v1/collections", json={"name": "旧的"}).json()["id"]
    client.post("/api/v1/collections", json={"name": "新的"})
    client.post(f"/api/v1/collections/{first}/books", json={"book_ids": ids[:1]})

    names = [c["name"] for c in client.get("/api/v1/collections").json()["items"]]
    assert names[0] == "旧的", names
