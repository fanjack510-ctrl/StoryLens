# -*- coding: utf-8 -*-
"""Seal Reader Journey UI Final Freeze v2.9 from current disk hashes."""
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
        / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v2.8"
        / "reader-journey-ui-final-freeze-v2.8.json"
    )
    old = json.loads(old_path.read_text(encoding="utf-8"))

    changed = {
        "apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx",
        "apps/desktop/src/components/readerJourney/JourneyResizableSplit.tsx",
        "apps/desktop/src/components/readerJourney/exportJourneyPng.ts",
        "apps/desktop/src/components/readerJourney/readerJourney.css",
        "apps/desktop/src/components/readerJourney/CanonicalJourneyChart.tsx",
        "apps/desktop/src/components/readerJourney/JourneyChartToolbar.tsx",
        "apps/desktop/src/components/readerJourney/journeyVisualizationConfig.ts",
    }

    files = []
    for entry in old["files"]:
        rel = entry["path"]
        path = ROOT / Path(*rel.split("/"))
        item = dict(entry)
        item["approved_version"] = "reader-journey-ui-final-v2.9"
        item["source_thaw"] = "ui-presentation-thaw-v2-10.json"
        if path.exists():
            item["sha256"] = sha256_file(path)
        if rel in changed:
            item["responsibility"] = f"{entry.get('responsibility', '')} (viz v2.9 restore)".strip()
            item["test_coverage"] = ["phase_1dc1_ui03_visualization_v2_9.test.tsx"]
        files.append(item)

    ux = [
        item
        for item in old.get("ux_invariants", [])
        if "360" not in item and "compact/standard/expanded" not in item
    ]
    ux.extend(
        [
            "曲线默认 plot_area_height=340px（SVG standard=408；expanded plot=480）",
            "Y轴默认固定0—100；聚焦数据仅在更多图表设置",
            "Inspector 默认收起；曲线为页面主视觉",
            "Scene<=15 一次完整展示，无放大/缩小控件",
            "PNG默认导出完整旅程独立于视口缩放与 Inspector",
            "图表内部 overflow-y 禁止 auto/scroll",
        ]
    )

    payload = {
        "baseline_name": "reader-journey-ui-final-v2.9",
        "version": "2.9",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reader Journey Visualization Canonical Journey View Restoration (Phase 1D-C1-UI-03)",
        "parent_baseline": "reader-journey-ui-final-v2.8",
        "source_thaw": "audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-10.json",
        "human_uat_parent_verdict": "READER_JOURNEY_VISUALIZATION_V2_8_HUMAN_UAT_FAILED",
        "files": files,
        "ux_invariants": ux,
        "category_counts": dict(Counter(item.get("category") for item in files)),
    }

    out_dir = ROOT / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v2.9"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "reader-journey-ui-final-freeze-v2.9.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"files={len(files)} changed={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
