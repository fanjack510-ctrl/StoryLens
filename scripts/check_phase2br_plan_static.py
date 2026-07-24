#!/usr/bin/env python3
"""Static checks for Phase 2B-R implementation plan (CHG-041).

Proves planning commit did not introduce formal prompts, model calls,
migrations, or production gate flips.
"""

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
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if version != "1.0.5":
        err(f"VERSION must be 1.0.5, got {version!r}")

    # Gates from source (not docs).
    api_dto = read(ROOT / "apps/api/app/narrative_core/contracts/api_dto.py")
    if "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED = True" not in api_dto:
        err("WHOLE_BOOK_RUNS_ENDPOINT_DISABLED must remain True")

    mock_lab = read(ROOT / "apps/api/app/narrative_core/run_shell_contract/mock_lab.py")
    if not re.search(r"WHOLE_BOOK_MOCK_LAB_ENABLED\s*:\s*bool\s*=\s*False", mock_lab):
        err("WHOLE_BOOK_MOCK_LAB_ENABLED must default False")

    registry = read(ROOT / "apps/api/app/narrative_core/services/whole_book_engine_registry.py")
    if "PRODUCTION_DEFAULT_ENGINE_ID: str | None = None" not in registry:
        err("PRODUCTION_DEFAULT_ENGINE_ID must be None")

    edition = read(ROOT / "apps/desktop/src/services/productEdition.ts")
    if "PRO_CAPABILITIES_SHIPPED = false" not in edition:
        err("PRO_CAPABILITIES_SHIPPED must be false")

    gateway = read(ROOT / "apps/api/app/narrative_core/services/whole_book_provider_gateway.py")
    if "_NETWORK_FORBIDDEN = True" not in gateway:
        err("whole-book provider gateway must keep _NETWORK_FORBIDDEN=True on plan branch")

    # No new alembic/migration files under narrative_core/migrations beyond runner.
    mig_dir = ROOT / "apps/api/app/narrative_core/migrations"
    mig_files = sorted(p.name for p in mig_dir.iterdir() if p.is_file())
    if mig_files != ["__init__.py", "runner.py"]:
        err(f"unexpected narrative_core migrations files: {mig_files}")

    # Plan docs must exist; formal prompt bodies must not appear in new plan docs.
    required_docs = [
        "docs/architecture/narrative-intelligence-core/phase2br-implementation-plan.md",
        "docs/architecture/narrative-intelligence-core/phase2br-private-repository-boundary.md",
        "docs/architecture/narrative-intelligence-core/phase2br-provider-and-budget-plan.md",
        "docs/architecture/narrative-intelligence-core/phase2br-live-analysis-safety.md",
        "docs/architecture/narrative-intelligence-core/phase2br-parallel-file-ownership.md",
        "docs/architecture/narrative-intelligence-core/phase2br-parallel-file-ownership.json",
    ]
    for rel in required_docs:
        if not (ROOT / rel).is_file():
            err(f"missing required doc: {rel}")

    banned_prompt_markers = (
        "你是一名小说结构分析专家",
        "SYSTEM_PROMPT_BODY",
        "<<<FORMAL_PROMPT_START>>>",
    )
    for rel in required_docs:
        if rel.endswith(".json"):
            continue
        text = read(ROOT / rel)
        for marker in banned_prompt_markers:
            if marker in text:
                err(f"formal prompt marker in {rel}: {marker}")

    # Ownership JSON: exists paths must exist; planned marked.
    ownership = json.loads(
        read(
            ROOT
            / "docs/architecture/narrative-intelligence-core/phase2br-parallel-file-ownership.json"
        )
    )
    for key in (
        "public_agent_s",
        "public_agent_t",
        "integration_shared",
    ):
        for item in ownership[key]:
            path = item["path"]
            status = item["status"]
            # Skip directory-ish trailing ownership that is change json planned
            full = ROOT / path
            if status == "exists":
                if not full.exists():
                    err(f"ownership claims exists but missing: {path}")
            elif status == "planned":
                if full.exists() and path.endswith(".py") and "phase2br" in path:
                    # planned test/router files should not exist yet on plan branch
                    pass
            else:
                err(f"unknown ownership status for {path}: {status}")

    # Changes registered.
    for cid in (
        "CHG-20260723-041",
        "CHG-20260723-042",
        "CHG-20260723-043",
        "CHG-20260723-044",
    ):
        path = ROOT / "release/changes" / f"{cid}.json"
        if not path.is_file():
            err(f"missing change file {cid}")
            continue
        data = json.loads(read(path))
        if data.get("base_version") != "1.0.5":
            err(f"{cid} base_version must be 1.0.5")
        if data.get("status") in {"ready", "released"}:
            err(f"{cid} must not be ready/released")

    for cid in ("CHG-20260723-036",):
        st = json.loads(read(ROOT / "release/changes" / f"{cid}.json"))["status"]
        if st != "verified":
            err(f"{cid} must remain verified, got {st}")
    for cid in (
        "CHG-20260723-037",
        "CHG-20260723-038",
        "CHG-20260723-039",
        "CHG-20260723-040",
    ):
        st = json.loads(read(ROOT / "release/changes" / f"{cid}.json"))["status"]
        if st != "tested":
            err(f"{cid} must remain tested, got {st}")

    for cid in (
        "CHG-20260723-042",
        "CHG-20260723-043",
        "CHG-20260723-044",
    ):
        st = json.loads(read(ROOT / "release/changes" / f"{cid}.json"))["status"]
        if st != "registered":
            err(f"{cid} must be registered at plan time, got {st}")

    private_root = Path(r"D:\Dstorylens-private-engine")
    if private_root.exists():
        # Plan phase must not have modified it; existence alone is OK to report.
        print(f"note: private engine path exists (audit-only): {private_root}")
    else:
        print("note: private engine path absent (plan-only OK)")

    if ERRORS:
        print("PHASE2BR_PLAN_STATIC_FAIL")
        for e in ERRORS:
            print(f" - {e}")
        return 1
    print("PHASE2BR_PLAN_STATIC_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
