from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import ValidationError

from storylens_online.contracts.beta import (
    AuthenticatedUser,
    AuthSession,
    PocketBaseAuthResponse,
)
from storylens_online.errors import PublicApiError


class AuthGateway(Protocol):
    async def register(self, email: str, password: str) -> AuthSession: ...

    async def login(self, email: str, password: str) -> AuthSession: ...

    async def authenticate(self, token: str) -> AuthSession: ...


class PocketBaseAuthClient:
    def __init__(
        self,
        base_url: str,
        collection: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._collection = collection
        self._timeout_seconds = timeout_seconds

    async def register(self, email: str, password: str) -> AuthSession:
        url = f"{self._base_url}/api/collections/{self._collection}/records"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    url,
                    json={
                        "email": email,
                        "emailVisibility": False,
                        "password": password,
                        "passwordConfirm": password,
                    },
                )
        except httpx.HTTPError as exc:
            raise PublicApiError(
                503,
                "auth_service_unavailable",
                "认证服务暂时不可用，请稍后重试。",
            ) from exc
        if response.status_code >= 400:
            raise PublicApiError(
                400,
                "registration_failed",
                "注册失败，请检查邮箱是否已使用以及密码是否符合要求。",
            )
        return await self.login(email, password)

    async def login(self, email: str, password: str) -> AuthSession:
        url = f"{self._base_url}/api/collections/{self._collection}/auth-with-password"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    url,
                    json={"identity": email, "password": password},
                )
        except httpx.HTTPError as exc:
            raise PublicApiError(
                503,
                "auth_service_unavailable",
                "认证服务暂时不可用，请稍后重试。",
            ) from exc
        if response.status_code >= 400:
            raise PublicApiError(401, "invalid_credentials", "邮箱或密码不正确。")
        return self._validated_session(response)

    async def authenticate(self, token: str) -> AuthSession:
        url = f"{self._base_url}/api/collections/{self._collection}/auth-refresh"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(url, headers={"Authorization": token})
        except httpx.HTTPError as exc:
            raise PublicApiError(
                503,
                "auth_service_unavailable",
                "认证服务暂时不可用，请稍后重试。",
            ) from exc
        if response.status_code >= 400:
            raise PublicApiError(401, "authentication_required", "登录已失效，请重新登录。")
        return self._validated_session(response)

    @staticmethod
    def _validated_session(response: httpx.Response) -> AuthSession:
        try:
            auth = PocketBaseAuthResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise PublicApiError(
                503,
                "auth_service_invalid_response",
                "认证服务响应异常，请稍后重试。",
            ) from exc
        return AuthSession(
            token=auth.token,
            user=AuthenticatedUser(id=auth.record.id, email=auth.record.email.lower()),
        )
