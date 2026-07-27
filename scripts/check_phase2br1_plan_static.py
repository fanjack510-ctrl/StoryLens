#!/usr/bin/env python3
"""Static checks for Phase 2B-R1 live readiness plan (CHG-045)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def err(msg: str) -> None:
    ERRORS.append(msg)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    if (ROOT / "VERSION").read_text(encoding="utf-8").strip() != "1.0.5":
        err("VERSION must be 1.0.5")

    api_dto = read(ROOT / "apps/api/app/narrative_core/contracts/api_dto.py")
    if "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED = True" not in api_dto:
        err("WHOLE_BOOK_RUNS_ENDPOINT_DISABLED must remain True")

    mock = read(ROOT / "apps/api/app/narrative_core/run_shell_contract/mock_lab.py")
    if not re.search(r"WHOLE_BOOK_MOCK_LAB_ENABLED\s*:\s*bool\s*=\s*False", mock):
        err("WHOLE_BOOK_MOCK_LAB_ENABLED must default False")

    pelab = read(ROOT / "apps/api/app/narrative_core/run_shell_contract/private_engine_lab.py")
    if not re.search(r"WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED\s*:\s*bool\s*=\s*False", pelab):
        err("WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED must default False")

    if "PRODUCTION_DEFAULT_ENGINE_ID: str | None = None" not in read(
        ROOT / "apps/api/app/narrative_core/services/whole_book_engine_registry.py"
    ):
        err("PRODUCTION_DEFAULT_ENGINE_ID must be None")

    if "PRO_CAPABILITIES_SHIPPED = false" not in read(
        ROOT / "apps/desktop/src/services/productEdition.ts"
    ):
        err("PRO_CAPABILITIES_SHIPPED must be false")

    # Shell-only still present at baseline (plan must not pretend fixed).
    lab_router = read(ROOT / "apps/api/app/routers/whole_book_private_engine_lab_runs.py")
    if 'modules_implemented": False' not in lab_router and "modules_implemented\": False" not in lab_router:
        # tolerate either quote style in source
        if "modules_implemented" not in lab_router or "False" not in lab_router:
            err("expected shell-only modules_implemented=False still in Lab router at plan baseline")

    gateway = read(ROOT / "apps/api/app/narrative_core/services/whole_book_provider_gateway.py")
    if "instruction_ref=" not in gateway or "input_bundle_ref=" not in gateway:
        err("expected ref-only live payload still present at plan baseline")

    mig = sorted(p.name for p in (ROOT / "apps/api/app/narrative_core/migrations").iterdir() if p.is_file())
    if mig != ["__init__.py", "runner.py"]:
        err(f"unexpected migrations files: {mig}")

    required = [
        "docs/architecture/narrative-intelligence-core/phase2br1-live-readiness-plan.md",
        "docs/architecture/narrative-intelligence-core/phase2br1-provider-payload-estimate.md",
        "docs/architecture/narrative-intelligence-core/phase2br1-private-lab-persistence.md",
        "docs/architecture/narrative-intelligence-core/phase2br1-parallel-file-ownership.md",
        "docs/architecture/narrative-intelligence-core/phase2br1-parallel-file-ownership.json",
        "docs/architecture/narrative-intelligence-core/phase2br1-plan-verification.md",
    ]
    for rel in required:
        if not (ROOT / rel).is_file():
            err(f"missing {rel}")

    for rel in required:
        if rel.endswith(".json"):
            continue
        text = read(ROOT / rel)
        for marker in ("<<<FORMAL_PROMPT_START>>>", "你是一名小说结构分析专家"):
            if marker in text:
                err(f"formal prompt marker in {rel}")

    ownership = json.loads(
        read(
            ROOT
            / "docs/architecture/narrative-intelligence-core/phase2br1-parallel-file-ownership.json"
        )
    )
    if ownership.get("public_baseline_commit") != "a8349c44b2b7ecebccb46b512ab77f1d8a0524c4":
        err("ownership public baseline mismatch")
    if ownership.get("private_baseline_commit") != "61cdc3ad184c00e0ab19bcc87b61149293fc3598":
        err("ownership private baseline mismatch")

    def collect(key: str) -> set[str]:
        return {item["path"] for item in ownership[key]}

    overlap = collect("public_agent_u") & collect("public_agent_v")
    if overlap:
        err(f"public U/V ownership overlap: {sorted(overlap)}")
    priv_overlap = collect("private_agent_u") & collect("private_agent_v")
    if priv_overlap:
        err(f"private U/V ownership overlap: {sorted(priv_overlap)}")

    for key in ("public_agent_u", "public_agent_v", "integration_shared"):
        for item in ownership[key]:
            path = item["path"]
            status = item["status"]
            full = ROOT / path
            if status == "exists" and not full.exists():
                err(f"ownership exists but missing: {path}")

    for cid, want in (
        ("CHG-20260723-041", "tested"),
        ("CHG-20260723-042", "tested"),
        ("CHG-20260723-043", "tested"),
        ("CHG-20260723-044", "tested"),
        ("CHG-20260723-046", "registered"),
        ("CHG-20260723-047", "registered"),
        ("CHG-20260723-048", "registered"),
    ):
        data = json.loads(read(ROOT / "release/changes" / f"{cid}.json"))
        if data.get("status") != want:
            err(f"{cid} status want {want} got {data.get('status')}")
        if data.get("base_version") != "1.0.5":
            err(f"{cid} base_version must be 1.0.5")
        if data.get("status") in {"ready", "released"}:
            err(f"{cid} must not be ready/released")

    chg045 = json.loads(read(ROOT / "release/changes/CHG-20260723-045.json"))
    if chg045.get("status") not in {"registered", "implemented", "tested"}:
        err("CHG-045 unexpected status")
    if chg045.get("status") in {"ready", "released", "verified"}:
        err("CHG-045 must not be verified/ready/released at plan max tested")

    if ERRORS:
        print("PHASE2BR1_PLAN_STATIC_FAIL")
        for e in ERRORS:
            print(f" - {e}")
        return 1
    print("PHASE2BR1_PLAN_STATIC_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
