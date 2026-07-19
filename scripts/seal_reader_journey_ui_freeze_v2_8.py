# -*- coding: utf-8 -*-
"""Seal Reader Journey UI Final Freeze v2.8 from current disk hashes."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    old_path = (
        ROOT
        / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v2.7"
        / "reader-journey-ui-final-freeze-v2.7.json"
    )
    old = json.loads(old_path.read_text(encoding="utf-8"))

    changed = {
        "apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx",
        "apps/desktop/src/components/readerJourney/JourneyResizableSplit.tsx",
        "apps/desktop/src/components/readerJourney/exportJourneyPng.ts",
        "apps/desktop/src/components/readerJourney/readerJourney.css",
    }
    new_files = [
        (
            "apps/desktop/src/components/readerJourney/CanonicalJourneyChart.tsx",
            "FROZEN_JOURNEY_VISUALIZATION",
            "Canonical journey chart SVG",
        ),
        (
            "apps/desktop/src/components/readerJourney/JourneyChartToolbar.tsx",
            "FROZEN_JOURNEY_VISUALIZATION",
            "Chart height/zoom/Y-domain toolbar",
        ),
        (
            "apps/desktop/src/components/readerJourney/journeyChartScales.ts",
            "FROZEN_JOURNEY_VISUALIZATION",
            "Y/X scales, null breaks, view window",
        ),
        (
            "apps/desktop/src/components/readerJourney/journeyVisualizationConfig.ts",
            "FROZEN_JOURNEY_VISUALIZATION",
            "Global visualization v2.8 config",
        ),
    ]

    files = []
    for entry in old["files"]:
        rel = entry["path"]
        path = ROOT / Path(*rel.split("/"))
        item = dict(entry)
        item["approved_version"] = "reader-journey-ui-final-v2.8"
        item["source_thaw"] = "ui-presentation-thaw-v2-9.json"
        if path.exists():
            item["sha256"] = sha256_file(path)
        if rel in changed:
            item["responsibility"] = f"{entry.get('responsibility', '')} (viz v2.8)".strip()
        files.append(item)

    for rel, category, responsibility in new_files:
        path = ROOT / Path(*rel.split("/"))
        files.append(
            {
                "path": rel,
                "sha256": sha256_file(path),
                "category": category,
                "responsibility": responsibility,
                "approved_version": "reader-journey-ui-final-v2.8",
                "source_thaw": "ui-presentation-thaw-v2-9.json",
                "test_coverage": ["phase_1dc1_ui02_visualization_v2_8.test.tsx"],
            }
        )

    ux = [item for item in old["ux_invariants"] if "min-height=300" not in item]
    ux.extend(
        [
            "曲线默认标准高度=360px（compact/standard/expanded）",
            "Y轴默认固定0—100",
            "PNG默认导出完整旅程独立于视口缩放",
        ]
    )

    payload = {
        "baseline_name": "reader-journey-ui-final-v2.8",
        "version": "2.8",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reader Journey Visualization Global Optimization (Phase 1D-C1-UI-02)",
        "parent_baseline": "reader-journey-ui-final-v2.7",
        "parent_core_freeze": "audits/mvp-functional-baseline-v1/core-freeze-manifest.json",
        "source_thaw": "audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-9.json",
        "change_policy": {
            "direct_edit_frozen_files": False,
            "required_change_package": "reader-journey-ui-change-<version>.json",
            "notes": "Do not overwrite this manifest in place; issue a new change package and bump baseline version.",
        },
        "ux_invariants": ux,
        "ux_invariant_count": len(ux),
        "category_counts": dict(Counter(item["category"] for item in files)),
        "file_count": len(files),
        "files": files,
    }

    out_dir = ROOT / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v2.8"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "reader-journey-ui-final-freeze-v2.8.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path.relative_to(ROOT).as_posix()} files={len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
