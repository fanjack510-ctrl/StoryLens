from __future__ import annotations

from pydantic import SecretStr
from storylens_online.services.afdian import build_open_api_payload


def test_afdian_signature_is_deterministic_and_never_returns_token() -> None:
    payload = build_open_api_payload(
        user_id="publisher",
        api_token=SecretStr("super-secret"),
        params={"out_trade_no": "ORDER-001"},
        timestamp=1_725_000_000,
    )
    assert payload == build_open_api_payload(
        user_id="publisher",
        api_token=SecretStr("super-secret"),
        params={"out_trade_no": "ORDER-001"},
        timestamp=1_725_000_000,
    )
    assert payload["user_id"] == "publisher"
    assert "super-secret" not in str(payload)
    assert len(str(payload["sign"])) == 32
