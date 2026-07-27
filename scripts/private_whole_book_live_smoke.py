#!/usr/bin/env python3
"""Private Whole-Book Live Smoke harness (Phase 2B-R1 / CHG-050).

Default: dry-run only. Real Live requires explicit --live AND Live Probe env.
Environment must be set before Runtime construction / API start.
Never prints novel body, prompt body, or credentials.
Does not mutate permanent environment variables.
Does not auto-delete Runs.
Does not auto-enable Probe.
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
PRIVATE_LAB_ENV = "WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED"


def _safe_print(title: str, payload: dict) -> None:
    """Refuse secret-bearing *keys* (exact), not status labels like credential_present."""

    banned_exact = {"api_key", "credential", "authorization", "bearer", "prompt", "messages", "text"}

    def _walk(obj: object, path: str = "") -> str | None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_l = str(key).lower()
                here = f"{path}.{key}" if path else str(key)
                if key_l in banned_exact:
                    return here
                hit = _walk(value, here)
                if hit:
                    return hit
        elif isinstance(obj, (list, tuple)):
            for i, item in enumerate(obj):
                hit = _walk(item, f"{path}[{i}]")
                if hit:
                    return hit
        return None

    bad = _walk(payload)
    if bad:
        raise SystemExit(f"refusing to print payload containing secret key at {bad}")
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
    lab = str(os.environ.get(PRIVATE_LAB_ENV, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if live and not probe:
        print(
            f"Real Live refused: set {PRIVATE_PROBE_ENV}=1 explicitly before Runtime "
            "(CI Integration must not do this).",
            file=sys.stderr,
        )
        return 2
    if live and not lab:
        print(
            f"Real Live refused: set {PRIVATE_LAB_ENV}=true before Runtime.",
            file=sys.stderr,
        )
        return 2

    # Import late so --help works without full app. Env must already be set.
    from app.db.session import SessionLocal
    from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
        create_live_readiness_runtime,
    )

    session = SessionLocal()
    try:
        runtime = create_live_readiness_runtime(
            environment="development",
            lab_enabled=True,
            dry_run=True,  # default; Create request carries dry_run=false for Live
            allow_network=None,  # derived from Probe + Lab + env
            session=session,
            allow_fake_resolver=False,
            auto_wire_credentials=True,
        )
        runtime.bind_session(session)
        if live and not runtime.allow_network:
            print(
                json.dumps(
                    {
                        "status": "security_gate_failed",
                        "deny_reason": "allow_network_false",
                        "note": "Runtime did not authorize network; not a Provider failure.",
                        "live_probe": probe,
                        "lab_enabled": runtime.lab_enabled,
                        "http_calls": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 4

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
                "credential_status": pre.details.get("credential_status"),
                "resolver_is_fake": runtime.uses_fake_resolver,
                "allow_network": runtime.allow_network,
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
        primary = cached.get("primary_manifest")
        chapter_ids = list(getattr(primary, "selected_chapter_ids", ()) or ())
        paragraph_ids = list(getattr(primary, "selected_paragraph_ids", ()) or ())
        _safe_print(
            "estimate",
            {
                "fingerprint": est.fingerprint,
                "consent_fingerprint": cached.get("consent_fingerprint"),
                "data_transfer_manifest_hash": est.data_transfer_manifest_hash,
                "usage_summary": dict(est.usage_summary),
                "cost_summary": dict(est.cost_summary),
                "selection_summary": {
                    "selected_chapter_ids": chapter_ids,
                    "selected_paragraph_count": len(paragraph_ids),
                    "source_character_count": getattr(primary, "source_character_count", None),
                    "context_bundle_hash": getattr(primary, "context_bundle_hash", None),
                },
                "module_keys": list(est.module_keys),
                "live": live,
                "probe": probe,
                "create_dry_run": not live,
                "allow_network": runtime.allow_network,
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
                        "Harness completed Dry Preflight/Estimate only. "
                        "Create/execute requires explicit confirmation and "
                        f"dry_run={str(not live).lower()}. "
                        "Run is never auto-deleted."
                    ),
                    "cancel_supported": True,
                    "check_results": bool(args.check_results),
                    "live_executed": False,
                    "http_calls": 0,
                    "create_dry_run": not live,
                    "allow_network": runtime.allow_network,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.cancel:
            print("cancel: cooperative cancel would be issued after create (not executed here)")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
