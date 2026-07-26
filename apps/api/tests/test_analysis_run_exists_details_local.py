"""CHG-20260727-014: ANALYSIS_RUN_EXISTS details + error() details default."""

from __future__ import annotations

from fastapi import HTTPException

from app.api.v1.router import error


def test_error_helper_default_details_empty():
    exc = error(400, "X", "msg")
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 400
    assert exc.detail["error_code"] == "X"
    assert exc.detail["message"] == "msg"
    assert exc.detail["details"] == {}


def test_error_helper_accepts_details():
    exc = error(409, "ANALYSIS_RUN_EXISTS", "exists", details={"existing_run_id": 13})
    assert exc.detail["details"]["existing_run_id"] == 13
