"""Provider Attempt / usage / cost accounting for native Overview (STEP 2.3-A4).

Fake Transport records every request for tests. Orchestrator persists
``model_invocations`` and links windows via ``provider_attempt_id``.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, ModelInvocation, WholeBookRunWindow, utc_now
from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    FIXTURE_ENGINE_VERSION,
    FIXTURE_PROMPT_VERSION,
)
from app.narrative_core.contracts.whole_book_overview_v1 import CONTRACT_VERSION
from app.narrative_core.services.whole_book_overview_engine_protocol import (
    ProviderTransport,
)


@dataclass
class TransportCallRecord:
    prompt: str
    model_options: dict[str, Any]
    response: dict[str, Any]
    latency_ms: int


@dataclass
class RecordingFakeTransport:
    """In-memory Fake ProviderTransport — records Attempt/usage/cost facts."""

    default_input_tokens: int = 128
    default_output_tokens: int = 64
    default_cost: float = 0.0
    currency: str = "CNY"
    fail_after: int | None = None
    calls: list[TransportCallRecord] = field(default_factory=list)

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def reset(self) -> None:
        self.calls.clear()

    def request(
        self,
        prompt: str,
        model_options: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        options = dict(model_options or {})
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise RuntimeError("fake transport forced failure")
        started = time.perf_counter()
        input_tokens = int(options.get("input_tokens") or self.default_input_tokens)
        output_tokens = int(options.get("output_tokens") or self.default_output_tokens)
        cost = float(options.get("cost") if options.get("cost") is not None else self.default_cost)
        response = {
            "ok": True,
            "text": str(options.get("text") or "fake-transport-ok"),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "estimated_cost": cost,
            "currency": self.currency,
            "request_id": f"fake-{len(self.calls) + 1}",
            "model": str(options.get("model") or FIXTURE_ENGINE_VERSION),
        }
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        self.calls.append(
            TransportCallRecord(
                prompt=str(prompt),
                model_options=options,
                response=dict(response),
                latency_ms=latency_ms,
            )
        )
        return response


class OverviewProviderAccounting:
    """Persist Provider Attempt rows and roll up window/run usage."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record_window_attempt(
        self,
        run: AnalysisRun,
        window: WholeBookRunWindow,
        *,
        transport: RecordingFakeTransport | ProviderTransport | None,
        prompt: str,
        model_options: Mapping[str, Any] | None = None,
        status: str = "succeeded",
        error_message: str | None = None,
    ) -> ModelInvocation:
        options = dict(model_options or {})
        response: Mapping[str, Any] = {}
        latency_ms = 0
        if transport is not None and status == "succeeded":
            response = transport.request(prompt, options)
            if isinstance(transport, RecordingFakeTransport) and transport.calls:
                latency_ms = transport.calls[-1].latency_ms
        elif isinstance(transport, RecordingFakeTransport) and status != "succeeded":
            # Still record a failed attempt without calling transport again.
            response = {
                "input_tokens": int(options.get("input_tokens") or transport.default_input_tokens),
                "output_tokens": 0,
                "total_tokens": int(options.get("input_tokens") or transport.default_input_tokens),
                "estimated_cost": 0.0,
                "currency": transport.currency,
                "request_id": f"fake-failed-{window.window_index}-{window.attempt_count}",
            }

        input_tokens = int(response.get("input_tokens") or options.get("input_tokens") or 0)
        output_tokens = int(response.get("output_tokens") or options.get("output_tokens") or 0)
        total_tokens = int(response.get("total_tokens") or (input_tokens + output_tokens))
        cost = float(response.get("estimated_cost") or options.get("cost") or 0.0)
        request_hash = hashlib.sha256(
            f"{run.id}|{window.window_index}|{window.input_hash}|{prompt[:200]}".encode("utf-8")
        ).hexdigest()

        attempt_no = int(window.attempt_count or 0) or 1
        invocation = ModelInvocation(
            run_id=int(run.id),
            task_type="whole_book_overview_window",
            provider_name=str(run.provider or FIXTURE_ENGINE_ID),
            model_name=str(run.model or FIXTURE_ENGINE_VERSION),
            prompt_version=str(run.prompt_version or FIXTURE_PROMPT_VERSION),
            schema_version=CONTRACT_VERSION,
            attempt_no=attempt_no,
            invocation_kind="window",
            request_hash=request_hash,
            input_snapshot_json=json.dumps(
                {
                    "window_index": window.window_index,
                    "input_hash": window.input_hash,
                    "prompt_preview": prompt[:240],
                },
                ensure_ascii=False,
            ),
            raw_response_text=str(response.get("text") or error_message or ""),
            parsed_response_json=json.dumps(dict(response), ensure_ascii=False),
            status=status,
            latency_ms=latency_ms,
            http_status_code=200 if status == "succeeded" else None,
            response_model_name=str(response.get("model") or run.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            request_id=str(response.get("request_id") or ""),
            estimated_cost=cost,
            currency=str(response.get("currency") or "CNY"),
            pricing_version="fixture-accounting-v1",
            created_at=utc_now(),
        )
        self._session.add(invocation)
        self._session.flush()

        window.provider_attempt_id = int(invocation.id)
        window.token_input = int(window.token_input or 0) + input_tokens
        window.token_output = int(window.token_output or 0) + output_tokens
        window.cost = float(window.cost or 0.0) + cost
        self._session.flush()
        return invocation

    def run_usage_totals(self, run_id: int) -> dict[str, float | int]:
        windows = list(
            self._session.query(WholeBookRunWindow).filter(WholeBookRunWindow.run_id == int(run_id))
        )
        token_in = sum(int(w.token_input or 0) for w in windows)
        token_out = sum(int(w.token_output or 0) for w in windows)
        cost = sum(float(w.cost or 0.0) for w in windows)
        return {
            "actual_tokens": token_in + token_out,
            "token_input": token_in,
            "token_output": token_out,
            "actual_cost": cost,
        }


__all__ = [
    "OverviewProviderAccounting",
    "RecordingFakeTransport",
    "TransportCallRecord",
]
