# -*- coding: utf-8 -*-
"""Offline gate: Reader Journey output-token budget (DEFECT-CANARY-016)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))

from app.core.config import get_settings  # noqa: E402
from app.services.reader_journey_output_budget import (  # noqa: E402
    budget_gate_verdict,
    build_output_budget_audit,
)

OUT = ROOT / "audits/single-chapter-pipeline/reader-journey-output-budget-v1.json"


def main() -> int:
    get_settings.cache_clear()
    audit = build_output_budget_audit()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verdict = budget_gate_verdict(audit)
    print(verdict)
    return 0 if verdict == "READER_JOURNEY_OUTPUT_BUDGET_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
