# -*- coding: utf-8 -*-
"""One-shot hygiene restore of CRLF-only freeze files from audit JSON."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.freeze_hygiene_lf import restore_file_to_lf  # noqa: E402


def main() -> int:
    audit = json.loads(
        (ROOT / "audits/mvp-functional-baseline-v1/frozen-drift-audit-2.5.2.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = {
        e["path"]: e["sha256"]
        for e in json.loads(
            (ROOT / "audits/mvp-functional-baseline-v1/core-freeze-manifest.json").read_text(
                encoding="utf-8"
            )
        )["files"]
    }
    results = []
    for finding in audit["per_file_findings"]:
        if not finding.get("line_ending_only"):
            continue
        rel = finding["path"]
        base = manifest[rel]
        path = ROOT.joinpath(*rel.split("/"))
        report = restore_file_to_lf(path, base)
        results.append(report)
        print(f"OK {rel}")
        print(f"  before={report['before_sha256']}")
        print(f"  after ={report['after_sha256']}")
    print(f"restored={len(results)}")
    return 0 if len(results) == 12 else 1


if __name__ == "__main__":
    raise SystemExit(main())
