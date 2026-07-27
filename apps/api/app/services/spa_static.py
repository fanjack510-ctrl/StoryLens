"""Serve the production React SPA from the same loopback FastAPI process."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.paths import resource_root


def resolve_frontend_dist() -> Path | None:
    override = os.environ.get("STORYLENS_FRONTEND_DIST", "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        return path if path.is_dir() else None
    candidate = (resource_root() / "apps" / "desktop" / "dist").resolve()
    return candidate if candidate.is_dir() else None


def should_serve_frontend() -> bool:
    flag = os.environ.get("STORYLENS_SERVE_FRONTEND", "").lower()
    if flag in {"0", "false", "no"}:
        return False
    if flag in {"1", "true", "yes"}:
        return True
    return os.environ.get("STORYLENS_WEB_MODE", "").lower() in {"1", "true", "yes", "web"}


def _is_safe_child(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def mount_spa(app: FastAPI) -> Path | None:
    if not should_serve_frontend():
        return None
    dist = resolve_frontend_dist()
    if dist is None:
        return None

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="frontend-assets")

    index = dist / "index.html"

    @app.get("/")
    async def spa_index() -> FileResponse:
        if not index.is_file():
            raise HTTPException(status_code=404, detail="FRONTEND_DIST_MISSING")
        return FileResponse(index)

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        # Never shadow API / health / internal routes (registered earlier take precedence
        # for exact matches; this catch-all only runs when no earlier route matched).
        lowered = full_path.lower()
        if (
            lowered.startswith("api/")
            or lowered.startswith("assets/")
            or lowered in {"health", "docs", "openapi.json", "redoc"}
            or lowered.startswith("internal/")
        ):
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        candidate = (dist / full_path).resolve()
        if candidate.is_file() and _is_safe_child(dist, candidate):
            return FileResponse(candidate)
        if not index.is_file():
            raise HTTPException(status_code=404, detail="FRONTEND_DIST_MISSING")
        return FileResponse(index)

    return dist
