from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import uuid

from app.api.v1.router import router as api_v1_router
from app.api.v1.analysis import router as analysis_router
from app.api.v1.analysis_recovery import router as analysis_recovery_router
from app.api.v1.desktop import router as desktop_router
from app.api.v1.boundary_reviews import router as boundary_review_router
from app.api.v1.reader_journey import router as reader_journey_router
from app.core.config import get_settings
from app.db.session import SessionLocal, create_db
from app.services.scene_pipeline import mark_interrupted_runs_failed


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db()
    with SessionLocal() as session:
        mark_interrupted_runs_failed(session)
    yield


app = FastAPI(title="StoryLens API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:1420",
        "http://localhost:1420",
        "tauri://localhost",
        "http://tauri.localhost",
    ],
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


@app.get("/api/v1/system/capabilities")
def system_capabilities() -> dict[str, str]:
    return {"capability_schema_version": "1c-a-2"}
