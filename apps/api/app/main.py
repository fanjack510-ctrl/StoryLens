from contextlib import asynccontextmanager
import os
import uuid

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.api.v1.router import router as api_v1_router
from app.api.v1.analysis import router as analysis_router
from app.api.v1.analysis_recovery import router as analysis_recovery_router
from app.api.v1.desktop import router as desktop_router
from app.api.v1.boundary_reviews import router as boundary_review_router
from app.api.v1.reader_journey import router as reader_journey_router
from app.core.config import get_settings
from app.core.paths import is_web_production_mode
from app.core.sidecar_control import request_shutdown, shutdown_token
from app.db.session import SessionLocal, create_db
from app.middleware.local_origin import LocalOriginGuardMiddleware, SecurityHeadersMiddleware
from app.services.instance_lock import acquire_instance_lock, release_instance_lock
from app.services.scene_pipeline import mark_interrupted_runs_failed
from app.services.spa_static import mount_spa


def _cors_origins() -> list[str]:
    port = os.environ.get("STORYLENS_WEB_PORT", "8765").strip() or "8765"
    origins = [
        "http://127.0.0.1:1420",
        "http://localhost:1420",
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        "tauri://localhost",
        "http://tauri.localhost",
    ]
    extra = os.environ.get("STORYLENS_ALLOWED_ORIGINS", "")
    for item in extra.split(","):
        item = item.strip().rstrip("/")
        if item and item not in origins:
            origins.append(item)
    return origins


def _bind_port() -> int:
    for key in ("STORYLENS_WEB_PORT", "STORYLENS_API_PORT", "PORT"):
        raw = os.environ.get(key, "").strip()
        if raw.isdigit():
            return int(raw)
    return 8765 if is_web_production_mode() else 8000


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Prefer one writer on the production SQLite root when running local web.
    if is_web_production_mode() and os.environ.get(
        "STORYLENS_DISABLE_INSTANCE_LOCK", ""
    ).lower() not in {"1", "true", "yes"}:
        acquire_instance_lock(port=_bind_port(), shell="browser_local_production")
    try:
        create_db()
        with SessionLocal() as session:
            mark_interrupted_runs_failed(session)
        yield
    finally:
        if is_web_production_mode():
            release_instance_lock()


app = FastAPI(title="StoryLens API", version=__version__, lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LocalOriginGuardMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_v1_router)
# Recovery Center owns GET recovery-plan + POST recover (unified/legacy dispatch).
app.include_router(analysis_recovery_router, prefix="/api/v1")
app.include_router(analysis_router)
app.include_router(desktop_router)
app.include_router(boundary_review_router)
app.include_router(reader_journey_router)


@app.middleware("http")
async def request_trace(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error_code" in exc.detail:
        content = dict(exc.detail)
        content["request_id"] = getattr(_.state, "request_id", None)
        content.setdefault("retryable", False)
        content.setdefault("user_action_hint", None)
        return JSONResponse(status_code=exc.status_code, content=content)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "HTTP_ERROR", "message": str(exc.detail), "details": {}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={
        "error_code": "REQUEST_VALIDATION_ERROR",
        "message": "请求字段校验失败。",
        "details": exc.errors(),
        "request_id": getattr(request.state, "request_id", None),
        "retryable": False,
        "user_action_hint": "请刷新页面后重新提交；若仍失败，请查看字段诊断。",
    })


@app.get("/health")
def health() -> dict[str, str]:
    with SessionLocal() as session:
        session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "service": "storylens-api",
        "database": "ok",
        "default_provider": get_settings().default_model_provider,
    }


def _client_is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    # "testclient" is Starlette/FastAPI TestClient's in-process peer, not a network client.
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


@app.post("/internal/shutdown")
def internal_shutdown(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Desktop-owned graceful stop. Loopback + optional bearer token only."""
    if not _client_is_loopback(request):
        raise HTTPException(status_code=403, detail="Shutdown allowed from loopback only")
    expected = shutdown_token()
    if expected:
        provided = ""
        if authorization and authorization.lower().startswith("bearer "):
            provided = authorization[7:].strip()
        if provided != expected:
            raise HTTPException(status_code=401, detail="Invalid shutdown token")
    request_shutdown()
    return {"status": "shutting_down"}


@app.get("/api/v1/system/capabilities")
def system_capabilities() -> dict[str, str]:
    return {"capability_schema_version": "1c-a-2"}


# SPA catch-all must be last so API routes keep precedence.
mount_spa(app)
