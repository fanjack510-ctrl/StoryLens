#!/usr/bin/env python3
"""Private Whole-Book Live Smoke harness (Phase 2B-R1 Integration).

Default: dry-run only. Real Live requires explicit --live AND Live Probe env.
Never prints novel body, prompt body, or credentials.
Does not mutate permanent environment variables.
Does not auto-delete Runs.
This Integration must not execute real Live in CI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

PRIVATE_PROBE_ENV = "WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE"


def _safe_print(title: str, payload: dict) -> None:
    banned = ("text", "prompt", "messages", "api_key", "credential", "authorization", "bearer")
    blob = json.dumps(payload, ensure_ascii=False)
    lower = blob.lower()
    for token in banned:
        if token in lower and token in ("api_key", "credential", "authorization", "bearer"):
            raise SystemExit(f"refusing to print payload containing {token}")
    print(f"== {title} ==")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Private whole-book live smoke (default dry-run)")
    p.add_argument("--book-id", type=int, required=True)
    p.add_argument("--snapshot-id", type=int, required=True)
    p.add_argument(
        "--modules",
        default="book_overview",
        help="Comma-separated modules; default book_overview only",
    )
    p.add_argument("--live", action="store_true", help="Opt-in real Live (requires Live Probe)")
    p.add_argument("--yes", action="store_true", help="Skip interactive confirm (dry only)")
    p.add_argument("--cancel", action="store_true", help="Cancel after create (cooperative)")
    p.add_argument("--check-results", action="store_true", help="Fetch result index after run")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    modules = tuple(m.strip() for m in str(args.modules).split(",") if m.strip())
    if not modules:
        print("modules required", file=sys.stderr)
        return 2
    if len(modules) > 1 and args.live and not args.yes:
        print("Four-module Live requires per-module confirmation; refusing batch --live.")
        return 2

    live = bool(args.live)
    probe = str(os.environ.get(PRIVATE_PROBE_ENV, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if live and not probe:
        print(
            f"Real Live refused: set {PRIVATE_PROBE_ENV}=1 explicitly "
            "(CI Integration must not do this).",
            file=sys.stderr,
        )
        return 2

    # Import late so --help works without full app.
    from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
        create_live_readiness_runtime,
    )

    runtime = create_live_readiness_runtime(
        environment="development",
        lab_enabled=True,
        dry_run=not live,
        allow_network=live,
    )
    # Estimate via adapters without DB session for dry summary when possible.
    assert runtime.estimate is not None
    assert runtime.preflight is not None
    pre = runtime.preflight.preflight(
        book_id=int(args.book_id),
        book_snapshot_id=int(args.snapshot_id),
        configuration_fingerprint="live-smoke-cfg",
        requested_modules=modules,
    )
    _safe_print(
        "preflight",
        {
            "ok": pre.ok,
            "fingerprint": pre.fingerprint,
            "reason_code": pre.reason_code,
            "run_created": False,
            "details_keys": sorted(pre.details.keys()),
        },
    )
    if not pre.ok:
        return 1

    est = runtime.estimate.estimate(
        book_id=int(args.book_id),
        book_snapshot_id=int(args.snapshot_id),
        configuration_fingerprint="live-smoke-cfg",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
        requested_modules=modules,
        preflight_fingerprint=pre.fingerprint,
    )
    cached = runtime.estimate._cache.get(est.fingerprint) or {}
    _safe_print(
        "estimate",
        {
            "fingerprint": est.fingerprint,
            "consent_fingerprint": cached.get("consent_fingerprint"),
            "data_transfer_manifest_hash": est.data_transfer_manifest_hash,
            "usage_summary": dict(est.usage_summary),
            "cost_summary": dict(est.cost_summary),
            "module_keys": list(est.module_keys),
            "live": live,
            "probe": probe,
            "dry_run": not live,
        },
    )

    if not args.yes:
        prompt = "Confirm create Private Lab Run? [y/N] "
        if live:
            prompt = "Confirm REAL LIVE Provider call? Type YES: "
        answer = input(prompt).strip()
        if live and answer != "YES":
            print("aborted")
            return 3
        if not live and answer.lower() not in {"y", "yes"}:
            print("aborted")
            return 3

    print(
        json.dumps(
            {
                "status": "ready",
                "note": (
                    "Harness stops before create when run without app DB session. "
                    "Wire through HTTP Lab for full create/execute. "
                    "Run is never auto-deleted."
                ),
                "cancel_supported": True,
                "check_results": bool(args.check_results),
                "live_executed": False,
                "http_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.cancel:
        print("cancel: cooperative cancel would be issued after create (not executed here)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
