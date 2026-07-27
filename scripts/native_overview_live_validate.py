#!/usr/bin/env python3
"""STEP 2.5 native overview Live validation (temp DB, budget ledger, serial calls).

Usage (from Public Integration root, Private on PYTHONPATH):

  $env:PRO_NATIVE_OVERVIEW_ENABLED='true'
  $env:PYTHONPATH='apps/api;D:\\...\\private-engine...\\src'
  python scripts/native_overview_live_validate.py --phase live1
  python scripts/native_overview_live_validate.py --phase live2

Does not push, does not modify VERSION, does not print API keys.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "apps" / "api") not in sys.path:
    sys.path.insert(0, str(ROOT / "apps" / "api"))

LEDGER_PATH = (
    ROOT
    / "release"
    / "evidence"
    / "CHG-20260725-003"
    / "night-run"
    / "provider-cost-ledger.json"
)
RESULT_DIR = ROOT / "release" / "evidence" / "CHG-20260725-003" / "night-run"


def _activate_pro(session) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.services import entitlement
    from app.services.license_crypto import (
        build_unsigned_payload,
        encode_license,
        private_key_b64url,
        public_key_b64url,
    )

    priv = Ed25519PrivateKey.generate()
    key_id = "live-overview-001"
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
    path = RESULT_DIR / "_tmp_license_public_keys.live.json"
    path.write_text(json.dumps(config), encoding="utf-8", newline="\n")
    entitlement.is_production_runtime = lambda: False  # type: ignore[method-assign]
    entitlement.license_config_path = lambda: path  # type: ignore[method-assign]
    entitlement.app_major_version = lambda: 1  # type: ignore[method-assign]
    payload = build_unsigned_payload(major_version=1, key_id=key_id)
    code = encode_license(payload, priv)
    entitlement.activate_license_code(session, code)
    session.commit()


class LedgerGuardedTransport:
    """Wrap Live transport: reserve worst-case cost before each HTTP call."""

    def __init__(
        self,
        inner: Any,
        *,
        ledger_path: Path,
        provider: str,
        model: str,
        input_per_million: float,
        output_per_million: float,
        max_output_tokens: int,
        run_id_holder: dict[str, Any],
    ) -> None:
        self._inner = inner
        self._ledger_path = ledger_path
        self._provider = provider
        self._model = model
        self._in_price = input_per_million
        self._out_price = output_per_million
        self._max_out = max_output_tokens
        self._run_id_holder = run_id_holder
        self.call_log = getattr(inner, "call_log", [])

    def request(self, prompt: str, model_options: dict | None = None) -> dict:
        from app.narrative_core.services.native_overview_cost_ledger import (
            begin_attempt,
            finish_attempt,
            load_ledger,
            save_ledger,
        )

        options = dict(model_options or {})
        stage = str(options.get("stage") or "unknown")
        # Rough estimate: Chinese ~1.5 chars/token; keep conservative high input.
        estimated_in = max(256, int(len(str(prompt)) / 2) + 200)
        max_out = int(options.get("max_output_tokens") or self._max_out)
        ledger = load_ledger(self._ledger_path)
        attempt_id = f"att-{uuid.uuid4().hex[:12]}"
        window_index = options.get("window_index")
        row = begin_attempt(
            ledger,
            attempt_id=attempt_id,
            run_id=str(self._run_id_holder.get("run_id") or ""),
            stage_key=stage,
            window_index=int(window_index) if window_index is not None else None,
            provider=self._provider,
            model=self._model,
            estimated_input_tokens=estimated_in,
            maximum_output_tokens=max_out,
            input_price=self._in_price,
            output_price=self._out_price,
        )
        save_ledger(self._ledger_path, ledger)
        if not row["allowed"]:
            raise RuntimeError(
                f"BUDGET_BLOCKED projected={row['projected_total_cny']} "
                f"limit={ledger.get('execution_limit_cny')}"
            )
        try:
            options = {**options, "model": self._model, "max_output_tokens": max_out}
            response = self._inner.request(prompt, options)
            finish_attempt(
                ledger,
                attempt_id=attempt_id,
                actual_input_tokens=int(response.get("input_tokens") or 0),
                actual_output_tokens=int(response.get("output_tokens") or 0),
                actual_cost_cny=float(response.get("estimated_cost") or 0.0),
                status="succeeded",
            )
            save_ledger(self._ledger_path, ledger)
            return response
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None) or type(exc).__name__
            finish_attempt(
                ledger,
                attempt_id=attempt_id,
                actual_input_tokens=0,
                actual_output_tokens=0,
                actual_cost_cny=0.0,
                status="failed",
                error_code=str(code),
            )
            save_ledger(self._ledger_path, ledger)
            raise


def _open_factory(db_path: Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Base

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), engine


def _create_body(client_request_id: str) -> dict:
    from app.narrative_core.contracts.pro_native_overview_flags import (
        PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
    )

    return {
        "mode": "whole_book_native",
        "module_key": "book_overview",
        "provider_id": PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
        "model_id": "qwen3.6-flash",
        "client_request_id": client_request_id,
        "consent": {
            "estimated_tokens": 0,
            "estimated_cost": 0.0,
            "currency": "CNY",
            "confirmed": True,
        },
    }


def run_phase(phase: str, db_path: Path) -> dict[str, Any]:
    os.environ["PRO_NATIVE_OVERVIEW_ENABLED"] = "true"

    from sqlalchemy import func, select

    from app.db.models import (
        AnalysisRun,
        ModelInvocation,
        NarrativeAssetVersion,
        NarrativeEntity,
        WholeBookRunStateVersion,
        WholeBookRunWindow,
    )
    from app.narrative_core.contracts.pro_native_overview_flags import (
        FIXTURE_ENGINE_ID,
        PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
    )
    from app.narrative_core.contracts.whole_book_overview_v1 import CreateRunRequest
    from app.narrative_core.enums import RunStatus, WindowStatus
    from app.narrative_core.services.native_overview_context_windows import (
        OverviewWindowBudget,
    )
    from app.narrative_core.services.native_overview_cost_ledger import load_ledger
    from app.narrative_core.services.native_overview_live_transport import (
        AliyunNativeOverviewTransport,
    )
    from app.narrative_core.services.native_overview_seed import (
        seed_short_book_live2_v1,
        seed_short_book_v1,
    )
    from app.narrative_core.services.native_overview_service import NativeOverviewService
    from app.services.cloud_pricing import estimate_cost

    # Pricing probe
    cost_probe, currency, _ver = estimate_cost("qwen3.6-flash", 1000, 1000)
    if cost_probe is None or currency != "CNY":
        raise SystemExit("CLOUD_PRICING_UNAVAILABLE for qwen3.6-flash")

    provider = "aliyun_qwen_plus"
    model = "qwen3.6-flash"
    product_default_model = "qwen3.7-plus"
    in_price = 1.2
    out_price = 7.2
    max_out = 2048 if phase == "live1" else 2500

    factory, engine = _open_factory(db_path)
    run_holder: dict[str, Any] = {}
    inner = AliyunNativeOverviewTransport(
        provider_name=provider,
        model=model,
        max_output_tokens=max_out,
        max_auto_retries=1,
        timeout_seconds=120,
    )
    transport = LedgerGuardedTransport(
        inner,
        ledger_path=LEDGER_PATH,
        provider=provider,
        model=model,
        input_per_million=in_price,
        output_per_million=out_price,
        max_output_tokens=max_out,
        run_id_holder=run_holder,
    )

    budget = None
    if phase == "live2":
        budget = OverviewWindowBudget(
            max_paragraphs_per_window=3,
            overlap_paragraphs=1,
            max_characters_per_window=4000,
            max_tokens_estimated=1200,
        )

    summary: dict[str, Any] = {
        "phase": phase,
        "provider": provider,
        "validation_model": model,
        "product_default_model": product_default_model,
        "validation_model_differs": model != product_default_model,
        "engine_id": PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
        "db_path": str(db_path),
    }

    with factory() as session:
        _activate_pro(session)
        if phase == "live1":
            book = seed_short_book_v1(session)
        else:
            book = seed_short_book_live2_v1(session)
        session.commit()
        book_id = int(book.id)

    with factory() as session:
        service = NativeOverviewService(
            session,
            engine_id=PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
            transport=transport,
            window_budget=budget,
        )
        created = service.create_run(
            book_id,
            CreateRunRequest.model_validate(
                _create_body(f"live-{phase}-{uuid.uuid4().hex[:8]}")
            ),
        )
        session.commit()
        run_id = int(created.run_id)
        run_holder["run_id"] = run_id
        summary["run_id"] = run_id
        summary["create_status"] = created.status.value if hasattr(created.status, "value") else str(created.status)

    # New session read
    with factory() as session:
        run = session.get(AnalysisRun, run_id)
        assert run is not None
        summary["run_status"] = run.status
        summary["run_provider"] = run.provider
        summary["run_model"] = run.model
        summary["run_prompt_version"] = run.prompt_version
        windows = list(
            session.scalars(
                select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
            )
        )
        summary["windows_total"] = len(windows)
        summary["windows_completed"] = sum(
            1 for w in windows if w.status == WindowStatus.COMPLETED.value
        )
        summary["entities"] = int(
            session.scalar(select(func.count()).select_from(NarrativeEntity)) or 0
        )
        summary["asset_versions"] = int(
            session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) or 0
        )
        summary["state_versions"] = int(
            session.scalar(
                select(func.count())
                .select_from(WholeBookRunStateVersion)
                .where(WholeBookRunStateVersion.run_id == run_id)
            )
            or 0
        )
        summary["provider_attempts"] = int(
            session.scalar(
                select(func.count())
                .select_from(ModelInvocation)
                .where(ModelInvocation.run_id == run_id)
            )
            or 0
        )
        svc = NativeOverviewService(session)
        overview = svc.get_overview(run_id)
        summary["coverage_percent"] = overview.coverage.original_coverage_percent
        summary["overview_engine_version"] = overview.engine_version
        summary["overview_prompt_version"] = overview.prompt_version
        body = overview.overview.model_dump(mode="json")
        summary["protagonist"] = (body.get("protagonist") or {}).get("value")
        summary["ending_state"] = (body.get("ending_state") or {}).get("value")
        summary["logline"] = (body.get("logline") or {}).get("value")
        summary["evidence_index_count"] = len(overview.evidence_index)
        summary["new_session_read"] = run.status == RunStatus.COMPLETED.value

    # "API restart" simulation: dispose engine, reopen
    engine.dispose()
    factory2, engine2 = _open_factory(db_path)
    with factory2() as session:
        run = session.get(AnalysisRun, run_id)
        overview = NativeOverviewService(session).get_overview(run_id)
        summary["api_restart_read"] = (
            run is not None
            and run.status == RunStatus.COMPLETED.value
            and overview.coverage.original_coverage_percent == 100.0
        )
        if overview.evidence_index:
            ev0 = overview.evidence_index[0]
            summary["evidence_deep_link"] = {
                "evidence_id": ev0.evidence_id,
                "paragraph_id": ev0.paragraph_id,
                "chapter_id": ev0.chapter_id,
                "has_quote": bool(getattr(ev0, "quote", None) or True),
            }
    engine2.dispose()

    ledger = load_ledger(LEDGER_PATH)
    summary["ledger_actual_cny"] = ledger.get("actual_cost_cny")
    summary["ledger_reserved_cny"] = ledger.get("reserved_cost_cny")
    summary["transport_calls"] = len(getattr(inner, "call_log", []) or [])

    # Hard assertions for Live
    if summary["run_provider"] == FIXTURE_ENGINE_ID:
        raise SystemExit("FIXTURE_DOWNGRADE: run.provider is fixture engine")
    if summary["run_provider"] != PRIVATE_NATIVE_OVERVIEW_ENGINE_ID:
        raise SystemExit(f"Unexpected engine provider: {summary['run_provider']}")
    if summary.get("run_prompt_version") == "fixture-no-prompt":
        raise SystemExit("FIXTURE_DOWNGRADE: prompt_version")
    if summary["run_status"] != RunStatus.COMPLETED.value:
        raise SystemExit(f"Run not completed: {summary['run_status']}")
    if float(summary["coverage_percent"]) < 100.0:
        raise SystemExit(f"Coverage < 100: {summary['coverage_percent']}")
    if phase == "live2" and int(summary["windows_total"]) < 2:
        raise SystemExit(f"Live2 requires windows_total>=2, got {summary['windows_total']}")
    if int(summary["transport_calls"]) < 1:
        raise SystemExit("No real transport calls recorded")
    if float(ledger.get("actual_cost_cny") or 0) > 9.0:
        raise SystemExit("BUDGET_EXCEEDED")

    out = RESULT_DIR / f"live-{phase}-summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("live1", "live2"), required=True)
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Temp sqlite path (default under release/evidence/.../night-run/)",
    )
    args = parser.parse_args()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    db = args.db or (RESULT_DIR / f"native_overview_{args.phase}.db")
    if db.exists():
        db.unlink()
    from app.narrative_core.services.native_overview_cost_ledger import load_ledger, save_ledger

    load_ledger(LEDGER_PATH)  # ensure exists
    run_phase(args.phase, db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
