from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from storylens_online import __version__
from storylens_online.config import OnlineConfigSnapshot, OnlineSettings
from storylens_online.contracts.beta import (
    AuthCredentials,
    AuthSession,
    JobCreateRequest,
    JobResponse,
    JobResultResponse,
    PublicErrorBody,
    PublicErrorResponse,
    UploadResponse,
    UserResponse,
    phase_result_from_json,
)
from storylens_online.db.models import OnlineAnalysisJob
from storylens_online.db.session import OnlineDatabase
from storylens_online.errors import PublicApiError
from storylens_online.services.auth import AuthGateway, PocketBaseAuthClient
from storylens_online.services.queue import JobQueue, RedisJobQueue
from storylens_online.services.repository import OnlineRepository
from storylens_online.services.storage import SecureUploadStorage

LOGGER = logging.getLogger("storylens_online.api")
SESSION_COOKIE_NAME = "storylens_online_session"


class HealthResponse(BaseModel):
    status: str
    service: str
    component_version: str
    runtime: str


class ReadinessResponse(BaseModel):
    status: str
    configuration: OnlineConfigSnapshot
    blockers: tuple[str, ...]


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = PublicErrorResponse(error=PublicErrorBody(code=code, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _available_pipelines(settings: OnlineSettings, user_id: str) -> tuple[str, ...]:
    pipelines = ["phase2a_smoke"]
    if settings.phase2b1_enabled and user_id in settings.phase2b1_allowlisted_user_ids:
        pipelines.append("phase2b1_txt_evidence_summary")
    return tuple(pipelines)


def _user_response(session: AuthSession, settings: OnlineSettings) -> UserResponse:
    return UserResponse(
        id=session.user.id,
        email=session.user.email,
        available_pipelines=_available_pipelines(settings, session.user.id),
    )


def _set_session_cookie(response: Response, token: str, settings: OnlineSettings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_cookie_max_age_seconds,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def create_app(
    settings: OnlineSettings | None = None,
    *,
    database: OnlineDatabase | None = None,
    auth_gateway: AuthGateway | None = None,
    queue: JobQueue | None = None,
    storage: SecureUploadStorage | None = None,
) -> FastAPI:
    active_settings = settings or OnlineSettings()
    active_database = database or OnlineDatabase(active_settings.database_url)
    active_auth = auth_gateway or PocketBaseAuthClient(
        active_settings.pocketbase_url,
        active_settings.pocketbase_auth_collection,
    )
    active_queue = queue or RedisJobQueue(
        active_settings.redis_url,
        active_settings.job_queue_name,
    )
    active_storage = storage or SecureUploadStorage(
        active_settings.upload_dir,
        active_settings.upload_max_bytes,
    )
    repository = OnlineRepository()
    owns_database = database is None
    owns_queue = queue is None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_queue and isinstance(active_queue, RedisJobQueue):
            active_queue.close()
        if owns_database:
            active_database.dispose()

    app = FastAPI(
        title="StoryLens Online API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.database = active_database
    app.state.auth_gateway = active_auth
    app.state.queue = active_queue
    app.state.storage = active_storage

    @app.exception_handler(PublicApiError)
    async def public_error_handler(_request: Request, exc: PublicApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(422, "invalid_request", "请求参数不符合要求。")

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        LOGGER.error("Unhandled StoryLens Online request failure")
        return _error_response(500, "internal_error", "服务暂时无法完成请求。")

    async def current_session(request: Request) -> AuthSession:
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if not token:
            raise PublicApiError(401, "authentication_required", "请先登录。")
        return await active_auth.authenticate(token)

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

    @app.post("/api/v1/auth/register", response_model=UserResponse, status_code=201)
    async def register(
        credentials: AuthCredentials,
        response: Response,
    ) -> UserResponse:
        session = await active_auth.register(credentials.email, credentials.password)
        _set_session_cookie(response, session.token, active_settings)
        return _user_response(session, active_settings)

    @app.post("/api/v1/auth/login", response_model=UserResponse)
    async def login(credentials: AuthCredentials, response: Response) -> UserResponse:
        session = await active_auth.login(credentials.email, credentials.password)
        _set_session_cookie(response, session.token, active_settings)
        return _user_response(session, active_settings)

    @app.post("/api/v1/auth/logout", status_code=204)
    async def logout(response: Response) -> None:
        response.delete_cookie(
            SESSION_COOKIE_NAME,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )

    @app.get("/api/v1/auth/me", response_model=UserResponse)
    async def me(
        response: Response,
        session: AuthSession = Depends(current_session),  # noqa: B008
    ) -> UserResponse:
        _set_session_cookie(response, session.token, active_settings)
        return _user_response(session, active_settings)

    @app.post("/api/v1/uploads", response_model=UploadResponse, status_code=201)
    async def upload_txt(
        file: UploadFile = File(...),  # noqa: B008
        session: AuthSession = Depends(current_session),  # noqa: B008
    ) -> UploadResponse:
        content = await file.read(active_settings.upload_max_bytes + 1)
        stored = active_storage.store(file.filename, content)
        try:
            with active_database.session() as db_session:
                upload = repository.create_upload(db_session, session.user.id, stored)
                response = UploadResponse.model_validate(upload)
        except Exception:
            active_storage.delete(stored.storage_key)
            raise
        return response

    @app.post("/api/v1/jobs", response_model=JobResponse, status_code=201)
    async def create_job(
        request: JobCreateRequest,
        session: AuthSession = Depends(current_session),  # noqa: B008
    ) -> JobResponse:
        if request.pipeline not in _available_pipelines(active_settings, session.user.id):
            raise PublicApiError(403, "pipeline_unavailable", "该分析任务尚未对当前账户开放。")
        with active_database.session() as db_session:
            upload = repository.get_upload_for_user(
                db_session,
                request.upload_id,
                session.user.id,
            )
            if upload is None:
                raise PublicApiError(404, "upload_not_found", "找不到该上传文件。")
            job, created = repository.create_or_get_job(
                db_session,
                user_id=session.user.id,
                upload_id=upload.id,
                idempotency_key=request.idempotency_key,
                pipeline=request.pipeline,
            )
            if not created and (job.upload_id != upload.id or job.pipeline != request.pipeline):
                raise PublicApiError(409, "idempotency_conflict", "幂等键已用于其他任务。")
            result = JobResponse.model_validate(job)
        if created:
            try:
                await run_in_threadpool(active_queue.enqueue, job.id)
            except Exception as exc:
                with active_database.session() as db_session:
                    repository.mark_failed(db_session, job.id, "queue_unavailable")
                raise PublicApiError(503, "queue_unavailable", "任务队列暂时不可用。") from exc
        return result

    @app.get("/api/v1/jobs", response_model=list[JobResponse])
    async def list_jobs(
        session: AuthSession = Depends(current_session),  # noqa: B008
    ) -> list[JobResponse]:
        with active_database.session() as db_session:
            jobs = repository.list_jobs(db_session, session.user.id)
            return [JobResponse.model_validate(job) for job in jobs]

    @app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
    async def get_job(
        job_id: str,
        session: AuthSession = Depends(current_session),  # noqa: B008
    ) -> JobResponse:
        job = _owned_job(active_database, repository, job_id, session.user.id)
        return JobResponse.model_validate(job)

    @app.get("/api/v1/jobs/{job_id}/result", response_model=JobResultResponse)
    async def get_job_result(
        job_id: str,
        session: AuthSession = Depends(current_session),  # noqa: B008
    ) -> JobResultResponse:
        job = _owned_job(active_database, repository, job_id, session.user.id)
        if job.status != "succeeded" or job.result_json is None:
            raise PublicApiError(409, "job_not_succeeded", "任务尚未成功完成。")
        return JobResultResponse(
            job_id=job.id,
            result=phase_result_from_json(job.result_json),
        )

    return app


def _owned_job(
    database: OnlineDatabase,
    repository: OnlineRepository,
    job_id: str,
    user_id: str,
) -> OnlineAnalysisJob:
    with database.session() as db_session:
        job = repository.get_job_for_user(db_session, job_id, user_id)
        if job is None:
            raise PublicApiError(404, "job_not_found", "找不到该任务。")
        db_session.expunge(job)
        return job


app = create_app()
