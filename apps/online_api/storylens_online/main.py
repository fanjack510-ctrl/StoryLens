from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from storylens_online import __version__
from storylens_online.config import OnlineConfigSnapshot, OnlineSettings


class HealthResponse(BaseModel):
    status: str
    service: str
    component_version: str
    runtime: str


class ReadinessResponse(BaseModel):
    status: str
    configuration: OnlineConfigSnapshot
    blockers: tuple[str, ...]


def create_app(settings: OnlineSettings | None = None) -> FastAPI:
    active_settings = settings or OnlineSettings()
    app = FastAPI(
        title="StoryLens Online API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = active_settings

    @app.get("/health/live", response_model=HealthResponse)
    def health_live() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="storylens-online-api",
            component_version=__version__,
            runtime=active_settings.runtime,
        )

    @app.get("/health/ready", response_model=ReadinessResponse)
    def health_ready() -> ReadinessResponse:
        snapshot = active_settings.public_snapshot()
        blockers: list[str] = []
        if not snapshot.pocketbase_configured:
            blockers.append("pocketbase_not_configured")
        if not snapshot.redis_configured:
            blockers.append("redis_not_configured")
        if not snapshot.afdian_configured:
            blockers.append("afdian_not_configured")
        return ReadinessResponse(
            status="ready" if not blockers else "configuration_pending",
            configuration=snapshot,
            blockers=tuple(blockers),
        )

    return app


app = create_app()
