# -*- coding: utf-8 -*-
"""Generate Reader Journey UI Final Freeze v2.7 manifests from real import graph."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP_SRC = ROOT / "apps" / "desktop" / "src"
OUT_DIR = ROOT / "audits" / "mvp-functional-baseline-v1" / "reader-journey-ui-final-v2.7"

ENTRY_POINTS = [
    "apps/desktop/src/components/readerJourney/ReaderJourneyWorkspace.tsx",
    "apps/desktop/src/components/readerJourney/ReaderJourneySyncWorkspace.tsx",
    "apps/desktop/src/components/readerJourney/JourneySceneDetailPanel.tsx",
    "apps/desktop/src/components/readerJourney/inspectorShell.tsx",
    "apps/desktop/src/components/readerJourney/exportJourneyPng.ts",
    "apps/desktop/src/components/readerJourney/journeyUiLabels.ts",
    "apps/desktop/src/components/readerJourney/journeySelectionTransaction.ts",
    "apps/desktop/src/hooks/useJourneySelection.ts",
    "apps/desktop/src/components/readerJourney/readerJourney.css",
    "apps/desktop/src/components/readerJourney/syncWorkspace.css",
]

# Relative import resolver: only follow local project modules under apps/desktop/src
IMPORT_RE = re.compile(
    r"""(?:import|export)\s+(?:type\s+)?[\s\S]*?from\s*['"](\.[^'"]+)['"]"""
    r"""|import\s+['"](\.[^'"]+)['"]""",
    re.MULTILINE,
)

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    (
        "FROZEN_JOURNEY_COMPOSITION",
        [
            "ReaderJourneyWorkspace.tsx",
            "ReaderJourneySyncWorkspace.tsx",
            "JourneyResizableSplit.tsx",
            "SplitPane.tsx",
            "StructuredChapterTextPane.tsx",
            "SceneStructureDrawer.tsx",
            "overviewMode.ts",
            "States.tsx",
        ],
    ),
    (
        "FROZEN_JOURNEY_INTERACTION",
        [
            "journeySelectionTransaction.ts",
            "useJourneySelection.ts",
            "journeySelection.ts",
        ],
    ),
    (
        "FROZEN_JOURNEY_VISUALIZATION",
        [
            "JourneyOverviewModes.tsx",
            "journeyVisualTokens.ts",
            "readerJourneyVisualization.ts",
        ],
    ),
    (
        "FROZEN_JOURNEY_INSPECTOR",
        [
            "JourneySceneDetailPanel.tsx",
            "inspectorShell.tsx",
            "sceneDetailFields.tsx",
            "safeRender.ts",
            "JourneyDetailErrorBoundary.tsx",
            "readerJourneyProfileItems.ts",
        ],
    ),
    (
        "FROZEN_JOURNEY_EXPORT",
        [
            "exportJourneyPng.ts",
            "exportSceneCard.ts",
        ],
    ),
    (
        "FROZEN_JOURNEY_PRESENTATION",
        [
            "readerJourney.css",
            "syncWorkspace.css",
            "journeyUiLabels.ts",
        ],
    ),
]

EXCLUDE_NAMES = {
    "mockVisualization.ts",
}

EXCLUDE_SUFFIXES = (".test.tsx", ".test.ts", ".spec.ts", ".spec.tsx")

RESPONSIBILITY = {
    "ReaderJourneyWorkspace.tsx": "Journey Overview + Context Inspector composition",
    "ReaderJourneySyncWorkspace.tsx": "Books/standalone sync shell, selection wiring",
    "JourneyResizableSplit.tsx": "Overview/Inspector resizable split",
    "SplitPane.tsx": "Text/journey column split",
    "StructuredChapterTextPane.tsx": "Chapter text + scroll spy surface",
    "SceneStructureDrawer.tsx": "Scene structure side drawer",
    "overviewMode.ts": "Overview/inspector URL param helpers",
    "journeySelectionTransaction.ts": "Atomic URL selection transaction",
    "useJourneySelection.ts": "Selection state hook",
    "journeySelection.ts": "Selection types",
    "JourneyOverviewModes.tsx": "Legacy overview mode panels (data retained)",
    "journeyVisualTokens.ts": "Phase/role visual tokens",
    "readerJourneyVisualization.ts": "Visualization TypeScript contract",
    "JourneySceneDetailPanel.tsx": "Scene/Phase/Question/Hook/Payoff/Risk inspectors",
    "inspectorShell.tsx": "Shared Inspector presentation shell",
    "sceneDetailFields.tsx": "Safe field list renderers",
    "safeRender.ts": "Normalize unknown analysis field shapes",
    "JourneyDetailErrorBoundary.tsx": "Inspector error boundary",
    "readerJourneyProfileItems.ts": "Profile item TypeScript types",
    "exportJourneyPng.ts": "PNG Overview export",
    "exportSceneCard.ts": "Scene card markdown export helper",
    "readerJourney.css": "Reader Journey presentation CSS",
    "syncWorkspace.css": "Sync workspace presentation CSS",
    "journeyUiLabels.ts": "Chinese label maps",
}

TEST_COVERAGE = {
    "ReaderJourneyWorkspace.tsx": [
        "phase_1cc27_context_inspector_hierarchy.test.tsx",
        "phase_1cc26_journey_analysis_focused_view.test.tsx",
        "phase_1cc262_compact_phase_navigation.test.tsx",
    ],
    "JourneySceneDetailPanel.tsx": [
        "phase_1cc27_context_inspector_hierarchy.test.tsx",
        "phase_1cc24b_scene_detail_information_architecture.test.tsx",
    ],
    "inspectorShell.tsx": ["phase_1cc27_context_inspector_hierarchy.test.tsx"],
    "journeySelectionTransaction.ts": [
        "phase_1cc253_books_route_selection_transaction.test.tsx"
    ],
    "exportJourneyPng.ts": ["phase_1cc251_blocking_ui_fix.test.tsx"],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_import(from_file: Path, spec: str) -> Path | None:
    base = (from_file.parent / spec).resolve()
    candidates = []
    if base.suffix:
        candidates.append(base)
    else:
        for ext in (".tsx", ".ts", ".css", "/index.tsx", "/index.ts"):
            candidates.append(Path(str(base) + ext) if not ext.startswith("/") else base / ext.lstrip("/"))
            if ext.startswith("/"):
                candidates.append(base.with_name(base.name + ext.replace("/index", "") + ".tsx"))
    # Also try as directory index
    if base.is_dir():
        candidates.extend([base / "index.tsx", base / "index.ts"])
    for cand in candidates:
        try:
            cand.relative_to(DESKTOP_SRC)
        except ValueError:
            continue
        if cand.is_file():
            return cand
    # bare .ts when .tsx missing
    for ext in (".tsx", ".ts"):
        cand = Path(str(base) + ext)
        if cand.is_file():
            try:
                cand.relative_to(DESKTOP_SRC)
                return cand
            except ValueError:
                pass
    return None


def rel_posix(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def walk_imports(entry_rels: list[str]) -> tuple[set[str], dict[str, list[str]]]:
    graph: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    queue: list[Path] = []
    for rel in entry_rels:
        p = ROOT / rel
        if p.exists():
            queue.append(p.resolve())
            seen.add(rel_posix(p.resolve()))

    while queue:
        current = queue.pop()
        crel = rel_posix(current)
        if current.suffix == ".css":
            continue
        text = current.read_text(encoding="utf-8")
        for match in IMPORT_RE.finditer(text):
            spec = match.group(1) or match.group(2)
            if not spec:
                continue
            target = resolve_import(current, spec)
            if not target:
                continue
            trel = rel_posix(target)
            if any(trel.endswith(suf) for suf in EXCLUDE_SUFFIXES):
                continue
            if Path(trel).name in EXCLUDE_NAMES:
                continue
            graph[crel].append(trel)
            if trel not in seen:
                seen.add(trel)
                queue.append(target)
    return seen, dict(graph)


def categorize(path: str) -> str:
    name = Path(path).name
    for category, names in CATEGORY_RULES:
        if name in names and name not in EXCLUDE_NAMES:
            return category
    if "hooks/" in path or "journeySelection" in path:
        return "FROZEN_JOURNEY_INTERACTION"
    if path.endswith(".css") or "Labels" in name:
        return "FROZEN_JOURNEY_PRESENTATION"
    if "export" in name.lower():
        return "FROZEN_JOURNEY_EXPORT"
    if (
        "Detail" in name
        or "inspector" in name.lower()
        or "safeRender" in name
        or "sceneDetail" in name
        or "ProfileItems" in name
    ):
        return "FROZEN_JOURNEY_INSPECTOR"
    if "Visualization" in name or "Visual" in name or "Overview" in name:
        return "FROZEN_JOURNEY_VISUALIZATION"
    return "FROZEN_JOURNEY_COMPOSITION"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "screenshots").mkdir(exist_ok=True)

    files, graph = walk_imports(ENTRY_POINTS)
    # Always include CSS entry points even if only side-effect imported
    for rel in ENTRY_POINTS:
        if rel.endswith(".css") and (ROOT / rel).exists():
            files.add(rel)

    freeze_files = []
    for path in sorted(files):
        name = Path(path).name
        if name in EXCLUDE_NAMES:
            continue
        if any(path.endswith(suf) for suf in EXCLUDE_SUFFIXES):
            continue
        full = ROOT / path
        if not full.is_file():
            continue
        category = categorize(path)
        freeze_files.append(
            {
                "path": path,
                "sha256": sha256_file(full),
                "category": category,
                "responsibility": RESPONSIBILITY.get(name, "Reader Journey production dependency"),
                "approved_version": "reader-journey-ui-final-v2.7",
                "source_thaw": "ui-presentation-thaw-v2-5.json",
                "test_coverage": TEST_COVERAGE.get(name, []),
            }
        )

    by_cat = defaultdict(int)
    for f in freeze_files:
        by_cat[f["category"]] += 1

    ux_invariants = [
        "页面名称为「旅程分析」",
        "页面只显示一个标题",
        "章节结论条为紧凑布局",
        "Phase 桌面四列",
        "Phase 中宽横向滚动",
        "Phase 窄屏下拉",
        "曲线 min-height=300px",
        "当前 Scene marker 数量=1",
        "Scene 首次点击不回退",
        "Phase 点击不改 Scene",
        "Context Inspector 单一实例",
        "六类 Inspector 统一骨架",
        "空状态不创建新 Run",
        "Evidence 仍可精确定位",
        "Inspector 不挤压曲线",
        "PNG 只包含 Overview",
        "Books 与独立路由都可用",
        "旧 overview URL 兼容",
        "一个 Inspector 纵向滚动容器",
        "无嵌套详情卡片墙",
    ]

    freeze_manifest = {
        "baseline_name": "reader-journey-ui-final-v2.7",
        "version": "2.7",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Final freeze of Reader Journey UI after Context Inspector hierarchy (Phase 1C-C.2.7)",
        "parent_core_freeze": "audits/mvp-functional-baseline-v1/core-freeze-manifest.json",
        "source_thaw": "audits/mvp-functional-baseline-v1/ui-presentation-thaw-v2-5.json",
        "change_policy": {
            "direct_edit_frozen_files": False,
            "required_change_package": "reader-journey-ui-change-<version>.json",
            "notes": "Do not overwrite this manifest in place; issue a new change package and bump baseline version.",
        },
        "ux_invariants": ux_invariants,
        "ux_invariant_count": len(ux_invariants),
        "category_counts": dict(by_cat),
        "file_count": len(freeze_files),
        "files": freeze_files,
    }

    dependency_map = {
        "baseline_name": "reader-journey-ui-final-v2.7",
        "entry_points": ENTRY_POINTS,
        "edges": {k: sorted(set(v)) for k, v in sorted(graph.items())},
        "nodes": sorted(files),
        "excluded": sorted(EXCLUDE_NAMES),
        "note": "Built by static relative-import walk from production entry points; no node_modules.",
    }

    route_baseline = {
        "baseline_name": "reader-journey-ui-final-v2.7",
        "routes": [
            {
                "id": "books-embedded",
                "url": "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
                "expected_title": "旅程分析",
                "expected_scene": 9,
                "expected_phase": None,
                "expected_inspector": "scene",
                "expected_metric": "engagement",
                "expected_visible_regions": [
                    "journey-analysis-title",
                    "journey-overview-curve",
                    "journey-detail-pane",
                    "journey-phase-strip",
                ],
            },
            {
                "id": "standalone-results",
                "url": "/analysis-runs/55/results?tab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
                "expected_title": "旅程分析",
                "expected_scene": 9,
                "expected_phase": None,
                "expected_inspector": "scene",
                "expected_metric": "engagement",
                "expected_visible_regions": [
                    "journey-analysis-title",
                    "journey-overview-curve",
                    "journey-detail-pane",
                ],
            },
            {
                "id": "legacy-overview-questions",
                "url": "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=questions&inspector=scene",
                "expected_title": "旅程分析",
                "expected_scene": 9,
                "expected_inspector": "scene",
                "normalized_overview": "curve",
                "expected_visible_regions": ["journey-overview-curve"],
            },
            {
                "id": "legacy-overview-diagnosis",
                "url": "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=diagnosis&inspector=scene",
                "expected_title": "旅程分析",
                "expected_scene": 9,
                "expected_inspector": "scene",
                "normalized_overview": "curve",
                "expected_visible_regions": ["journey-overview-curve"],
            },
        ],
    }

    test_baseline = {
        "baseline_name": "reader-journey-ui-final-v2.7",
        "unit_tests": [
            "apps/desktop/src/components/readerJourney/phase_1cc27_context_inspector_hierarchy.test.tsx",
            "apps/desktop/src/components/readerJourney/phase_1cc26_journey_analysis_focused_view.test.tsx",
            "apps/desktop/src/components/readerJourney/phase_1cc262_compact_phase_navigation.test.tsx",
            "apps/desktop/src/components/readerJourney/phase_1cc261_header_insight_density.test.tsx",
            "apps/desktop/src/components/readerJourney/phase_1cc253_books_route_selection_transaction.test.tsx",
            "apps/desktop/src/components/readerJourney/phase_1cc252_context_inspector.test.tsx",
        ],
        "e2e_tests": [
            "apps/desktop/e2e/phase_1cc27_context_inspector_hierarchy.spec.ts",
            "apps/desktop/e2e/phase_1cc27_reader_journey_ui_final_visual_baseline.spec.ts",
            "apps/desktop/e2e/phase_1cc26_journey_analysis_focused_view.spec.ts",
            "apps/desktop/e2e/phase_1cc262_compact_phase_navigation.spec.ts",
            "apps/desktop/e2e/phase_1cc261_header_insight_density.spec.ts",
        ],
        "gates": [
            "check_core_freeze.py",
            "check_ui_presentation_thaw.py",
            "check_reader_journey_ui_freeze.py",
            "check_project.py",
            "pytest",
            "ruff",
            "typecheck",
            "lint",
            "vitest",
            "build",
            "test:e2e",
        ],
    }

    visual_baseline = {
        "baseline_name": "reader-journey-ui-final-v2.7",
        "screenshots_dir": "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v2.7/screenshots",
        "screenshots": [
            {
                "file": "books-1920x1080-scene.png",
                "viewport": {"width": 1920, "height": 1080},
                "route": "books-embedded",
                "focus": "scene-inspector",
            },
            {
                "file": "books-1280x720-phase.png",
                "viewport": {"width": 1280, "height": 720},
                "route": "books-embedded-phase",
                "focus": "phase-inspector",
            },
            {
                "file": "books-1024x768-empty-state.png",
                "viewport": {"width": 1024, "height": 768},
                "route": "books-no-selection",
                "focus": "empty-state",
            },
            {
                "file": "standalone-1920x1080-scene.png",
                "viewport": {"width": 1920, "height": 1080},
                "route": "standalone-results",
                "focus": "scene-inspector",
            },
            {
                "file": "png-export-reader-journey-v2.7.png",
                "viewport": {"width": 1920, "height": 1080},
                "route": "books-embedded",
                "focus": "png-export-overview",
            },
        ],
        "checks": [
            "no text occlusion",
            "no duplicate titles",
            "no overlapping tags",
            "phase titles readable",
            "curve complete",
            "inspector hierarchy clear",
            "empty state compact",
            "png not cropped",
        ],
        "note": "Screenshots are visual references only; DOM/E2E assertions remain authoritative.",
    }

    (OUT_DIR / "reader-journey-ui-final-freeze-v2.7.json").write_text(
        json.dumps(freeze_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "reader-journey-ui-dependency-map-v2.7.json").write_text(
        json.dumps(dependency_map, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "reader-journey-ui-route-baseline-v2.7.json").write_text(
        json.dumps(route_baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "reader-journey-ui-test-baseline-v2.7.json").write_text(
        json.dumps(test_baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "reader-journey-ui-visual-baseline-v2.7.json").write_text(
        json.dumps(visual_baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(freeze_files)} frozen files to {OUT_DIR}")
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
