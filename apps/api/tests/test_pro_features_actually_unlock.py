"""付了钱的人，功能到底解不解锁。

四个 Pro 功能的门我都验过「没授权时挡住」——那是容易验的一半。真正会变成事故的是另一半：
**有授权时放不放行**。它只在有人付过钱之后才会暴露，而那时候已经晚了。

这里特别盯一件事：`common_patterns` 这个能力键是共性视图做出来之后才加进
`CANONICAL_FEATURES` 的。授权验证以**载荷里的 features 为准**，常量只是没有载荷时的兜底。
也就是说，在加这个键**之前**签发出去的授权码里没有它——老客户点共性视图会被拒，
而他明明付过钱。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services import entitlement
from app.services.license_crypto import (
    CANONICAL_FEATURES,
    build_unsigned_payload,
    encode_license,
    private_key_b64url,
    public_key_b64url,
)


@pytest.fixture()
def license_keypair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """一副只在测试里存在的签名密钥。

    和 `test_pro_whole_book_insights_gate.py` 里那份是同一套做法。没有把它提到 conftest：
    授权是全局单例状态，一个被所有测试自动看见的密钥装置，会让「这条测试到底有没有授权」
    变得要翻 conftest 才知道。
    """
    priv = Ed25519PrivateKey.generate()
    key_id = "pro-unlock-test-001"
    config = {
        "keys": [
            {
                "key_id": key_id,
                "signature_version": 1,
                "algorithm": "ed25519",
                "environment": "test",
                "public_key_b64url": public_key_b64url(priv.public_key()),
                "status": "active",
            }
        ],
        "commerce": {
            "afdian_product_url": "https://afdian.com/item/test",
            "product_code": "storylens_pro",
        },
    }
    path = tmp_path / "license_public_keys.test.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: False)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: path)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    return priv, key_id, private_key_b64url(priv)

#: 共性视图之前就已经在签发的那份清单。用它模拟一个老客户手里的授权码。
FEATURES_BEFORE_COMMON_PATTERNS = (
    "whole_book_analysis",
    "narrative_asset_library",
    "story_lab",
    "cross_book_search",
    "advanced_export",
    "pro_whole_book_insights",
)

#: 这一轮做出来的、要卖钱的东西。
PRO_FEATURES_SHIPPED_NOW = ("advanced_export", "common_patterns", "cross_book_search")


def _activate(session, license_keypair, features=None) -> None:
    priv, key_id, _ = license_keypair
    payload = build_unsigned_payload(major_version=1, key_id=key_id, features=features)
    entitlement.activate_license_code(session, encode_license(payload, priv))


def _session(client):
    from app.db.session import get_db

    return next(client.app.dependency_overrides[get_db]())


@pytest.mark.parametrize("feature", PRO_FEATURES_SHIPPED_NOW)
def test_a_fresh_licence_unlocks_every_shipped_pro_feature(
    client, license_keypair, feature
) -> None:
    """新签发的授权码要能打开这一轮做的每一个功能。

    只验「没授权时被挡住」是验了容易的那一半。放行这一半没验过的话，
    第一个发现问题的人是付了钱之后点下去的那个。
    """
    session = _session(client)
    _activate(session, license_keypair)
    gate = entitlement.can_use_feature(session, feature)
    assert gate.get("enabled") is True, f"{feature} 没解锁：{gate}"


@pytest.mark.parametrize("feature", PRO_FEATURES_SHIPPED_NOW)
def test_without_a_licence_every_pro_feature_is_shut(client, feature) -> None:
    session = _session(client)
    gate = entitlement.can_use_feature(session, feature)
    assert gate.get("enabled") is False
    # 拒绝的理由要是「没授权」，不是「这个功能不存在」——后者说明能力没注册，
    # 那样连付了钱的人也会被拒。
    assert gate.get("reason") != "FEATURE_UNKNOWN", f"{feature} 没在能力注册表里"


def test_an_older_licence_still_opens_what_it_was_sold_with(
    client, license_keypair
) -> None:
    """老授权码里没有的键，不能反过来把它本来买到的东西也关掉。"""
    session = _session(client)
    _activate(session, license_keypair, features=FEATURES_BEFORE_COMMON_PATTERNS)
    for feature in ("advanced_export", "cross_book_search"):
        gate = entitlement.can_use_feature(session, feature)
        assert gate.get("enabled") is True, f"老授权打不开 {feature}：{gate}"


def test_an_older_licence_also_opens_features_added_after_it_was_issued(
    client, license_keypair
) -> None:
    """在付费期内的人，点新功能不该被拒。

    授权码里的 features 是**签发那一刻**的清单。按它判定的话，每加一个 Pro 功能，
    所有已签发的码都打不开它——而持有者明明在付费期内。他不会来投诉，
    只会觉得这软件坏了。

    `common_patterns` 就是那个例子：它是共性视图做完之后才进清单的。
    语义已定为「授权在有效期内，即享当期 Pro 全集」。
    """
    session = _session(client)
    _activate(session, license_keypair, features=FEATURES_BEFORE_COMMON_PATTERNS)
    gate = entitlement.can_use_feature(session, "common_patterns")
    assert gate.get("enabled") is True, f"付费期内却被拒：{gate}"


def test_an_expired_licence_opens_nothing(client, license_keypair) -> None:
    """并集只对**有效**的授权生效。

    上一条把「载荷里没有」放行了。这一条守住另一边：过期或吊销之后，
    并集不能把它变成永久授权——那会让「有效期」这三个字失去意义。
    """
    from app.db.models import LocalLicense

    session = _session(client)
    _activate(session, license_keypair)
    row = session.query(LocalLicense).first()
    assert row is not None
    row.license_status = "expired"
    session.flush()
    for feature in PRO_FEATURES_SHIPPED_NOW:
        gate = entitlement.can_use_feature(session, feature)
        assert gate.get("enabled") is False, f"过期授权仍然打开了 {feature}"


def test_the_canonical_list_covers_everything_we_actually_gate(client) -> None:
    """卖的东西必须在清单里。

    不在清单里的键，新签发的授权码也不会带上它——那样连刚付完钱的人都打不开。
    """
    for feature in PRO_FEATURES_SHIPPED_NOW:
        assert feature in CANONICAL_FEATURES, f"{feature} 不在 CANONICAL_FEATURES 里"
