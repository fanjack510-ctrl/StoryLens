from __future__ import annotations

import json

import httpx
import pytest
from storylens_online.errors import PublicApiError
from storylens_online.services import auth as auth_module
from storylens_online.services.auth import PocketBaseAuthClient


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: httpx.MockTransport,
) -> None:
    original_client = httpx.AsyncClient

    def client_factory(*, timeout: float) -> httpx.AsyncClient:
        return original_client(timeout=timeout, transport=handler)

    monkeypatch.setattr(auth_module.httpx, "AsyncClient", client_factory)


@pytest.mark.asyncio
async def test_pocketbase_register_then_password_login_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/records"):
            payload = json.loads(request.content)
            assert payload == {
                "email": "reader@example.com",
                "emailVisibility": False,
                "password": "safe-password-123",
                "passwordConfirm": "safe-password-123",
            }
            return httpx.Response(200, json={"id": "user-1"})
        assert request.url.path.endswith("/auth-with-password")
        assert json.loads(request.content) == {
            "identity": "reader@example.com",
            "password": "safe-password-123",
        }
        return httpx.Response(
            200,
            json={
                "token": "pocketbase-session-token",
                "record": {"id": "user-1", "email": "reader@example.com"},
            },
        )

    _install_transport(monkeypatch, httpx.MockTransport(handle))
    client = PocketBaseAuthClient("http://pocketbase:8090", "users")

    session = await client.register("reader@example.com", "safe-password-123")

    assert session.user.id == "user-1"
    assert [request.url.path for request in requests] == [
        "/api/collections/users/records",
        "/api/collections/users/auth-with-password",
    ]


@pytest.mark.asyncio
async def test_pocketbase_refresh_uses_internal_token_and_returns_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            httpx.Response(
                200,
                json={
                    "token": "rotated-pocketbase-token",
                    "record": {"id": "user-1", "email": "READER@example.com"},
                },
            ),
            httpx.Response(401, json={"message": "internal PocketBase detail"}),
        ]
    )

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/collections/users/auth-refresh"
        assert request.headers["Authorization"] == "private-session-token"
        return next(responses)

    _install_transport(monkeypatch, httpx.MockTransport(handle))
    client = PocketBaseAuthClient("http://pocketbase:8090", "users")

    session = await client.authenticate("private-session-token")
    assert session.token == "rotated-pocketbase-token"
    assert session.user.email == "reader@example.com"

    with pytest.raises(PublicApiError) as error:
        await client.authenticate("private-session-token")
    assert error.value.code == "authentication_required"
    assert "PocketBase" not in error.value.message
