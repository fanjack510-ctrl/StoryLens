#!/usr/bin/env python3
"""Verify desktop CAPABILITY_KEYS match Phase 1C contract fixture / backend enum values.

Agent H routes may be unmerged — this checks shared contract strings only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS_TS = ROOT / "apps" / "desktop" / "src" / "services" / "capability" / "keys.ts"
ENUMS_PY = ROOT / "apps" / "api" / "app" / "narrative_core" / "enums.py"
FIXTURE_TS = (
    ROOT
    / "apps"
    / "desktop"
    / "src"
    / "services"
    / "capability"
    / "contractKeys.fixture.ts"
)

EXPECTED = [
    "whole_book_analysis",
    "narrative_asset_library",
    "story_lab",
    "cross_book_search",
    "advanced_export",
]


def _extract_quoted(text: str) -> list[str]:
    return re.findall(r'"([a-z0-9_]+)"', text)


def main() -> int:
    keys_ts = KEYS_TS.read_text(encoding="utf-8")
    fixture_ts = FIXTURE_TS.read_text(encoding="utf-8")
    enums_py = ENUMS_PY.read_text(encoding="utf-8")

    block = re.search(r"CAPABILITY_KEYS\s*=\s*\[(.*?)]\s*as const", keys_ts, re.S)
    if not block:
        print("error: CAPABILITY_KEYS not found", file=sys.stderr)
        return 1
    frontend_keys = _extract_quoted(block.group(1))

    fixture_block = re.search(
        r"PHASE1C_CONTRACT_CAPABILITY_KEYS\s*=\s*\[(.*?)]\s*as const",
        fixture_ts,
        re.S,
    )
    if not fixture_block:
        print("error: fixture keys not found", file=sys.stderr)
        return 1
    fixture_keys = _extract_quoted(fixture_block.group(1))

    enum_block = re.search(r"class CapabilityKey\(StrEnum\):(.*?)(?:\nclass |\Z)", enums_py, re.S)
    if not enum_block:
        print("error: CapabilityKey enum not found", file=sys.stderr)
        return 1
    backend_keys = re.findall(r'=\s*"([a-z0-9_]+)"', enum_block.group(1))

    errors: list[str] = []
    if frontend_keys != EXPECTED:
        errors.append(f"frontend keys mismatch: {frontend_keys}")
    if fixture_keys != EXPECTED:
        errors.append(f"fixture keys mismatch: {fixture_keys}")
    if backend_keys != EXPECTED:
        errors.append(f"backend enum mismatch: {backend_keys}")
    if len(set(frontend_keys)) != len(frontend_keys):
        errors.append("frontend keys not unique")

    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1

    print("capability key consistency ok:", ", ".join(EXPECTED))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
