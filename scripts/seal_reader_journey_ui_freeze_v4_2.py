# -*- coding: utf-8 -*-
"""Seal Reader Journey UI Final Freeze v4.2 from current disk hashes."""
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
        / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v4.1"
        / "reader-journey-ui-final-freeze-v4.1.json"
    )
    old = json.loads(old_path.read_text(encoding="utf-8"))

    changed = {
        "apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx",
        "apps/desktop/src/components/readerJourney/JourneyChartToolbar.tsx",
        "apps/desktop/src/components/readerJourney/readerJourney.css",
        "apps/desktop/src/components/readerJourney/journeyVisualizationConfig.ts",
        "apps/desktop/src/components/readerJourney/JourneyAnchoredMenu.tsx",
        "apps/desktop/src/components/readerJourney/journeyUiLabels.ts",
    }

    new_files = [
        (
            "apps/desktop/src/components/readerJourney/MetricSelectorPanel.tsx",
            "In-flow metric listbox panel (v4.2)",
        ),
        (
            "apps/desktop/src/components/readerJourney/JourneyPopover.tsx",
            "Shared JourneyPopover / overlay-root popover (v4.2)",
        ),
        (
            "apps/desktop/src/components/readerJourney/journeyOverlayTokens.ts",
            "Unified z-index and overlay-root helpers (v4.2)",
        ),
    ]

    files = []
    for entry in old["files"]:
        rel = entry["path"]
        path = ROOT / Path(*rel.split("/"))
        item = dict(entry)
        item["approved_version"] = "reader-journey-ui-final-v4.2"
        item["source_thaw"] = "ui-presentation-thaw-v2-14.json"
        if path.exists():
            item["sha256"] = sha256_file(path)
        if rel in changed:
            item["responsibility"] = (
                f"{entry.get('responsibility', '')} (metric selector overlay v4.2)"
            ).strip()
            item["test_coverage"] = ["phase_1dc1_ui07_metric_selector_v4_2.test.tsx"]
        files.append(item)

    for rel, responsibility in new_files:
        if not any(f["path"] == rel for f in files):
            path = ROOT / Path(*rel.split("/"))
            files.append(
                {
                    "path": rel,
                    "sha256": sha256_file(path),
                    "category": "FROZEN_JOURNEY_COMPOSITION",
                    "responsibility": responsibility,
                    "approved_version": "reader-journey-ui-final-v4.2",
                    "source_thaw": "ui-presentation-thaw-v2-14.json",
                    "test_coverage": ["phase_1dc1_ui07_metric_selector_v4_2.test.tsx"],
                }
            )

    ux = list(old.get("ux_invariants", []))
    ux.extend(
        [
            "MetricSelectorPanel 进入文档流：Toolbar 下、Phase 上；展开推动 Phase/Chart，禁止 absolute/fixed 覆盖",
            "简单菜单统一 JourneyPopover→journey-overlay-root；z-index content0/sticky10/popover40/tooltip50/modal100",
            "指标面板 max-height 280px、实心背景、2–4 列 Grid；窄屏全宽内嵌；PNG 导出时隐藏打开面板",
        ]
    )

    payload = {
        "baseline_name": "reader-journey-ui-final-v4.2",
        "version": "4.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reader Journey Metric Selector and Overlay System v4.2 (Phase 1D-C1-UI-07)",
        "parent_baseline": "reader-journey-ui-final-v4.1",
        "source_thaw": "audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-14.json",
        "human_uat_parent_verdict": "READER_JOURNEY_RESIZABLE_WORKSPACE_V4_1_HUMAN_UAT_FAILED",
        "defect_addressed": "DEFECT-UAT-009 Metric Selector Overlays Journey Content",
        "files": files,
        "ux_invariants": ux,
        "category_counts": dict(Counter(item.get("category") for item in files)),
        "rollback": [
            "Point scripts/check_reader_journey_ui_freeze.py to reader-journey-ui-final-v4.1",
            "Remove ui-presentation-thaw-v2-14.json from check_core_freeze.py DEFAULT_THAWS",
            "Restore frozen files from v4.1 hashes",
        ],
    }

    out_dir = ROOT / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v4.2"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "reader-journey-ui-final-freeze-v4.2.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"files={len(files)} changed={len(changed)} new={len(new_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
