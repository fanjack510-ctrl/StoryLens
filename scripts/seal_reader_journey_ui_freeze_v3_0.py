# -*- coding: utf-8 -*-
"""Seal Reader Journey UI Final Freeze v3.0 from current disk hashes."""
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
        / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v2.9"
        / "reader-journey-ui-final-freeze-v2.9.json"
    )
    old = json.loads(old_path.read_text(encoding="utf-8"))

    changed = {
        "apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx",
        "apps/desktop/src/components/readerJourney/JourneyResizableSplit.tsx",
        "apps/desktop/src/components/readerJourney/exportJourneyPng.ts",
        "apps/desktop/src/components/readerJourney/readerJourney.css",
        "apps/desktop/src/components/readerJourney/CanonicalJourneyChart.tsx",
        "apps/desktop/src/components/readerJourney/JourneyChartToolbar.tsx",
        "apps/desktop/src/components/readerJourney/JourneyChartToolRail.tsx",
        "apps/desktop/src/components/readerJourney/journeyVisualizationConfig.ts",
        "apps/desktop/src/components/readerJourney/SplitPane.tsx",
        "apps/desktop/src/components/readerJourney/syncWorkspace.css",
    }

    files = []
    for entry in old["files"]:
        rel = entry["path"]
        path = ROOT / Path(*rel.split("/"))
        item = dict(entry)
        item["approved_version"] = "reader-journey-ui-final-v3.0"
        item["source_thaw"] = "ui-presentation-thaw-v2-11.json"
        if path.exists():
            item["sha256"] = sha256_file(path)
        if rel in changed:
            item["responsibility"] = f"{entry.get('responsibility', '')} (viz v3.0 full plot)".strip()
            item["test_coverage"] = ["phase_1dc1_ui04_visualization_v3_0.test.tsx"]
        files.append(item)

    # New file not in v2.9 freeze
    rail = "apps/desktop/src/components/readerJourney/JourneyChartToolRail.tsx"
    if not any(f["path"] == rail for f in files):
        path = ROOT / Path(*rail.split("/"))
        files.append(
            {
                "path": rail,
                "sha256": sha256_file(path),
                "category": "FROZEN_JOURNEY_COMPOSITION",
                "responsibility": "Vertical chart tool rail (viz v3.0)",
                "approved_version": "reader-journey-ui-final-v3.0",
                "source_thaw": "ui-presentation-thaw-v2-11.json",
                "test_coverage": ["phase_1dc1_ui04_visualization_v3_0.test.tsx"],
            }
        )

    ux = [
        item
        for item in old.get("ux_invariants", [])
        if "408" not in item and "plot_area_height=340" not in item
    ]
    ux.extend(
        [
            "曲线默认 svg_height=420 / plot_area_height>=340 / shell>=440",
            "Y轴五个刻度 0/25/50/75/100 默认完整可见，禁止纵向裁剪",
            "竖向工具轨替代顶部主工具栏；更多设置收纳高度/聚焦/缩放",
            "Inspector 默认收起摘要条；展开不压缩 Plot 高度",
            "Scene 导航条位于 SVG 下方",
            "clipPath 高度等于实时 plotHeight；节点不被 clip 裁半径",
            "PNG默认导出完整旅程 v3.0",
        ]
    )

    payload = {
        "baseline_name": "reader-journey-ui-final-v3.0",
        "version": "3.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reader Journey Visualization Full Plot Restoration and Vertical Tool Rail (Phase 1D-C1-UI-04)",
        "parent_baseline": "reader-journey-ui-final-v2.9",
        "source_thaw": "audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-11.json",
        "human_uat_parent_verdict": "READER_JOURNEY_VISUALIZATION_V2_9_HUMAN_UAT_FAILED",
        "files": files,
        "ux_invariants": ux,
        "category_counts": dict(Counter(item.get("category") for item in files)),
    }

    out_dir = ROOT / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v3.0"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "reader-journey-ui-final-freeze-v3.0.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"files={len(files)} changed={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
