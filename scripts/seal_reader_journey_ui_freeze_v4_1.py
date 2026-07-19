# -*- coding: utf-8 -*-
"""Seal Reader Journey UI Final Freeze v4.1 from current disk hashes."""
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
        / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v4.0"
        / "reader-journey-ui-final-freeze-v4.0.json"
    )
    old = json.loads(old_path.read_text(encoding="utf-8"))

    changed = {
        "apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx",
        "apps/desktop/src/components/readerJourney/JourneyChartToolbar.tsx",
        "apps/desktop/src/components/readerJourney/readerJourney.css",
        "apps/desktop/src/components/readerJourney/journeyVisualizationConfig.ts",
        "apps/desktop/src/components/readerJourney/JourneyPaneSplitter.tsx",
        "apps/desktop/src/components/readerJourney/journeyPaneWidth.ts",
    }

    files = []
    for entry in old["files"]:
        rel = entry["path"]
        path = ROOT / Path(*rel.split("/"))
        item = dict(entry)
        item["approved_version"] = "reader-journey-ui-final-v4.1"
        item["source_thaw"] = "ui-presentation-thaw-v2-13.json"
        if path.exists():
            item["sha256"] = sha256_file(path)
        if rel in changed:
            item["responsibility"] = (
                f"{entry.get('responsibility', '')} (resizable workspace v4.1)"
            ).strip()
            item["test_coverage"] = ["phase_1dc1_ui06_resizable_workspace_v4_1.test.tsx"]
        files.append(item)

    for rel, responsibility in (
        (
            "apps/desktop/src/components/readerJourney/JourneyPaneSplitter.tsx",
            "Column/row pane splitter with pointer capture and keyboard (v4.1)",
        ),
        (
            "apps/desktop/src/components/readerJourney/journeyPaneWidth.ts",
            "Pane width ranges and preferred/effective clamp helpers (v4.1)",
        ),
    ):
        if not any(f["path"] == rel for f in files):
            path = ROOT / Path(*rel.split("/"))
            files.append(
                {
                    "path": rel,
                    "sha256": sha256_file(path),
                    "category": "FROZEN_JOURNEY_COMPOSITION",
                    "responsibility": responsibility,
                    "approved_version": "reader-journey-ui-final-v4.1",
                    "source_thaw": "ui-presentation-thaw-v2-13.json",
                    "test_coverage": ["phase_1dc1_ui06_resizable_workspace_v4_1.test.tsx"],
                }
            )

    ux = [
        item
        for item in old.get("ux_invariants", [])
        if "minmax 720px" not in item and "CSS Grid：Source | Main" not in item
    ]
    ux.extend(
        [
            "CSS Grid：Source | Splitter | Main(minmax 640px) | Splitter | Inspector；可拖拽栏宽",
            "preferredWidth 持久化；effectiveWidth 临时 Clamp；折叠不覆盖偏好",
            ">=1440 双侧竖向分隔柄；1100-1439 左分隔柄 + 底部 Dock 水平分隔柄；<1100 无分隔柄",
            "滚动所有权：Workspace overflow hidden；Source/Main/Inspector 各自纵向滚动；Chart 无纵向滚动",
            "保留 Plot 地板：svg=420 / plot>=340 / shell>=440 / Y 0-100",
            "PNG 默认导出完整旅程不受栏宽影响（文件名仍可沿用 v4.0 模式）",
        ]
    )

    payload = {
        "baseline_name": "reader-journey-ui-final-v4.1",
        "version": "4.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reader Journey Resizable Workspace v4.1 (Phase 1D-C1-UI-06)",
        "parent_baseline": "reader-journey-ui-final-v4.0",
        "source_thaw": "audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-13.json",
        "human_uat_parent_verdict": "READER_JOURNEY_WORKSPACE_LAYOUT_V4_0_READY_FOR_HUMAN_UAT",
        "files": files,
        "ux_invariants": ux,
        "category_counts": dict(Counter(item.get("category") for item in files)),
        "rollback": [
            "Point scripts/check_reader_journey_ui_freeze.py to reader-journey-ui-final-v4.0",
            "Remove ui-presentation-thaw-v2-13.json from check_core_freeze.py DEFAULT_THAWS",
            "Restore frozen files from v4.0 hashes",
        ],
    }

    out_dir = ROOT / "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v4.1"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "reader-journey-ui-final-freeze-v4.1.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"files={len(files)} changed={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
