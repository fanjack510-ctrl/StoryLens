from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class AfdianSku(BaseModel):
    sku_id: str = ""
    count: int = 0
    name: str = ""


class AfdianOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")

    out_trade_no: str = Field(min_length=1, max_length=64)
    user_id: str = ""
    user_private_id: str = ""
    plan_id: str = ""
    total_amount: Decimal = Field(ge=Decimal(0))
    show_amount: Decimal = Field(default=Decimal(0), ge=Decimal(0))
    status: int
    product_type: int = 0
    sku_detail: list[AfdianSku] = Field(default_factory=list)


class AfdianOrderList(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    orders: list[AfdianOrder] = Field(default_factory=list, alias="list")


class AfdianQueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ec: int
    em: str = ""
    data: AfdianOrderList | None = None


class VerifiedAfdianOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    out_trade_no: str
    plan_id: str
    user_private_id: str
    paid_amount_cny: Decimal
    sku_ids: tuple[str, ...]


def build_open_api_payload(
    *, user_id: str, api_token: SecretStr, params: dict[str, Any], timestamp: int | None = None
) -> dict[str, str | int]:
    """Build the legacy Afdian OpenAPI signature without exposing the API token."""

    ts = int(timestamp if timestamp is not None else time.time())
    params_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    signing_text = f"{api_token.get_secret_value()}params{params_json}ts{ts}user_id{user_id}"
    signature = hashlib.md5(signing_text.encode("utf-8"), usedforsecurity=False).hexdigest()
    return {"user_id": user_id, "params": params_json, "ts": ts, "sign": signature}


class AfdianClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        user_id: str,
        api_token: SecretStr,
        allowed_plan_ids: frozenset[str],
        timeout_seconds: float = 15.0,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._user_id = user_id
        self._api_token = api_token
        self._allowed_plan_ids = allowed_plan_ids
        self._timeout_seconds = timeout_seconds

    async def query_paid_order(self, out_trade_no: str) -> VerifiedAfdianOrder:
        payload = build_open_api_payload(
            user_id=self._user_id,
            api_token=self._api_token,
            params={"out_trade_no": out_trade_no},
        )
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(f"{self._api_base_url}/query-order", json=payload)
            response.raise_for_status()
        body = AfdianQueryResponse.model_validate(response.json())
        if body.ec != 200:
            raise ValueError(f"Afdian query failed with ec={body.ec}")
        orders = list(body.data.orders if body.data else [])
        matching = [order for order in orders if order.out_trade_no == out_trade_no]
        if len(matching) != 1:
            raise ValueError("Afdian order was not found or was ambiguous")
        order = matching[0]
        if order.status != 2:
            raise ValueError("Afdian order is not paid")
        if self._allowed_plan_ids and order.plan_id not in self._allowed_plan_ids:
            raise ValueError("Afdian order plan is not an allowed StoryLens recharge product")
        return VerifiedAfdianOrder(
            out_trade_no=order.out_trade_no,
            plan_id=order.plan_id,
            user_private_id=order.user_private_id,
            paid_amount_cny=order.total_amount,
            sku_ids=tuple(item.sku_id for item in order.sku_detail if item.sku_id),
        )
