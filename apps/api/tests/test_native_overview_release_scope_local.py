"""CHG-20260727-016: Native Overview create remains blocked when flag is off."""

from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import AnalysisRun

pytest_plugins = ["test_native_overview_walking_skeleton"]


def test_native_create_blocked_when_flag_off(api_env, monkeypatch):
    monkeypatch.setenv("PRO_NATIVE_OVERVIEW_ENABLED", "false")
    from test_native_overview_walking_skeleton import CREATE_BODY, _seed_pro_book

    book_id = _seed_pro_book(api_env)
    with api_env["factory"]() as session:
        before = int(session.scalar(select(func.count()).select_from(AnalysisRun)) or 0)

    resp = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "req-flag-off-create-016"},
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body.get("error_code") == "PRO_NATIVE_OVERVIEW_UNAVAILABLE"
    # Must not leak Private Engine implementation details.
    blob = str(body).lower()
    assert "storylens_private_engine" not in blob
    assert "private-native-overview-v1" not in blob

    with api_env["factory"]() as session:
        after = int(session.scalar(select(func.count()).select_from(AnalysisRun)) or 0)
    assert after == before
