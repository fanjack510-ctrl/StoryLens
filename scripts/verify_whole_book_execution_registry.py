#!/usr/bin/env python3
"""Verify Whole-Book execution registry numbering (docs-only, offline).

Does not access network, Provider, or databases. Read-only checks.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "whole-book" / "EXECUTION_REGISTRY.json"
STEP_RE = re.compile(r"^WB-\d+(?:\.\d+)+-[A-Z0-9-]+$")
CHG_RE = re.compile(r"^CHG-\d{8}-\d{3}$")
MG_RE = re.compile(r"^MG-WB-\d+(?:\.\d+)+$")
EVIDENCE_RE = re.compile(r"^release/evidence/whole-book/WB-\d+(?:\.\d+)+-[A-Z0-9-]+/$")


def main() -> int:
    if not REGISTRY.is_file():
        print("WHOLE-BOOK REGISTRY VERIFICATION：")
        print("FAIL")
        print(f"missing {REGISTRY}")
        return 1

    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    steps = data.get("steps") or []
    step_ids = [s.get("step_id") for s in steps]
    change_ids = [s.get("change_id") for s in steps]
    gate_ids = [s.get("manual_gate_id") for s in steps]
    evidence_paths = [s.get("evidence_dir") for s in steps]

    dup_steps = sorted({x for x in step_ids if step_ids.count(x) > 1})
    dup_changes = sorted({x for x in change_ids if change_ids.count(x) > 1})
    dup_gates = sorted({x for x in gate_ids if gate_ids.count(x) > 1})

    missing_gate = sum(1 for g in gate_ids if not g)
    invalid_evidence = [
        p for p in evidence_paths if not isinstance(p, str) or not EVIDENCE_RE.fullmatch(p)
    ]
    invalid_steps = [s for s in step_ids if not isinstance(s, str) or not STEP_RE.fullmatch(s)]
    invalid_changes = [c for c in change_ids if not isinstance(c, str) or not CHG_RE.fullmatch(c)]
    invalid_gates = [g for g in gate_ids if not isinstance(g, str) or not MG_RE.fullmatch(g)]

    # mapping completeness: each step has unique change+gate
    map_ok = all(
        isinstance(s.get("step_id"), str)
        and isinstance(s.get("change_id"), str)
        and isinstance(s.get("manual_gate_id"), str)
        and isinstance(s.get("evidence_dir"), str)
        for s in steps
    )

    # reserved change files must not collide with other registry files outside mapping
    # (002-038 reserved for steps; 001 is audit)
    reserved = {f"CHG-20260728-{n:03d}" for n in range(2, 39)}
    mapped = set(change_ids)
    missing_reserved = sorted(reserved - mapped)
    extra_mapped = sorted(mapped - reserved)

    conflicts = []
    changes_dir = ROOT / "release" / "changes"
    for cid in sorted(reserved):
        # only conflict if a change file exists for reserved id that is NOT our planned step
        # existence is expected once steps register; for freeze, conflict = duplicate stems only
        pass

    # Existing on-disk change IDs that collide with reserved range but are not in mapping
    # should not happen for 002-038 until registered; 001 allowed.
    on_disk = {p.stem for p in changes_dir.glob("CHG-*.json")}
    # If an on-disk ID in 002-038 exists now, it must equal mapped (WB-0.1 creates 002 only)
    unexpected_disk = sorted((on_disk & reserved) - mapped - {"CHG-20260728-002"})

    ok = (
        len(steps) == 37
        and len(set(step_ids)) == 37
        and len(set(change_ids)) == 37
        and len(set(gate_ids)) == 37
        and missing_gate == 0
        and not dup_steps
        and not dup_changes
        and not dup_gates
        and not invalid_evidence
        and not invalid_steps
        and not invalid_changes
        and not invalid_gates
        and map_ok
        and not missing_reserved
        and not extra_mapped
        and not unexpected_disk
    )

    # Optional V1.2.0 Free release path (CHG-20260803-044); does not change frozen 37 count.
    v120_path = data.get("v120_free_release_path")
    v120_steps = data.get("v120_release_steps") or []
    v120_ok = True
    v120_details: dict = {}
    if v120_path is not None or v120_steps:
        expected_ids = {
            "WB-2.2.1-V120-E2E-STABILIZATION",
            "WB-2.2.2-V120-RELEASE-DEBT",
            "WB-2.2.3-V120-L3-PROVIDER",
        }
        got_ids = {s.get("step_id") for s in v120_steps}
        wb22 = next((s for s in steps if s.get("step_id") == "WB-2.2-CHAPTER-FUNCTIONS"), {})
        wb64 = next((s for s in steps if s.get("step_id") == "WB-6.4-120-RC"), {})
        v120_ok = (
            isinstance(v120_path, dict)
            and got_ids == expected_ids
            and wb22.get("next_step") == "WB-2.2.1-V120-E2E-STABILIZATION"
            and wb64.get("depends_on") == ["WB-2.2.3-V120-L3-PROVIDER"]
            and (data.get("v120_free_product_scope") or {}).get("feature_end_step")
            == "WB-2.2-CHAPTER-FUNCTIONS"
            and (data.get("v120_free_product_scope") or {}).get("remaining_function_modules") == 0
        )
        if not v120_ok:
            v120_details = {
                "expected_v120_ids": sorted(expected_ids),
                "got_v120_ids": sorted(x for x in got_ids if x),
                "wb22_next_step": wb22.get("next_step"),
                "wb64_depends_on": wb64.get("depends_on"),
            }

    ok = ok and v120_ok

    print("WHOLE-BOOK REGISTRY VERIFICATION：")
    print("PASS" if ok else "FAIL")
    print("NUMBERED STEPS：")
    print(len(steps))
    print("MANUAL GATES：")
    print(len([g for g in gate_ids if g]))
    print("STEPS WITHOUT GATE：")
    print(missing_gate)
    print("DUPLICATE STEP IDS：")
    print(len(dup_steps))
    print("DUPLICATE CHANGE IDS：")
    print(len(dup_changes))
    print("DUPLICATE GATE IDS：")
    print(len(dup_gates))
    print("INVALID EVIDENCE PATHS：")
    print(len(invalid_evidence))
    print("V120 FREE RELEASE PATH：")
    print("PRESENT_OK" if v120_path and v120_ok else ("ABSENT" if not v120_path else "FAIL"))
    if not ok:
        details = {
            "dup_steps": dup_steps,
            "dup_changes": dup_changes,
            "dup_gates": dup_gates,
            "invalid_evidence": invalid_evidence,
            "invalid_steps": invalid_steps,
            "invalid_changes": invalid_changes,
            "invalid_gates": invalid_gates,
            "missing_reserved": missing_reserved,
            "extra_mapped": extra_mapped,
            "unexpected_disk": unexpected_disk,
            "v120": v120_details,
        }
        print(json.dumps(details, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
