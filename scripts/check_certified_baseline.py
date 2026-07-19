# -*- coding: utf-8 -*-
"""Offline gate: Single-Chapter Pipeline Certified Baseline v1.0 hashes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASHES = (
    ROOT
    / "audits"
    / "single-chapter-pipeline"
    / "phase-1db2-certified-file-hashes-v1.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if not HASHES.exists():
        print("CERTIFIED_BASELINE_FAIL: missing phase-1db2-certified-file-hashes-v1.json")
        return 1
    payload = json.loads(HASHES.read_text(encoding="utf-8"))
    failed: list[str] = []
    for row in payload.get("files") or []:
        rel = row["path"]
        expected = row.get("sha256")
        category = row.get("category") or ""
        path = ROOT / rel
        if not path.exists():
            failed.append(f"missing {rel}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            # CHANGEABLE_* may drift during 1D-C shell polish; still report but
            # only FROZEN_CERTIFIED_* hard-fail the gate.
            if str(category).startswith("FROZEN_CERTIFIED"):
                failed.append(f"hash_mismatch {rel} ({category})")
            else:
                print(f"NOTE changeable drift: {rel} ({category})")
    aggregate = hashlib.sha256()
    for row in sorted(
        [r for r in (payload.get("files") or []) if r.get("sha256")],
        key=lambda r: r["path"],
    ):
        # Recompute from current frozen files only for report; gate uses per-file.
        path = ROOT / row["path"]
        if not path.exists():
            continue
        if not str(row.get("category") or "").startswith("FROZEN_CERTIFIED"):
            continue
        aggregate.update(row["path"].encode("utf-8"))
        aggregate.update(b":")
        aggregate.update(sha256_file(path).encode("utf-8"))
        aggregate.update(b"\n")
    print("StoryLens Certified Baseline Check")
    print(f"baseline: {payload.get('baseline_id')}")
    print(f"recorded_aggregate: {payload.get('aggregate_sha256')}")
    print(f"frozen_live_aggregate: {aggregate.hexdigest()}")
    if failed:
        print("CERTIFIED_BASELINE_FAIL")
        for item in failed:
            print(" ", item)
        return 1
    print("CERTIFIED_BASELINE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
