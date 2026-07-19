# -*- coding: utf-8 -*-
"""Provider transport retry policy (DEFECT-CANARY-009 / change v1.0.4).

Only applies to retryable transport/provider errors. Validation and business
failures keep their existing repair/abort paths and do not use this backoff.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from app.model_gateway.base import ProviderRequestError


@dataclass(frozen=True)
class TransportRetryPolicy:
    """Cloud transport retry envelope (per phase).

    DEFECT-010: normal generation and structural repair each get an independent
    transport attempt budget of ``max_attempts`` (default 3). Delays apply before
    ``provider_retry`` / ``repair_provider_retry`` only — not before validation
    repair rounds.
    """

    max_attempts: int = 3
    # After 1st failure → first retry waits ~2–4s
    delay_1_min_seconds: float = 2.0
    delay_1_max_seconds: float = 4.0
    # After 2nd failure → second retry waits ~8–12s
    delay_2_min_seconds: float = 8.0
    delay_2_max_seconds: float = 12.0


DEFAULT_TRANSPORT_RETRY_POLICY = TransportRetryPolicy()


def transport_retry_policy_from_settings(settings: object) -> TransportRetryPolicy:
    return TransportRetryPolicy(
        max_attempts=int(getattr(settings, "aliyun_transport_max_attempts", 3)),
        delay_1_min_seconds=float(getattr(settings, "aliyun_transport_retry_delay_1_min", 2.0)),
        delay_1_max_seconds=float(getattr(settings, "aliyun_transport_retry_delay_1_max", 4.0)),
        delay_2_min_seconds=float(getattr(settings, "aliyun_transport_retry_delay_2_min", 8.0)),
        delay_2_max_seconds=float(getattr(settings, "aliyun_transport_retry_delay_2_max", 12.0)),
    )


def compute_provider_retry_delay_seconds(
    failed_attempt_no: int,
    policy: TransportRetryPolicy | None = None,
    *,
    rng: random.Random | None = None,
) -> float:
    """Return jittered backoff after a failed attempt before the next provider_retry.

    failed_attempt_no=1 → delay before 2nd attempt (2–4s)
    failed_attempt_no=2 → delay before 3rd attempt (8–12s)
    """
    policy = policy or DEFAULT_TRANSPORT_RETRY_POLICY
    sampler = rng if rng is not None else random
    if failed_attempt_no == 1:
        low, high = policy.delay_1_min_seconds, policy.delay_1_max_seconds
    elif failed_attempt_no == 2:
        low, high = policy.delay_2_min_seconds, policy.delay_2_max_seconds
    else:
        return 0.0
    if high < low:
        low, high = high, low
    if high <= 0:
        return 0.0
    return float(sampler.uniform(low, high))


def should_retry_provider_error(error: ProviderRequestError | None) -> bool:
    """Only clearly retryable transport/HTTP errors continue with backoff."""
    if error is None:
        return False
    return bool(error.retryable)


# HTTP statuses that remain retryable under TRANSPORT_HTTP / PROVIDER_* codes.
RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
NON_RETRYABLE_HTTP_STATUSES = frozenset({401, 403})
