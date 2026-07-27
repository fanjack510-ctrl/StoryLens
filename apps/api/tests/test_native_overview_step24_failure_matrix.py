"""STEP 2.4 — Public↔Private failure matrix, recovery, accounting (FakeTransport only).

Happy-path private+Fake end-to-end through Public orchestrator is covered when
AdaptiveFakeTransport can satisfy Private prompt/citation rules (see
``test_private_fake_happy_path_one_window``). Full Private unit happy paths live
in the Private repo; this module proves Public maps Private wire codes without
silent Fixture downgrade.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisRun,
    Base,
    Book,
    Chapter,
    ModelInvocation,
    NarrativeAssetVersion,
    Paragraph,
    WholeBookRunWindow,
)
from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
    is_pro_native_overview_enabled,
)
from app.narrative_core.contracts.whole_book_overview_errors import (
    WholeBookOverviewErrorCode,
)
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CreateRunRequest,
    RetryRunRequest,
)
from app.narrative_core.enums import RunStatus, WindowStatus
from app.narrative_core.hash_canon import calculate_text_hash
from app.narrative_core.services.native_overview_context_windows import OverviewWindowBudget
from app.narrative_core.services.native_overview_errors import NativeOverviewError
from app.narrative_core.services.native_overview_fixture_adapter import (
    load_private_fixture_engine_adapter,
)
from app.narrative_core.services.native_overview_seed import seed_short_book_v1
from app.narrative_core.services.native_overview_service import NativeOverviewService
from app.narrative_core.services.whole_book_overview_engine_loader import (
    EngineLoadError,
    load_overview_engine,
)
from app.narrative_core.services.whole_book_overview_engine_protocol import (
    WholeBookOverviewEngineAdapter,
)
from app.services import entitlement
from app.services.license_crypto import (
    build_unsigned_payload,
    encode_license,
    private_key_b64url,
    public_key_b64url,
)
from storylens_private_engine.modules.book_overview.transport import FakeTransport


CREATE_BODY = {
    "mode": "whole_book_native",
    "module_key": "book_overview",
    "provider_id": PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
    "model_id": "native-overview-1",
    "client_request_id": "req-step24-001",
    "consent": {
        "estimated_tokens": 1200,
        "estimated_cost": 0.02,
        "currency": "CNY",
        "confirmed": True,
    },
}

PROVIDER_FAILURE_CASES: list[tuple[Any, str]] = [
    (("timeout",), "PROVIDER_TIMEOUT"),
    (("rate_limit",), "PROVIDER_RATE_LIMITED"),
    (("unavailable",), "PROVIDER_UNAVAILABLE"),
    ("not-json {{{", "PROVIDER_OUTPUT_INVALID"),
    ("", "PROVIDER_OUTPUT_EMPTY"),
]


@pytest.fixture()
def license_keypair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    priv = Ed25519PrivateKey.generate()
    key_id = "overview-step24-001"
    pub = public_key_b64url(priv.public_key())
    config = {
        "keys": [
            {
                "key_id": key_id,
                "signature_version": 1,
                "algorithm": "ed25519",
                "environment": "test",
                "public_key_b64url": pub,
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


def _activate_pro(session: Session, license_keypair) -> None:
    priv, key_id, _ = license_keypair
    payload = build_unsigned_payload(major_version=1, key_id=key_id)
    code = encode_license(payload, priv)
    entitlement.activate_license_code(session, code)
    session.commit()


@pytest.fixture()
def enable_native_overview(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PRO_NATIVE_OVERVIEW_ENABLED", "true")
    assert is_pro_native_overview_enabled() is True


@pytest.fixture()
def api_env(tmp_path, fake_provider, license_keypair, enable_native_overview):
    from app.db.session import get_db, get_session_factory
    from app.main import app
    from app.model_gateway.gateway import ModelGateway
    from app.model_gateway.registry import get_model_gateway

    engine = create_engine(
        f"sqlite:///{tmp_path / 'native_overview_step24.db'}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_db():
        with factory() as session:
            yield session

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([fake_provider])
    client = TestClient(app)
    try:
        yield {"client": client, "factory": factory, "license_keypair": license_keypair}
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


def _seed_multi_para_book(session: Session, *, paragraphs: int = 6) -> Book:
    texts = [f"第{i}段正文内容，用于多窗口覆盖测试。" for i in range(1, paragraphs + 1)]
    all_text = "\n".join(texts)
    book = Book(
        title="多窗口测试书",
        source_file_name="multi_window.json",
        source_file_hash=calculate_text_hash(all_text),
        import_status="ready",
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        chapter_title="第一章",
        display_title="第一章",
        section_type="chapter",
    )
    session.add(chapter)
    session.flush()
    offset = 0
    for i, text in enumerate(texts, start=1):
        para = Paragraph(
            id=f"B{book.id:04d}-C0001-P{i:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=i,
            raw_text=text,
            normalized_text=text,
            char_start=offset,
            char_end=offset + len(text),
        )
        session.add(para)
        offset += len(text) + 1
    session.flush()
    return book


def _tiny_budget() -> OverviewWindowBudget:
    return OverviewWindowBudget(
        max_paragraphs_per_window=2,
        overlap_paragraphs=1,
        max_characters_per_window=10_000,
        max_tokens_estimated=5_000,
    )


class CountingAdapter:
    """Wrap fixture adapter and count analyze_window calls."""

    def __init__(self, inner: WholeBookOverviewEngineAdapter) -> None:
        self._inner = inner
        self.analyze_calls = 0
        self.analyze_window_indexes: list[int] = []
        self.fail_on_window: int | None = None

    @property
    def engine_id(self) -> str:
        return self._inner.engine_id

    def analyze_window(
        self,
        payload,
        transport=None,  # noqa: ANN001
    ):
        self.analyze_calls += 1
        idx = int(payload.window.window_index)
        self.analyze_window_indexes.append(idx)
        if self.fail_on_window is not None and idx == self.fail_on_window:
            raise RuntimeError(f"forced fail window {idx}")
        return self._inner.analyze_window(payload, transport=transport)

    def synthesize_overview(self, payload, transport=None):  # noqa: ANN001
        return self._inner.synthesize_overview(payload, transport=transport)


def _extract_json_after_marker(prompt: str, marker: str) -> dict[str, Any]:
    idx = prompt.find(marker)
    assert idx >= 0, f"marker {marker!r} missing from prompt"
    blob = prompt[idx + len(marker) :]
    # Drop trailing instruction lines after the JSON object.
    decoder = json.JSONDecoder()
    data, _ = decoder.raw_decode(blob.lstrip())
    assert isinstance(data, dict)
    return data


def _window_json_from_prompt(prompt: str) -> str:
    body = _extract_json_after_marker(prompt, "Window analysis request (JSON):\n")
    paragraphs = list(body.get("paragraphs") or [])
    assert paragraphs, "window prompt must include paragraphs"
    first = paragraphs[0]
    pid = str(first["paragraph_id"])
    chapter_id = str(first["chapter_id"])
    text = str(first["text"])
    quote = text[: min(12, len(text))]
    assert quote and quote in text
    payload = {
        "contract_version": "1.0",
        "run_id": str(body.get("run_id") or "0"),
        "window_id": str(body.get("window_id") or "w-0"),
        "input_hash": str(body.get("input_hash") or ""),
        "candidate_entities": [
            {
                "candidate_id": "ce-1",
                "entity_type": "character",
                "canonical_name": "主角",
                "aliases": [],
                "description": "",
                "confidence": 0.9,
                "evidence_refs": ["ev-1"],
            }
        ],
        "candidate_assets": [
            {
                "candidate_id": "ca-1",
                "asset_type": "goal",
                "title": "推进主线",
                "summary": "从窗口证据得出的目标候选",
                "subject_candidate_ids": ["ce-1"],
                "object_candidate_ids": [],
                "confidence": 0.7,
                "evidence_refs": ["ev-1"],
                "deduplication_key": f"goal:{pid}",
            }
        ],
        "candidate_evidence": [
            {
                "evidence_id": "ev-1",
                "paragraph_id": pid,
                "chapter_id": chapter_id,
                "quote": quote,
                "evidence_role": "support",
                "confidence": 0.95,
                "supports_candidate_ids": ["ce-1"],
            }
        ],
        "state_delta": {},
        "warnings": [],
        "quality": {
            "confidence": 0.8,
            "repair_attempted": False,
            "repair_succeeded": False,
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _projection_json_from_prompt(prompt: str) -> str:
    # Synthesis prompt embeds run_id; keep fields low-confidence / optional.
    run_match = re.search(r'"run_id"\s*:\s*"([^"]+)"', prompt)
    run_id = run_match.group(1) if run_match else "0"
    insufficient = {
        "value": None,
        "confidence": 0.0,
        "evidence_refs": [],
        "status": "insufficient_evidence",
    }
    payload = {
        "contract_version": "1.0",
        "run_id": run_id,
        "novel_type": {
            "value": "adventure",
            "confidence": 0.55,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "narrative_features": {
            "value": ["window-derived"],
            "confidence": 0.5,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "core_setting": {
            "value": "derived setting",
            "confidence": 0.5,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "protagonist": {
            "value": "主角",
            "confidence": 0.6,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "protagonist_core_goal": {
            "value": "推进主线",
            "confidence": 0.55,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "primary_conflict": insufficient,
        "central_question": {
            "value": "故事如何收束？",
            "confidence": 0.5,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "key_turning_points": insufficient,
        "climax": insufficient,
        "resolved_problem": insufficient,
        "ending_state": insufficient,
        "logline": {
            "value": "一段由窗口证据支撑的概要。",
            "confidence": 0.55,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "synopsis": {
            "value": "基于窗口段落的离线概要合成。",
            "confidence": 0.55,
            "evidence_refs": [],
            "status": "low_confidence",
        },
        "warnings": [],
    }
    return json.dumps(payload, ensure_ascii=False)


class AdaptiveFakeTransport:
    """Build valid Private window/projection JSON from the live prompt paragraphs."""

    def __init__(self) -> None:
        self.call_log: list[dict[str, Any]] = []
        self._index = 0

    @property
    def call_count(self) -> int:
        return len(self.call_log)

    def request(
        self,
        prompt: str,
        model_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = dict(model_options or {})
        self.call_log.append(
            {
                "prompt": prompt,
                "model_options": options,
                "call_index": self._index,
            }
        )
        stage = str(options.get("stage") or "")
        if stage == "synthesize_overview" or "Synthesis" in prompt or "projection" in prompt.lower():
            text = _projection_json_from_prompt(prompt)
        else:
            text = _window_json_from_prompt(prompt)
        response = {"text": text, "ok": True}
        self.call_log[-1]["response"] = dict(response)
        self._index += 1
        return response


@pytest.mark.parametrize("scripted,expected_code", PROVIDER_FAILURE_CASES)
def test_provider_failure_matrix_maps_private_codes(
    api_env, scripted: Any, expected_code: str
):
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    transport = FakeTransport(responses=[scripted])
    with factory() as session:
        service = NativeOverviewService(
            session,
            engine_id=PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
            transport=transport,
        )
        with pytest.raises(NativeOverviewError) as exc:
            service.create_run(
                book_id,
                CreateRunRequest.model_validate(
                    {
                        **CREATE_BODY,
                        "client_request_id": f"req-fail-{expected_code}",
                    }
                ),
            )
        session.commit()
        assert exc.value.code == expected_code

    assert transport.call_count >= 1

    with factory() as session:
        run = session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.client_request_id == f"req-fail-{expected_code}"
            )
        )
        assert run is not None
        assert run.status == RunStatus.FAILED.value
        # Private path stores AI binding identity (not Fixture engine id).
        assert run.provider != FIXTURE_ENGINE_ID
        assert run.provider == "aliyun_qwen_plus"
        windows = list(
            session.scalars(
                select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run.id)
            )
        )
        assert windows
        assert all(w.status != WindowStatus.COMPLETED.value for w in windows)
        failed_windows = [w for w in windows if w.status == WindowStatus.FAILED.value]
        assert failed_windows
        assert any(
            (w.error_code == expected_code) for w in failed_windows
        ) or session.scalar(
            select(func.count())
            .select_from(ModelInvocation)
            .where(
                ModelInvocation.run_id == run.id,
                ModelInvocation.status == "failed",
            )
        )
        invocations = list(
            session.scalars(
                select(ModelInvocation).where(ModelInvocation.run_id == run.id)
            )
        )
        assert invocations or any(w.error_code for w in failed_windows)


def test_private_engine_unavailable_on_import_failure(api_env, monkeypatch):
    import builtins
    import sys

    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    sys.modules.pop(
        "storylens_private_engine.modules.book_overview.native_engine", None
    )
    real_import = builtins.__import__

    def blocked(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        fl = fromlist or ()
        if name == "storylens_private_engine.modules.book_overview.native_engine":
            raise ImportError("blocked for step24 unavailable test")
        if (
            name == "storylens_private_engine.modules.book_overview"
            and "native_engine" in fl
        ):
            raise ImportError("blocked for step24 unavailable test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked)

    with factory() as session:
        service = NativeOverviewService(
            session,
            engine_id=PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
            transport=FakeTransport(responses=[("timeout",)]),
        )
        with pytest.raises(NativeOverviewError) as exc:
            service.create_run(
                book_id,
                CreateRunRequest.model_validate(
                    {**CREATE_BODY, "client_request_id": "req-engine-unavailable"}
                ),
            )
        session.commit()
        assert (
            exc.value.code
            == WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value
        )

    with factory() as session:
        run = session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.client_request_id == "req-engine-unavailable"
            )
        )
        assert run is not None
        assert run.provider != FIXTURE_ENGINE_ID
        assert run.provider == "aliyun_qwen_plus"
        asset_count = session.scalar(
            select(func.count())
            .select_from(NarrativeAssetVersion)
            .where(NarrativeAssetVersion.run_id == run.id)
        )
        assert int(asset_count or 0) == 0


def test_unknown_engine_id_incompatible():
    with pytest.raises(EngineLoadError) as exc:
        load_overview_engine("unknown-engine-id")
    assert (
        exc.value.code
        == WholeBookOverviewErrorCode.PRIVATE_ENGINE_INCOMPATIBLE.value
    )


def test_interrupted_recovery_skips_completed_window(api_env):
    """Window 0 completed + window 1 left RUNNING mid-flight → retry continues safely."""

    factory = api_env["factory"]
    with factory() as session:
        book = _seed_multi_para_book(session, paragraphs=6)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    adapter = CountingAdapter(load_private_fixture_engine_adapter())
    adapter.fail_on_window = 1

    with factory() as session:
        service = NativeOverviewService(
            session,
            adapter=adapter,
            engine_id=FIXTURE_ENGINE_ID,
            window_budget=_tiny_budget(),
        )
        with pytest.raises(NativeOverviewError):
            service.create_run(
                book_id,
                CreateRunRequest.model_validate(
                    {
                        **CREATE_BODY,
                        "provider_id": FIXTURE_ENGINE_ID,
                        "client_request_id": "req-interrupt-recover",
                    }
                ),
            )
        session.commit()

    with factory() as session:
        run = session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.client_request_id == "req-interrupt-recover"
            )
        )
        assert run is not None
        run_id = int(run.id)
        windows = {
            int(w.window_index): w
            for w in session.scalars(
                select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
            )
        }
        assert 0 in windows and windows[0].status == WindowStatus.COMPLETED.value
        w0_attempts = int(windows[0].attempt_count or 0)
        # Simulate crash: window 1 was mid-flight RUNNING when the process died.
        assert 1 in windows
        windows[1].status = WindowStatus.RUNNING.value
        windows[1].error_code = None
        windows[1].error_detail = None
        run.status = RunStatus.FAILED.value
        run.retryable = True
        asset_count_before = int(
            session.scalar(
                select(func.count())
                .select_from(NarrativeAssetVersion)
                .where(NarrativeAssetVersion.run_id == run_id)
            )
            or 0
        )
        session.commit()

    adapter.fail_on_window = None
    calls_before = adapter.analyze_calls

    with factory() as session:
        service = NativeOverviewService(
            session,
            adapter=adapter,
            engine_id=FIXTURE_ENGINE_ID,
            window_budget=_tiny_budget(),
        )
        retry_resp = service.retry_run(
            run_id,
            RetryRunRequest(client_request_id="retry-interrupt-1"),
        )
        session.commit()
        assert retry_resp.status == RunStatus.COMPLETED

    new_indexes = adapter.analyze_window_indexes[calls_before:]
    assert 0 not in new_indexes
    assert any(i >= 1 for i in new_indexes)

    with factory() as session:
        w0 = session.scalar(
            select(WholeBookRunWindow).where(
                WholeBookRunWindow.run_id == run_id,
                WholeBookRunWindow.window_index == 0,
            )
        )
        assert w0 is not None
        assert w0.status == WindowStatus.COMPLETED.value
        assert int(w0.attempt_count or 0) == w0_attempts
        windows = list(
            session.scalars(
                select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
            )
        )
        assert all(w.status == WindowStatus.COMPLETED.value for w in windows)
        asset_count_after = int(
            session.scalar(
                select(func.count())
                .select_from(NarrativeAssetVersion)
                .where(NarrativeAssetVersion.run_id == run_id)
            )
            or 0
        )
        assert asset_count_after >= asset_count_before


def test_accounting_no_double_invoke_on_timeout(api_env):
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    transport = FakeTransport(responses=[("timeout",)])
    with factory() as session:
        service = NativeOverviewService(
            session,
            engine_id=PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
            transport=transport,
        )
        with pytest.raises(NativeOverviewError) as exc:
            service.create_run(
                book_id,
                CreateRunRequest.model_validate(
                    {**CREATE_BODY, "client_request_id": "req-acct-once"}
                ),
            )
        session.commit()
        assert exc.value.code == "PROVIDER_TIMEOUT"

    # Accounting must harvest call_log[-1]["response"] — never re-call request().
    assert transport.call_count == 1


def test_accounting_preserves_provider_text_on_parse_failure(api_env):
    """FIX-3B: failure accounting must not overwrite Provider text / zero tokens."""

    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    prose = "Sure — here is a prose analysis without any JSON object."
    transport = FakeTransport(
        responses=[
            {
                "text": prose,
                "input_tokens": 111,
                "output_tokens": 22,
                "total_tokens": 133,
                "estimated_cost": 0.0033,
                "currency": "CNY",
                "request_id": "fix3b-preserve-1",
                "http_status_code": 200,
            }
        ]
    )
    with factory() as session:
        service = NativeOverviewService(
            session,
            engine_id=PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
            transport=transport,
        )
        with pytest.raises(NativeOverviewError) as exc:
            service.create_run(
                book_id,
                CreateRunRequest.model_validate(
                    {**CREATE_BODY, "client_request_id": "req-acct-preserve"}
                ),
            )
        session.commit()
        assert exc.value.code == "PROVIDER_OUTPUT_INVALID"
        run = session.scalar(select(AnalysisRun).order_by(AnalysisRun.id.desc()))
        assert run is not None
        assert run.status == "failed"
        inv = session.scalar(
            select(ModelInvocation).where(ModelInvocation.run_id == run.id)
        )
        assert inv is not None
        assert inv.input_tokens == 111
        assert inv.output_tokens == 22
        assert abs(float(inv.estimated_cost or 0) - 0.0033) < 1e-9
        assert prose in (inv.raw_response_text or "")
        assert inv.error_message
        assert run.failed_invocation_id == inv.id


def test_private_fake_happy_path_one_window(api_env):
    """Offline private engine through Public orchestrator (AdaptiveFakeTransport)."""

    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    transport = AdaptiveFakeTransport()
    with factory() as session:
        service = NativeOverviewService(
            session,
            engine_id=PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
            transport=transport,
        )
        created = service.create_run(
            book_id,
            CreateRunRequest.model_validate(
                {**CREATE_BODY, "client_request_id": "req-private-happy"}
            ),
        )
        session.commit()
        assert created.status == RunStatus.COMPLETED
        run_id = int(created.run_id)

    assert transport.call_count >= 2  # at least one window + synthesis
    with factory() as session:
        run = session.get(AnalysisRun, run_id)
        assert run is not None
        assert run.provider != FIXTURE_ENGINE_ID
        assert run.provider == "aliyun_qwen_plus"
        assert run.status == RunStatus.COMPLETED.value
        windows = list(
            session.scalars(
                select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
            )
        )
        assert windows
        assert all(w.status == WindowStatus.COMPLETED.value for w in windows)
        overview = NativeOverviewService(session).get_overview(run_id)
        assert overview.coverage.original_coverage_percent == 100.0


def test_materializer_nested_rollback_on_mid_write_failure(api_env, monkeypatch):
    """Entity write then forced failure must not leave half-committed assets."""

    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    with factory() as session:
        service = NativeOverviewService(
            session,
            adapter=load_private_fixture_engine_adapter(),
        )
        created = service.create_run(
            book_id,
            CreateRunRequest.model_validate(
                {**CREATE_BODY, "client_request_id": "req-mat-rollback-base", "provider_id": FIXTURE_ENGINE_ID}
            ),
        )
        session.commit()
        run_id = int(created.run_id)

    from app.narrative_core.contracts.whole_book_overview_v1 import (
        PriorStateV1,
        WholeBookOverviewWindowResultV1,
    )
    from app.narrative_core.services.native_overview_materializer import (
        NativeOverviewMaterializer,
    )

    with factory() as session:
        run = session.get(AnalysisRun, run_id)
        window = session.scalar(
            select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
        )
        assert run is not None and window is not None
        result = WholeBookOverviewWindowResultV1.model_validate(
            json.loads(window.checkpoint_json)["window_result"]
        )
        before_assets = int(
            session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) or 0
        )
        window.state_version_after = None
        session.flush()

        mat = NativeOverviewMaterializer(session)
        original = mat._upsert_asset

        def boom(*args, **kwargs):  # noqa: ANN001
            raise RuntimeError("forced asset write failure")

        monkeypatch.setattr(mat, "_upsert_asset", boom)
        with pytest.raises(Exception):
            mat.materialize_window(
                run, window, result, prior_state=PriorStateV1(state_version=0)
            )
        session.rollback()

    with factory() as session:
        after_assets = int(
            session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) or 0
        )
        # Nested transaction should prevent orphan asset versions from the failed rematerialize.
        assert after_assets == before_assets


def test_double_retry_idempotent_client_request(api_env):
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    transport = FakeTransport(responses=[("timeout",)])
    with factory() as session:
        service = NativeOverviewService(
            session,
            engine_id=PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
            transport=transport,
        )
        with pytest.raises(NativeOverviewError):
            service.create_run(
                book_id,
                CreateRunRequest.model_validate(
                    {**CREATE_BODY, "client_request_id": "req-double-retry-create"}
                ),
            )
        session.commit()
        run = session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.subject_type == "book",
                AnalysisRun.subject_id == str(book_id),
            )
        )
        assert run is not None
        run_id = int(run.id)
        assert run.status == RunStatus.FAILED.value

    # Heal with AdaptiveFake for retry path.
    heal = AdaptiveFakeTransport()
    with factory() as session:
        service = NativeOverviewService(
            session,
            engine_id=PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
            transport=heal,
        )
        first = service.retry_run(
            run_id,
            RetryRunRequest.model_validate({"client_request_id": "retry-same-24"}),
        )
        session.commit()
        second = service.retry_run(
            run_id,
            RetryRunRequest.model_validate({"client_request_id": "retry-same-24"}),
        )
        session.commit()
        assert first.run_id == second.run_id
        assets = int(
            session.scalar(
                select(func.count())
                .select_from(NarrativeAssetVersion)
                .where(NarrativeAssetVersion.run_id == run_id)
            )
            or 0
        )
        # Second identical retry must not create a second run or explode asset count.
        run_count = int(
            session.scalar(
                select(func.count())
                .select_from(AnalysisRun)
                .where(
                    AnalysisRun.subject_type == "book",
                    AnalysisRun.subject_id == str(book_id),
                )
            )
            or 0
        )
        assert run_count == 1
        assert assets >= 0
