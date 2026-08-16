"""Confirm a book profile through the API — for tests that start analysis runs.

Both analysis entries hard-gate on a confirmed profile (10_ADAPTIVE_PROFILE_LAYER §4.3,
CHG-20260815-093). A test that starts a run now does what a user does: confirm the five
axes first. Drafting is deterministic and free, so this costs nothing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

#: Every axis filled with a legal value; slice_of_life keeps the chapter-focus block short.
FULL_AXES = {
    "monetization": "paid_subscription",
    "audience": "neutral",
    "engine": "slice_of_life",
    "pov": "single_lead",
    "length": "short",
}


def confirm_book_profile(client: TestClient, book_id: int, axes: dict[str, str] | None = None) -> None:
    draft = client.post(f"/api/v1/books/{book_id}/profile/draft")
    assert draft.status_code == 200, draft.text
    confirmed = client.post(
        f"/api/v1/books/{book_id}/profile/confirm", json={"axes": axes or FULL_AXES}
    )
    assert confirmed.status_code == 200, confirmed.text
