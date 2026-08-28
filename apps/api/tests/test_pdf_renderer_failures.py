"""Regression tests for installed-app PDF failures (CHG-20260829-001)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.narrative_core.whole_book_v2 import router as pdf_router
from app.services import entitlement


def test_locked_chromium_profile_never_masks_render_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WinError 32 during cleanup used to abort the socket and surface as Failed to fetch."""
    workspace = tmp_path / "storylens-pdf-test"
    workspace.mkdir()
    cleanup_calls: list[tuple[str, bool]] = []
    commands: list[list[str]] = []

    monkeypatch.setattr(entitlement, "can_use_feature", lambda *_: {"enabled": True})
    monkeypatch.setattr(pdf_router, "_find_pdf_browser", lambda: "fake-edge.exe")
    monkeypatch.setattr(pdf_router, "_print_via_devtools", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pdf_router.tempfile, "mkdtemp", lambda **_kwargs: str(workspace))

    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=7, stderr=b"", stdout=b"")

    monkeypatch.setattr(pdf_router.subprocess, "run", fake_run)

    def locked_cleanup(path: str, *, ignore_errors: bool = False) -> None:
        cleanup_calls.append((path, ignore_errors))
        if not ignore_errors:
            raise PermissionError(32, "profile lock is still held")

    monkeypatch.setattr(pdf_router.shutil, "rmtree", locked_cleanup)

    with pytest.raises(HTTPException) as caught:
        pdf_router.render_report_pdf(None, "<title>测试</title><p>正文</p>")  # type: ignore[arg-type]

    assert caught.value.status_code == 500
    assert caught.value.detail["error_code"] == "PDF_RENDER_FAILED"
    assert caught.value.detail["message"] == "Chromium exit code: 7"
    assert cleanup_calls[-1] == (str(workspace), True)
    assert len(commands) == 2
    assert commands[0] != commands[1]
    assert "profile-1" in " ".join(commands[0])
    assert "profile-2" in " ".join(commands[1])


def test_cleanup_pdf_workspace_swallows_persistent_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []

    def always_locked(_path: str, *, ignore_errors: bool = False) -> None:
        calls.append(ignore_errors)
        if not ignore_errors:
            raise PermissionError(32, "locked")

    monkeypatch.setattr(pdf_router.shutil, "rmtree", always_locked)
    monkeypatch.setattr(pdf_router.time, "sleep", lambda _seconds: None)

    pdf_router._cleanup_pdf_workspace(str(tmp_path / "locked"))

    assert calls == [False, False, False, False, True]
