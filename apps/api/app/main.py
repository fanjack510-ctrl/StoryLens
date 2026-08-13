from contextlib import asynccontextmanager
import logging
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
from app.api.v1.scene_boundaries import router as scene_boundaries_router
from app.api.v1.reader_journey import router as reader_journey_router
from app.routers.capabilities import router as capabilities_router
from app.routers.whole_book_preflight import router as whole_book_preflight_router
from app.routers.whole_book_native_overview import router as whole_book_native_overview_router
from app.routers.whole_book_results import router as whole_book_results_router
from app.narrative_core.whole_book_v2.router import router as whole_book_v2_router
from app.routers.pro_whole_book_insights import router as pro_whole_book_insights_router
from app.routers.whole_book_cost_consent import router as whole_book_cost_consent_router
from app.routers.book_profile_router import router as book_profile_router
from app.routers.whole_book_foundation_router import router as whole_book_foundation_router
from app.routers.whole_book_free_product_router import router as whole_book_free_product_router
from app.routers.whole_book_product_capability_router import router as whole_book_product_capability_router
from app.routers import whole_book_mock_lab_runs as mock_lab_runs
from app.routers import whole_book_private_engine_lab_runs as private_engine_lab_runs
from app.core.config import get_settings
from app.core.paths import apply_runtime_path_defaults, is_web_production_mode

# Resolve absolute prompt/data paths before Settings is first constructed.
# Uvicorn entry uses cwd=apps/api; relative packages/prompts would miss repo prompts.
apply_runtime_path_defaults()
from app.core.sidecar_control import request_shutdown, shutdown_token
from app.db.session import SessionLocal, create_db
from app.middleware.local_origin import LocalOriginGuardMiddleware, SecurityHeadersMiddleware
from app.narrative_core.services import mock_whole_book_run_runtime as _mock_lab_runtime_mod
from app.narrative_core.services.mock_lab_authorization_service import (
    is_mock_lab_enabled_from_env,
)
from app.narrative_core.services.private_engine_lab_authorization_service import (
    is_private_engine_lab_enabled_from_env,
    should_register_private_engine_lab_router,
)
from app.narrative_core.services.mock_run_recovery_service import MockRunStartupRecoveryAdapter
from app.narrative_core.services.mock_whole_book_run_runtime import (
    create_mock_lab_runtime,
    log_lab_startup_status,
    should_register_mock_lab_router,
)
from app.services.instance_lock import acquire_instance_lock, release_instance_lock
from app.services.scene_pipeline import mark_interrupted_runs_failed
from app.narrative_core.services.whole_book_startup_recovery_v1 import (
    mark_interrupted_whole_book_runs,
)
from app.services.spa_static import mount_spa

logger = logging.getLogger(__name__)


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


def _resolve_environment(environment: str | None = None) -> str:
    if environment is not None:
        return str(environment).strip().lower()
    return str(
        os.environ.get("STORYLENS_APP_ENV")
        or os.environ.get("APP_ENV")
        or os.environ.get("ENVIRONMENT")
        or "development"
    ).strip().lower()


def _resolve_lab_enabled(lab_enabled: bool | None = None) -> bool:
    if lab_enabled is not None:
        return bool(lab_enabled)
    return is_mock_lab_enabled_from_env()


def _resolve_private_engine_lab_enabled(lab_enabled: bool | None = None) -> bool:
    if lab_enabled is not None:
        return bool(lab_enabled)
    return is_private_engine_lab_enabled_from_env()


def _set_default_mock_lab_runtime(runtime) -> None:
    with _mock_lab_runtime_mod._lock:
        _mock_lab_runtime_mod._default_runtime = runtime


def _make_lifespan(
    *,
    environment: str | None = None,
    lab_enabled: bool | None = None,
    private_engine_lab_enabled: bool | None = None,
):
    env = _resolve_environment(environment)
    lab_on = _resolve_lab_enabled(lab_enabled)
    private_lab_on = _resolve_private_engine_lab_enabled(private_engine_lab_enabled)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Prefer one writer on the production SQLite root when running local web.
        if is_web_production_mode() and os.environ.get(
            "STORYLENS_DISABLE_INSTANCE_LOCK", ""
        ).lower() not in {"1", "true", "yes"}:
            acquire_instance_lock(port=_bind_port(), shell="browser_local_production")
        try:
            create_db()
            requeue_journey_ids: list[int] = []
            with SessionLocal() as session:
                stats = mark_interrupted_runs_failed(session)
                requeue_journey_ids = list(stats.get("requeue_journey_ids") or [])
                try:
                    mark_interrupted_whole_book_runs(session)
                except Exception:  # noqa: BLE001 — never block startup
                    logger.exception("whole_book_startup_recovery_failed")
            # CHG-013: re-claim unclaimed starting/queued journeys after restart.
            if requeue_journey_ids:
                import asyncio

                from app.model_gateway.registry import get_model_gateway
                from app.services.reader_journey_pipeline import execute_reader_journey

                gateway = get_model_gateway()

                async def _requeue() -> None:
                    for journey_id in requeue_journey_ids:
                        try:
                            await execute_reader_journey(
                                SessionLocal, gateway, int(journey_id)
                            )
                        except Exception:  # noqa: BLE001
                            logger.exception(
                                "startup_requeue_journey_failed journey_run_id=%s",
                                journey_id,
                            )

                asyncio.create_task(_requeue())
                logger.info(
                    "reader_journey_startup_requeue count=%s ids=%s",
                    len(requeue_journey_ids),
                    requeue_journey_ids[:20],
                )
            log_lab_startup_status(environment=env, lab_enabled=lab_on)
            if private_lab_on:
                logger.info(
                    "private engine lab enabled for environment=%s (non-production only)",
                    env,
                )
            try:
                MockRunStartupRecoveryAdapter(
                    SessionLocal,
                    lab_enabled=lab_on,
                ).reconcile()
            except Exception:  # noqa: BLE001 — never block startup
                logger.exception(
                    "mock lab startup recovery reconcile failed (non-blocking)"
                )
            if private_lab_on:
                try:
                    from app.narrative_core.services.private_lab_recovery_service import (
                        PrivateLabRecoveryService,
                    )

                    with SessionLocal() as session:
                        result = PrivateLabRecoveryService(session).startup_reconcile()
                    logger.info(
                        "private lab startup recovery: scanned=%s interrupted=%s auto_resumed=%s",
                        result.scanned,
                        len(result.interrupted_run_ids),
                        result.auto_resumed,
                    )
                except Exception:  # noqa: BLE001 — never block startup; never auto-resume
                    logger.exception(
                        "private lab startup recovery reconcile failed (non-blocking)"
                    )
            yield
        finally:
            if is_web_production_mode():
                release_instance_lock()

    return lifespan


def _configure_middleware_and_routers(app: FastAPI) -> None:
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
    app.include_router(book_profile_router)
    app.include_router(analysis_recovery_router, prefix="/api/v1")
    app.include_router(analysis_router)
    app.include_router(desktop_router)
    app.include_router(boundary_review_router)
    app.include_router(scene_boundaries_router)
    app.include_router(reader_journey_router)
    app.include_router(capabilities_router)
    app.include_router(whole_book_cost_consent_router)
    app.include_router(whole_book_foundation_router)
    app.include_router(whole_book_product_capability_router)
    app.include_router(whole_book_free_product_router)
    app.include_router(whole_book_preflight_router)
    app.include_router(whole_book_native_overview_router)
    # Phase 1D Integration: read-only result projection (no run create / no review writes).
    app.include_router(whole_book_results_router)
    app.include_router(whole_book_v2_router)
    app.include_router(pro_whole_book_insights_router)


def mount_mock_lab_if_enabled(
    app: FastAPI,
    *,
    environment: str | None = None,
    lab_enabled: bool | None = None,
    runtime=None,
    session_factory=None,
) -> bool:
    """Conditionally mount Mock Lab router and wire default runtime."""
    env = _resolve_environment(environment)
    lab_on = _resolve_lab_enabled(lab_enabled)
    if not should_register_mock_lab_router(environment=env, lab_enabled=lab_on):
        return False
    if runtime is not None:
        _set_default_mock_lab_runtime(runtime)
    else:
        create_mock_lab_runtime(
            environment=env,
            lab_enabled=lab_on,
            session_factory=session_factory or SessionLocal,
            set_as_default=True,
        )
    app.include_router(mock_lab_runs.router)
    return True


def mount_private_engine_lab_if_enabled(
    app: FastAPI,
    *,
    environment: str | None = None,
    lab_enabled: bool | None = None,
) -> bool:
    """Conditionally mount Private Engine Lab router (distinct from Mock Lab)."""
    env = _resolve_environment(environment)
    lab_on = _resolve_private_engine_lab_enabled(lab_enabled)
    if not should_register_private_engine_lab_router(environment=env, lab_enabled=lab_on):
        return False
    app.include_router(private_engine_lab_runs.router)
    return True


def _register_app_handlers(app: FastAPI) -> None:
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
        errors = exc.errors()
        fields: list[str] = []
        for item in errors:
            loc = item.get("loc") or ()
            # Skip "body" / "query" prefix for readability.
            parts = [str(p) for p in loc if p not in {"body", "query", "path"}]
            if parts:
                fields.append(".".join(parts))
        if fields:
            message = f"请求参数异常：缺少或无效字段 {', '.join(fields)}"
        else:
            message = "请求参数异常。"
        return JSONResponse(status_code=422, content={
            "error_code": "REQUEST_SCHEMA_INVALID",
            "message": message,
            "details": errors,
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


def create_app(
    *,
    environment: str | None = None,
    lab_enabled: bool | None = None,
    private_engine_lab_enabled: bool | None = None,
) -> FastAPI:
    app = FastAPI(
        title="StoryLens API",
        version=__version__,
        lifespan=_make_lifespan(
            environment=environment,
            lab_enabled=lab_enabled,
            private_engine_lab_enabled=private_engine_lab_enabled,
        ),
    )
    _configure_middleware_and_routers(app)
    mount_mock_lab_if_enabled(
        app,
        environment=environment,
        lab_enabled=lab_enabled,
        session_factory=SessionLocal,
    )
    mount_private_engine_lab_if_enabled(
        app,
        environment=environment,
        lab_enabled=private_engine_lab_enabled,
    )
    _register_app_handlers(app)
    mount_spa(app)
    return app


app = create_app()
