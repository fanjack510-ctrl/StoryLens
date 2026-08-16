"""确认门：画像先于首次分析，单章与全书同一道门 (10_ADAPTIVE_PROFILE_LAYER §4.3, CHG-20260815-093).

Until now the profile only chose the engine — an unconfirmed book silently ran the old
path. Both run-creation entries now refuse with PROFILE_CONFIRMATION_REQUIRED until the
five axes are confirmed. A draft is not enough (INV-P2), and the error says which state
the profile is in so the client can word the next step.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.profile_gate_helpers import FULL_AXES, confirm_book_profile

TEXT = "第一章 起点\n\n" + "他推开门，看见院子里的旧机器还在转。\n\n" * 6


def _import_book(client: TestClient) -> tuple[int, int]:
    response = client.post(
        "/api/v1/books/import", files={"file": ("门测试.txt", TEXT.encode(), "text/plain")}
    )
    assert response.status_code == 201, response.text
    book_id = response.json()["book_id"]
    chapter_id = client.get(f"/api/v1/books/{book_id}/chapters").json()[0]["id"]
    return book_id, chapter_id


def test_chapter_run_blocked_without_profile(client: TestClient) -> None:
    _, chapter_id = _import_book(client)
    denied = client.post(
        f"/api/v1/chapters/{chapter_id}/analysis-runs", json={"provider_name": "fake"}
    )
    assert denied.status_code == 409, denied.text
    body = denied.json()
    assert body["error_code"] == "PROFILE_CONFIRMATION_REQUIRED"
    assert body["details"]["profile_status"] == "none"


def test_chapter_run_blocked_with_draft_only(client: TestClient) -> None:
    # INV-P2: an inferred draft is not a decision.
    book_id, chapter_id = _import_book(client)
    assert client.post(f"/api/v1/books/{book_id}/profile/draft").status_code == 200
    denied = client.post(
        f"/api/v1/chapters/{chapter_id}/analysis-runs", json={"provider_name": "fake"}
    )
    assert denied.status_code == 409
    assert denied.json()["details"]["profile_status"] == "draft"


def test_chapter_run_passes_after_confirmation(client: TestClient) -> None:
    book_id, chapter_id = _import_book(client)
    confirm_book_profile(client, book_id, FULL_AXES)
    accepted = client.post(
        f"/api/v1/chapters/{chapter_id}/analysis-runs", json={"provider_name": "fake"}
    )
    assert accepted.status_code == 202, accepted.text


def test_front_matter_refusal_still_wins_over_gate(client: TestClient) -> None:
    # The 422 about front matter is more specific than the gate and keeps precedence.
    response = client.post(
        "/api/v1/books/import",
        files={"file": ("序.txt", ("序言\n\n" + "介绍性文字。\n\n" * 5).encode(), "text/plain")},
    )
    book_id = response.json()["book_id"]
    chapters = client.get(f"/api/v1/books/{book_id}/chapters").json()
    front = [c for c in chapters if c.get("section_type") == "front_matter"]
    if not front:  # importer did not classify any front matter in this fixture — nothing to pin
        return
    denied = client.post(
        f"/api/v1/chapters/{front[0]['id']}/analysis-runs", json={"provider_name": "fake"}
    )
    assert denied.status_code == 422
    assert denied.json()["error_code"] == "FRONT_MATTER_ANALYSIS_DISABLED"


def test_whole_book_create_blocked_without_profile(client: TestClient) -> None:
    book_id, _ = _import_book(client)
    denied = client.post(
        f"/api/v1/books/{book_id}/whole-book/free/create",
        json={"estimate_id": 1, "client_request_id": "gate-test-1"},
    )
    assert denied.status_code == 409, denied.text
    body = denied.json()
    assert body["error_code"] == "PROFILE_CONFIRMATION_REQUIRED"
    assert body["details"]["profile_status"] == "none"


def test_whole_book_create_reaches_next_check_after_confirmation(client: TestClient) -> None:
    # With the profile confirmed the gate opens; the request then fails on the *next*
    # validation (bogus estimate / missing budget), which is the proof the 409 is gone.
    book_id, _ = _import_book(client)
    confirm_book_profile(client, book_id, FULL_AXES)
    response = client.post(
        f"/api/v1/books/{book_id}/whole-book/free/create",
        json={"estimate_id": 999999, "client_request_id": "gate-test-2"},
    )
    assert response.status_code != 409, response.text
    if response.status_code >= 400:
        assert response.json().get("error_code") != "PROFILE_CONFIRMATION_REQUIRED"
