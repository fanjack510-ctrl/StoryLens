from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from storylens_online.config import OnlineSettings
from storylens_online.contracts.beta import AuthenticatedUser, AuthSession
from storylens_online.db.models import (
    BillingReservation,
    ModelUsageLedger,
    OnlineAnalysisJob,
    OnlineBase,
    RechargeOrder,
    WalletAccount,
    WalletTransaction,
)
from storylens_online.db.session import OnlineDatabase
from storylens_online.errors import PublicApiError
from storylens_online.main import create_app
from storylens_online.services.storage import SecureUploadStorage
from storylens_online.worker import Phase2AWorker


class FakeAuthGateway:
    def __init__(self) -> None:
        self._users_by_email: dict[str, AuthenticatedUser] = {}
        self._sessions: dict[str, AuthSession] = {}

    async def register(self, email: str, password: str) -> AuthSession:
        del password
        if email in self._users_by_email:
            raise PublicApiError(400, "registration_failed", "注册失败。")
        user = AuthenticatedUser(id=f"user-{len(self._users_by_email) + 1}", email=email)
        self._users_by_email[email] = user
        return self._new_session(user)

    async def login(self, email: str, password: str) -> AuthSession:
        del password
        user = self._users_by_email.get(email)
        if user is None:
            raise PublicApiError(401, "invalid_credentials", "邮箱或密码不正确。")
        return self._new_session(user)

    async def authenticate(self, token: str) -> AuthSession:
        session = self._sessions.get(token)
        if session is None:
            raise PublicApiError(401, "authentication_required", "请先登录。")
        return session

    def _new_session(self, user: AuthenticatedUser) -> AuthSession:
        token = f"test-session-token-{user.id}-{len(self._sessions) + 1}"
        session = AuthSession(token=token, user=user)
        self._sessions[token] = session
        return session


class FakeQueue:
    def __init__(self) -> None:
        self.job_ids: list[str] = []

    def enqueue(self, job_id: str) -> None:
        self.job_ids.append(job_id)


@dataclass
class BetaHarness:
    client: TestClient
    database: OnlineDatabase
    storage: SecureUploadStorage
    queue: FakeQueue


@pytest.fixture
def beta_harness(tmp_path: Path) -> Iterator[BetaHarness]:
    database = OnlineDatabase(
        f"sqlite+pysqlite:///{tmp_path / 'online.db'}",
        connect_args={"check_same_thread": False},
    )
    OnlineBase.metadata.create_all(database.engine)
    storage = SecureUploadStorage(tmp_path / "uploads", max_bytes=64)
    queue = FakeQueue()
    settings = OnlineSettings(
        database_url="postgresql+psycopg://storylens@postgres:5432/storylens_online",
        frontend_origin="https://storylens.example.com",
        upload_dir=str(tmp_path / "uploads"),
        upload_max_bytes=64,
    )
    app = create_app(
        settings,
        database=database,
        auth_gateway=FakeAuthGateway(),
        queue=queue,
        storage=storage,
    )
    with TestClient(app, base_url="https://testserver") as client:
        yield BetaHarness(client=client, database=database, storage=storage, queue=queue)
    database.dispose()


def register(client: TestClient, email: str = "reader@example.com") -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "safe-password-123"},
    )
    assert response.status_code == 201, response.text


def upload(client: TestClient, filename: str = "book.txt", content: bytes = b"first\n\nsecond"):
    response = client.post(
        "/api/v1/uploads",
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_job(client: TestClient, upload_id: str, key: str = "request-key-001"):
    response = client.post(
        "/api/v1/jobs",
        json={"upload_id": upload_id, "idempotency_key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_register_login_logout_and_me_use_secure_cookie(beta_harness: BetaHarness) -> None:
    client = beta_harness.client
    register(client)
    cookie = client.cookies.get("storylens_online_session")
    assert cookie and cookie.startswith("test-session-token-")
    set_cookie = client.post(
        "/api/v1/auth/login",
        json={"email": "reader@example.com", "password": "safe-password-123"},
    ).headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert client.get("/api/v1/auth/me").json()["email"] == "reader@example.com"

    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "reader@example.com", "password": "safe-password-123"},
        ).status_code
        == 200
    )


def test_protected_endpoints_require_authentication(beta_harness: BetaHarness) -> None:
    client = beta_harness.client
    assert client.get("/api/v1/jobs").status_code == 401
    response = client.post(
        "/api/v1/uploads",
        files={"file": ("book.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_upload_validation_hash_and_path_safety(beta_harness: BetaHarness) -> None:
    client = beta_harness.client
    register(client)
    content = b"\xef\xbb\xbffirst\n\nsecond"
    saved = upload(client, "../../outside.txt", content)
    assert saved["original_filename"] == "outside.txt"
    assert saved["sha256"] == hashlib.sha256(content).hexdigest()
    files = list(beta_harness.storage.root.iterdir())
    assert len(files) == 1
    assert files[0].parent == beta_harness.storage.root
    assert files[0].name != "outside.txt"

    assert (
        client.post(
            "/api/v1/uploads",
            files={"file": ("book.md", b"hello", "text/markdown")},
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/api/v1/uploads",
            files={"file": ("empty.txt", b"", "text/plain")},
        ).json()["error"]["code"]
        == "empty_file"
    )
    assert (
        client.post(
            "/api/v1/uploads",
            files={"file": ("large.txt", b"x" * 65, "text/plain")},
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/v1/uploads",
            files={"file": ("invalid.txt", b"\xff\xfe\xfa", "text/plain")},
        ).json()["error"]["code"]
        == "invalid_text_encoding"
    )


def test_ownership_is_enforced_for_uploads_jobs_and_results(beta_harness: BetaHarness) -> None:
    client_a = beta_harness.client
    register(client_a, "a@example.com")
    saved = upload(client_a)
    job = create_job(client_a, saved["id"])

    client_a.post("/api/v1/auth/logout")
    register(client_a, "b@example.com")
    assert client_a.get(f"/api/v1/jobs/{job['id']}").status_code == 404
    assert client_a.get(f"/api/v1/jobs/{job['id']}/result").status_code == 404
    assert (
        client_a.post(
            "/api/v1/jobs",
            json={"upload_id": saved["id"], "idempotency_key": "request-key-b-001"},
        ).status_code
        == 404
    )


def test_job_creation_enqueues_once_and_is_idempotent(beta_harness: BetaHarness) -> None:
    client = beta_harness.client
    register(client)
    saved = upload(client)
    first = create_job(client, saved["id"])
    second = create_job(client, saved["id"])
    assert first["id"] == second["id"]
    assert first["status"] == "queued"
    assert beta_harness.queue.job_ids == [first["id"]]


def test_worker_progress_result_idempotency_and_no_billing(beta_harness: BetaHarness) -> None:
    client = beta_harness.client
    register(client)
    content = "第一行\n\n第三行".encode()
    saved = upload(client, content=content)
    job = create_job(client, saved["id"])
    observed_statuses = [client.get(f"/api/v1/jobs/{job['id']}").json()["status"]]

    original_read = beta_harness.storage.read

    def observe_running(storage_key: str) -> bytes:
        with beta_harness.database.session() as session:
            current = session.get(OnlineAnalysisJob, job["id"])
            assert current is not None
            observed_statuses.append(current.status)
        return original_read(storage_key)

    beta_harness.storage.read = observe_running  # type: ignore[method-assign]
    worker = Phase2AWorker(beta_harness.database, beta_harness.storage, lease_seconds=60)
    assert worker.process_job(job["id"]) is True
    observed_statuses.append(client.get(f"/api/v1/jobs/{job['id']}").json()["status"])
    assert observed_statuses == ["queued", "running", "succeeded"]

    result = client.get(f"/api/v1/jobs/{job['id']}/result").json()["result"]
    assert result["character_count"] == len(content.decode())
    assert result["nonempty_line_count"] == 2
    assert result["file_size_bytes"] == len(content)
    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["pipeline"] == "phase2a_smoke"
    assert result["real_ai_analysis"] is False
    assert result["billing_status"] == "not_billable"
    assert result["charged_cny"] == 0

    assert worker.process_job(job["id"]) is False
    with beta_harness.database.session() as session:
        stored_job = session.get(OnlineAnalysisJob, job["id"])
        assert stored_job is not None
        assert stored_job.attempt_count == 1
        for model in (
            WalletAccount,
            RechargeOrder,
            WalletTransaction,
            BillingReservation,
            ModelUsageLedger,
        ):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_worker_records_stable_failure_code(beta_harness: BetaHarness) -> None:
    client = beta_harness.client
    register(client)
    saved = upload(client)
    job = create_job(client, saved["id"])
    for path in beta_harness.storage.root.iterdir():
        path.unlink()

    worker = Phase2AWorker(beta_harness.database, beta_harness.storage, lease_seconds=60)
    assert worker.process_job(job["id"]) is False
    failed = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert failed["status"] == "failed"
    assert failed["progress"] == 100
    assert failed["public_error_code"] == "upload_missing"
