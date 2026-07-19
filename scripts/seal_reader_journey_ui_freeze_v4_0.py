# -*- coding: utf-8 -*-
"""Seal Reader Journey UI Final Freeze v4.0 from current disk hashes."""
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
        / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v3.0"
        / "reader-journey-ui-final-freeze-v3.0.json"
    )
    old = json.loads(old_path.read_text(encoding="utf-8"))

    changed = {
        "apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx",
        "apps/desktop/src/components/readerJourney/ReaderJourneySyncWorkspace.tsx",
        "apps/desktop/src/components/readerJourney/exportJourneyPng.ts",
        "apps/desktop/src/components/readerJourney/readerJourney.css",
        "apps/desktop/src/components/readerJourney/JourneyChartToolbar.tsx",
        "apps/desktop/src/components/readerJourney/JourneyChartToolRail.tsx",
        "apps/desktop/src/components/readerJourney/journeyVisualizationConfig.ts",
        "apps/desktop/src/components/readerJourney/JourneyAnchoredMenu.tsx",
    }

    files = []
    for entry in old["files"]:
        rel = entry["path"]
        path = ROOT / Path(*rel.split("/"))
        item = dict(entry)
        item["approved_version"] = "reader-journey-ui-final-v4.0"
        item["source_thaw"] = "ui-presentation-thaw-v2-12.json"
        if path.exists():
            item["sha256"] = sha256_file(path)
        if rel in changed:
            item["responsibility"] = (
                f"{entry.get('responsibility', '')} (workspace layout v4.0)"
            ).strip()
            item["test_coverage"] = ["phase_1dc1_ui05_workspace_layout_v4_0.test.tsx"]
        files.append(item)

    anchored = "apps/desktop/src/components/readerJourney/JourneyAnchoredMenu.tsx"
    if not any(f["path"] == anchored for f in files):
        path = ROOT / Path(*anchored.split("/"))
        files.append(
            {
                "path": anchored,
                "sha256": sha256_file(path),
                "category": "FROZEN_JOURNEY_COMPOSITION",
                "responsibility": "Portal anchored menu with viewport clamping (layout v4.0)",
                "approved_version": "reader-journey-ui-final-v4.0",
                "source_thaw": "ui-presentation-thaw-v2-12.json",
                "test_coverage": ["phase_1dc1_ui05_workspace_layout_v4_0.test.tsx"],
            }
        )

    ux = [
        item
        for item in old.get("ux_invariants", [])
        if "竖向工具轨" not in item and "PNG默认导出完整旅程 v3.0" not in item
    ]
    ux.extend(
        [
            "CSS Grid：Source | Main(minmax 720px) | Inspector；Inspector 不覆盖 Chart",
            "删除竖向工具轨单字缩写；主区顶部完整中文工具栏 + Portal 更多设置",
            ">=1440 右侧 Dock；1100-1439 底部 Dock；<1100 页内 Tab",
            "滚动所有权：Workspace overflow hidden；Source/Main/Inspector 各自最多一条纵向滚动；Chart 无纵向滚动",
            "保留 v3.0 Plot 地板：svg=420 / plot>=340 / shell>=440 / Y 0-100",
            "PNG 默认导出完整旅程 v4.0（不含侧栏/正文/Inspector/按钮）",
        ]
    )

    payload = {
        "baseline_name": "reader-journey-ui-final-v4.0",
        "version": "4.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reader Journey Workspace Layout v4.0 (Phase 1D-C1-UI-05)",
        "parent_baseline": "reader-journey-ui-final-v3.0",
        "source_thaw": "audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-12.json",
        "human_uat_parent_verdict": "READER_JOURNEY_VISUALIZATION_V3_0_HUMAN_UAT_FAILED",
        "files": files,
        "ux_invariants": ux,
        "category_counts": dict(Counter(item.get("category") for item in files)),
        "rollback": [
            "Point scripts/check_reader_journey_ui_freeze.py to reader-journey-ui-final-v3.0",
            "Remove ui-presentation-thaw-v2-12.json from check_core_freeze.py DEFAULT_THAWS",
            "Restore frozen files from v3.0 hashes",
        ],
    }

    out_dir = ROOT / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v4.0"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "reader-journey-ui-final-freeze-v4.0.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"files={len(files)} changed={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
