#!/usr/bin/env python3
"""Static gate: Public production code must not parse Provider-specific fields (CHG-057)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bevidence_map\b", "evidence_map"),
    (r"provider_policy\.get\(\s*[\"']synthetic_output[\"']", "provider_policy.synthetic_output"),
    (r"\bchoices\s*\[", "choices["),
    (r"message\.content", "message.content"),
    (r"\bdashscope\b", "dashscope"),
)

# Production roots under apps/api/app (exclude tests / fixtures / scripts).
SCAN_ROOTS = (
    "apps/api/app/narrative_core",
    "apps/api/app/routers",
)

ALLOWLIST_FILES = frozenset(
    {
        # Adapter / transport boundary — may mention host defaults and HTTP shapes.
        "apps/api/app/narrative_core/services/whole_book_provider_gateway.py",
        "apps/api/app/narrative_core/services/provider_transport_kind.py",
        "apps/api/app/narrative_core/services/book_overview_output_contract.py",
        "apps/api/app/model_gateway/providers/openai_compatible.py",
        "apps/api/app/services/aliyun_endpoint.py",
        # Mock / evaluation harness fixtures (not Live provider parse path).
        "apps/api/app/narrative_core/services/whole_book_evaluation_harness.py",
        "apps/api/app/narrative_core/services/whole_book_module_runner.py",
        "apps/api/app/narrative_core/services/private_lab_run_executor.py",
        "apps/api/app/narrative_core/services/mock_whole_book_run_executor.py",
    }
)


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args()
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()

    violations: list[str] = []
    for rel_root in SCAN_ROOTS:
        base = root / rel_root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            rel = _rel(path, root)
            if rel in ALLOWLIST_FILES:
                continue
            if "/tests/" in f"/{rel}/":
                continue
            text = path.read_text(encoding="utf-8")
            for pattern, label in FORBIDDEN_PATTERNS:
                if re.search(pattern, text):
                    # book_overview as module_key string is allowed; envelope field access is not.
                    if label == "evidence_map" and "UNDECLARED" in text:
                        continue
                    violations.append(f"{rel}: forbidden token {label}")

    if violations:
        print("PUBLIC PROVIDER BOUNDARY FAILED")
        for row in violations[:50]:
            print(row)
        if len(violations) > 50:
            print(f"... and {len(violations) - 50} more")
        return 1
    print("PUBLIC PROVIDER BOUNDARY OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
