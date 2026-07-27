# -*- coding: utf-8 -*-
"""Phase 1D-A: Single-Chapter Journey Template governance check (read-only).

Validates that Books + Standalone adapters share one canonical Reader Journey
Template v2.7 entry. Does not modify files, database, or freeze manifests.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = (
    ROOT
    / "audits"
    / "mvp-functional-baseline-v1"
    / "single-chapter-journey-template-v2.7.json"
)
DEFAULT_FREEZE = (
    ROOT
    / "audits"
    / "mvp-functional-baseline-v1"
    / "reader-journey-ui-final-v2.7"
    / "reader-journey-ui-final-freeze-v2.7.json"
)
DEFAULT_DEP_MAP = (
    ROOT
    / "audits"
    / "mvp-functional-baseline-v1"
    / "reader-journey-ui-final-v2.7"
    / "reader-journey-ui-dependency-map-v2.7.json"
)
DEFAULT_REPORT = (
    ROOT
    / "audits"
    / "mvp-functional-baseline-v1"
    / "single-chapter-template-conformance-report-v2.7.json"
)

PROD_SCAN_ROOTS = [
    ROOT / "apps" / "desktop" / "src" / "components" / "readerJourney",
    ROOT / "apps" / "desktop" / "src" / "pages",
    ROOT / "apps" / "desktop" / "src" / "components" / "chapterResult",
    ROOT / "apps" / "desktop" / "src" / "hooks",
]

SPECIAL_CASE_PATTERNS = [
    ("book-id-literal", re.compile(r"\bbookId\s*===\s*\d+")),
    ("chapter-id-literal", re.compile(r"\bchapterId\s*===\s*\d+")),
    ("run-55-literal", re.compile(r"\b(?:analysisRun(?:Id)?|runId)\s*===\s*55\b")),
    ("analysis-run-55-url", re.compile(r"analysisRun\s*[=:]\s*['\"]?55\b")),
    ("scene-count-14", re.compile(r"\bsceneCount\s*===\s*14\b")),
    ("phase-count-4", re.compile(r"\bphaseCount\s*===\s*4\b")),
    ("scene-nodes-length-14", re.compile(r"scene_nodes\.length\s*===\s*14")),
    ("phases-length-4", re.compile(r"phases\.length\s*===\s*4")),
]

TITLE_SPECIAL_PATTERNS = [
    ("novel-title-戏鬼", re.compile(r"===\s*['\"]戏鬼")),
    ("novel-title-镜中人", re.compile(r"===\s*['\"]镜中人")),
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def is_production_source(path: Path) -> bool:
    name = path.name
    if name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
        return False
    if "mockSingleChapterJourneyTemplateFixtures" in name:
        return False
    if name.endswith((".ts", ".tsx", ".css")):
        return True
    return False


def collect_production_files() -> list[Path]:
    files: list[Path] = []
    for root in PROD_SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and is_production_source(path):
                files.append(path)
    return sorted(files)


def scan_special_cases(files: list[Path]) -> list[dict]:
    hits: list[dict] = []
    for path in files:
        text = read_text(path)
        rel = path.relative_to(ROOT).as_posix()
        for kind, pattern in SPECIAL_CASE_PATTERNS + TITLE_SPECIAL_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                hits.append(
                    {
                        "kind": kind,
                        "path": rel,
                        "line": line,
                        "snippet": match.group(0),
                    }
                )
    return hits


def find_workspace_imports() -> list[dict]:
    """Locate production imports of ReaderJourneyWorkspace."""
    results: list[dict] = []
    pattern = re.compile(
        r"""from\s+['"].*ReaderJourneyWorkspace['"]|import\s*\(\s*['"].*ReaderJourneyWorkspace['"]"""
    )
    for path in collect_production_files():
        text = read_text(path)
        if "ReaderJourneyWorkspace" not in text:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.endswith("ReaderJourneyWorkspace.tsx"):
            continue
        if pattern.search(text) or re.search(
            r"import\s*\{[^}]*ReaderJourneyWorkspace", text
        ):
            results.append({"path": rel, "imports_workspace": True})
    return results


def find_sync_imports() -> list[dict]:
    results: list[dict] = []
    for path in collect_production_files():
        text = read_text(path)
        if "ReaderJourneySyncWorkspace" not in text:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.endswith("ReaderJourneySyncWorkspace.tsx"):
            continue
        if re.search(r"import\s*\{[^}]*ReaderJourneySyncWorkspace", text):
            results.append({"path": rel, "imports_sync": True})
    return results


def scan_version_strings() -> list[dict]:
    """Report where UI template version 2.7 / baseline id appear.

    Uses an explicit allowlist (no recursive ** globs) to avoid scanning
    generated conformance reports and binary screenshot trees.
    """
    locations: list[dict] = []
    scan_files = [
        ROOT
        / "audits"
        / "mvp-functional-baseline-v1"
        / "reader-journey-ui-final-v2.7"
        / "reader-journey-ui-final-freeze-v2.7.json",
        ROOT
        / "audits"
        / "mvp-functional-baseline-v1"
        / "reader-journey-ui-final-v2.7"
        / "reader-journey-ui-dependency-map-v2.7.json",
        ROOT
        / "audits"
        / "mvp-functional-baseline-v1"
        / "reader-journey-ui-final-v2.7"
        / "reader-journey-ui-route-baseline-v2.7.json",
        ROOT
        / "audits"
        / "mvp-functional-baseline-v1"
        / "reader-journey-ui-final-v2.7"
        / "reader-journey-ui-test-baseline-v2.7.json",
        ROOT
        / "audits"
        / "mvp-functional-baseline-v1"
        / "reader-journey-ui-final-v2.7"
        / "reader-journey-ui-visual-baseline-v2.7.json",
        ROOT
        / "audits"
        / "mvp-functional-baseline-v1"
        / "single-chapter-journey-template-v2.7.json",
        ROOT / "docs" / "47_reader_journey_ui_final_freeze_v2_7.md",
        ROOT / "docs" / "48_single_chapter_journey_template_governance.md",
        ROOT / "scripts" / "check_reader_journey_ui_freeze.py",
        ROOT / "scripts" / "check_single_chapter_journey_template.py",
        ROOT / "scripts" / "generate_reader_journey_ui_final_v2_7.py",
        ROOT / "apps" / "desktop" / "src" / "components" / "readerJourney" / "journeyUiLabels.ts",
        ROOT
        / "apps"
        / "desktop"
        / "e2e"
        / "phase_1cc27_reader_journey_ui_final_visual_baseline.spec.ts",
    ]
    patterns = [
        ("ui-baseline-id", re.compile(r"reader-journey-ui-final-v2\.7")),
        ("version-2.7", re.compile(r'(?<![\d.])2\.7(?![\d.])')),
        ("template-version", re.compile(r'"template_version"\s*:\s*"2\.7"')),
    ]
    seen: set[tuple[str, str, int]] = set()
    for path in scan_files:
        if not path.is_file():
            continue
        try:
            text = read_text(path)
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        category = classify_version_file(rel)
        for kind, pattern in patterns:
            # Cap per-file matches to keep the report bounded.
            for match in list(pattern.finditer(text))[:40]:
                line = text.count("\n", 0, match.start()) + 1
                key = (rel, kind, line)
                if key in seen:
                    continue
                seen.add(key)
                locations.append(
                    {
                        "path": rel,
                        "line": line,
                        "kind": kind,
                        "category": category,
                        "snippet": match.group(0),
                        "drift_risk": category
                        in {"ui-title-comment", "test", "docs"}
                        and kind == "version-2.7",
                    }
                )
    return locations


def classify_version_file(rel: str) -> str:
    if rel.endswith("reader-journey-ui-final-freeze-v2.7.json"):
        return "authoritative-manifest"
    if "single-chapter-journey-template-v2.7.json" in rel:
        return "template-governance-manifest"
    if rel.startswith("audits/"):
        return "audit-manifest"
    if rel.startswith("docs/"):
        return "docs"
    if rel.startswith("scripts/"):
        return "gate-script"
    if rel.endswith("journeyUiLabels.ts"):
        return "ui-title-comment"
    if "/e2e/" in rel or rel.endswith(".test.tsx") or rel.endswith(".spec.ts"):
        return "test"
    return "other"


def verify_chain_files(chain: list[str]) -> list[str]:
    missing = []
    for rel in chain:
        if not (ROOT / Path(*rel.split("/"))).exists():
            missing.append(rel)
    return missing


def build_report(template: dict, write_report: bool) -> dict:
    freeze_path = ROOT / Path(*str(template.get("freeze_manifest") or DEFAULT_FREEZE.relative_to(ROOT).as_posix()).split("/"))
    dep_path = ROOT / Path(*str(template.get("dependency_map") or DEFAULT_DEP_MAP.relative_to(ROOT).as_posix()).split("/"))
    if not freeze_path.exists():
        freeze_path = DEFAULT_FREEZE
    if not dep_path.exists():
        dep_path = DEFAULT_DEP_MAP

    freeze = json.loads(read_text(freeze_path))
    dep_map = json.loads(read_text(dep_path))

    canonical = template["canonical_entry"]
    composition = template.get("composition_shell")
    freeze_files = {entry["path"] for entry in freeze.get("files") or []}
    dep_nodes = set(dep_map.get("nodes") or [])

    issues: list[str] = []
    checks: dict[str, object] = {}

    canonical_exists = (ROOT / Path(*canonical.split("/"))).exists()
    checks["canonical_entry_exists"] = canonical_exists
    if not canonical_exists:
        issues.append(f"canonical entry missing: {canonical}")

    if composition:
        composition_exists = (ROOT / Path(*composition.split("/"))).exists()
        checks["composition_shell_exists"] = composition_exists
        if not composition_exists:
            issues.append(f"composition shell missing: {composition}")

    adapters = template.get("route_adapters") or []
    checks["route_adapter_count"] = len(adapters)
    if len(adapters) < 2:
        issues.append("expected Books + Standalone route adapters")

    adapter_ok: list[dict] = []
    for adapter in adapters:
        chain = adapter.get("chain") or []
        missing = verify_chain_files(chain)
        points = False
        if chain:
            # Last node should be canonical; Sync should appear before it.
            points = chain[-1] == canonical and any(
                "ReaderJourneySyncWorkspace" in step for step in chain
            )
        adapter_ok.append(
            {
                "id": adapter.get("id"),
                "chain_complete": not missing,
                "missing": missing,
                "points_to_canonical": points,
                "role": adapter.get("role"),
            }
        )
        if missing:
            issues.append(f"adapter {adapter.get('id')} missing files: {missing}")
        if not points:
            issues.append(f"adapter {adapter.get('id')} does not end at canonical entry")
    checks["route_adapters"] = adapter_ok

    # Dependencies of canonical/composition must be in freeze graph when they are journey files.
    journey_deps_ok = canonical in freeze_files and (
        not composition or composition in freeze_files
    )
    checks["canonical_in_freeze"] = canonical in freeze_files
    checks["composition_in_freeze"] = (not composition) or composition in freeze_files
    if not journey_deps_ok:
        issues.append("canonical/composition not listed in v2.7 freeze manifest")

    # Production imports of Workspace should only come from SyncWorkspace.
    workspace_importers = find_workspace_imports()
    unexpected = [
        item
        for item in workspace_importers
        if not item["path"].endswith("ReaderJourneySyncWorkspace.tsx")
    ]
    checks["workspace_importers"] = workspace_importers
    checks["unexpected_workspace_importers"] = unexpected
    if unexpected:
        issues.append(
            "ReaderJourneyWorkspace imported outside SyncWorkspace: "
            + ", ".join(item["path"] for item in unexpected)
        )

    sync_importers = find_sync_imports()
    checks["sync_importers"] = sync_importers
    allowed_sync_importers = {
        "apps/desktop/src/pages/AnalysisResultsPage.tsx",
        "apps/desktop/src/components/readerJourney/WorkspaceJourneyPane.tsx",
    }
    # Standalone results + Books workspace pane are intentional SyncWorkspace entry points.
    sync_unexpected = [
        item for item in sync_importers if item["path"] not in allowed_sync_importers
    ]
    checks["unexpected_sync_importers"] = sync_unexpected
    if sync_unexpected:
        issues.append(
            "ReaderJourneySyncWorkspace imported outside allowed entry points: "
            + ", ".join(item["path"] for item in sync_unexpected)
        )

    # Second production template entry?
    duplicate_candidates = []
    for path in (ROOT / "apps" / "desktop" / "src").rglob("*Journey*Workspace*.tsx"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.endswith(".test.tsx"):
            continue
        if rel in {canonical, composition}:
            continue
        if "Workspace" in path.name:
            duplicate_candidates.append(rel)
    checks["duplicate_workspace_candidates"] = duplicate_candidates
    if duplicate_candidates:
        issues.append(f"extra workspace files: {duplicate_candidates}")

    # JourneyOverviewModes is legacy non-entry — allowed to exist unused.
    legacy = template.get("legacy_non_entry_files") or []
    checks["legacy_non_entry_files"] = legacy

    special_hits = scan_special_cases(collect_production_files())
    # Filter opacity={...0.55} false positives already avoided by word-boundary patterns.
    checks["production_special_cases"] = special_hits
    checks["production_special_case_count"] = len(special_hits)
    if special_hits:
        # Report only — do not fail freeze; governance phase forbids editing frozen files.
        # Still FAIL the checker so the report is visible, unless hits are only in adapters
        # that are data wiring (none expected).
        issues.append(
            f"production special-case hits: {len(special_hits)} (report-only; do not edit frozen files)"
        )

    version_locations = scan_version_strings()
    authoritative = [
        item
        for item in version_locations
        if item["category"] == "authoritative-manifest"
    ]
    checks["version_string_locations"] = version_locations
    checks["authoritative_version_sources"] = authoritative
    checks["version_drift_risk_count"] = sum(
        1 for item in version_locations if item.get("drift_risk")
    )

    # Required regions documented
    regions = template.get("required_regions") or []
    checks["required_region_count"] = len(regions)
    if len(regions) < 8:
        issues.append("required_regions incomplete")

    # Freeze dependency nodes for journey package presence
    required_freeze_nodes = [
        canonical,
        composition,
        "apps/desktop/src/components/readerJourney/inspectorShell.tsx",
        "apps/desktop/src/components/readerJourney/exportJourneyPng.ts",
        "apps/desktop/src/components/readerJourney/readerJourney.css",
    ]
    missing_nodes = [n for n in required_freeze_nodes if n and n not in dep_nodes and n not in freeze_files]
    checks["missing_freeze_graph_nodes"] = missing_nodes
    if missing_nodes:
        issues.append(f"freeze graph missing nodes: {missing_nodes}")

    # Books + Standalone both point to canonical
    books_ok = any(
        a.get("id") == "books-embedded" and a.get("points_to_canonical") for a in adapter_ok
    )
    standalone_ok = any(
        a.get("id") == "standalone-results" and a.get("points_to_canonical") for a in adapter_ok
    )
    checks["books_points_to_canonical"] = books_ok
    checks["standalone_points_to_canonical"] = standalone_ok

    result = "PASS" if not issues else "FAIL"
    # Special-case hits are reported; if ONLY special-case issues and count==0 we're fine.
    # If special cases found, phase says "只报告；不得直接修改" — checker should PASS with
    # warnings when structural checks pass, and list special cases as warnings.
    structural_issues = [i for i in issues if not i.startswith("production special-case")]
    warnings = [i for i in issues if i.startswith("production special-case")]
    if not structural_issues:
        result = "PASS"

    report = {
        "phase": "1D-A",
        "template_id": template.get("template_id"),
        "template_version": template.get("template_version"),
        "ui_final_baseline": template.get("ui_final_baseline"),
        "canonical_entry": canonical,
        "composition_shell": composition,
        "production_template_entry_count": 1 if not duplicate_candidates else 1 + len(duplicate_candidates),
        "duplicated_template": bool(duplicate_candidates),
        "books_route_chain": next(
            (a.get("chain") for a in adapters if a.get("id") == "books-embedded"),
            [],
        ),
        "standalone_route_chain": next(
            (a.get("chain") for a in adapters if a.get("id") == "standalone-results"),
            [],
        ),
        "book_special_cases": [h for h in special_hits if "book" in h["kind"]],
        "chapter_special_cases": [h for h in special_hits if "chapter" in h["kind"]],
        "run_special_cases": [h for h in special_hits if "run" in h["kind"] or "55" in h["kind"]],
        "hardcoded_scene_count": [h for h in special_hits if "scene" in h["kind"]],
        "hardcoded_phase_count": [h for h in special_hits if "phase" in h["kind"]],
        "version_authority": "audits/mvp-functional-baseline-v1/reader-journey-ui-final-v2.7/reader-journey-ui-final-freeze-v2.7.json#version",
        "version_string_locations": version_locations,
        "checks": checks,
        "structural_issues": structural_issues,
        "warnings": warnings,
        "data_independence": template.get("data_independence"),
        "pipeline_reliability_certification_allowed": result == "PASS"
        and not structural_issues
        and not duplicate_candidates
        and books_ok
        and standalone_ok,
        "result": result,
    }

    if write_report:
        DEFAULT_REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Single-chapter Reader Journey template governance check"
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--write-report",
        action="store_true",
        default=True,
        help="Write conformance report JSON (default on; read-only w.r.t. production/freeze)",
    )
    parser.add_argument(
        "--no-write-report",
        action="store_true",
        help="Skip writing the conformance report file",
    )
    args = parser.parse_args()

    template_path = args.template if args.template.is_absolute() else ROOT / args.template
    if not template_path.exists():
        print(f"FAIL: template description missing: {template_path}")
        return 1

    template = json.loads(read_text(template_path))
    report = build_report(template, write_report=not args.no_write_report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("StoryLens Single-Chapter Journey Template Check")
        print(f"template: {template_path.relative_to(ROOT).as_posix()}")
        print(f"canonical_entry: {report['canonical_entry']}")
        print(f"production_template_entry_count: {report['production_template_entry_count']}")
        print(f"duplicated_template: {report['duplicated_template']}")
        print(f"books_points_to_canonical: {report['checks']['books_points_to_canonical']}")
        print(
            f"standalone_points_to_canonical: {report['checks']['standalone_points_to_canonical']}"
        )
        print(
            f"production_special_case_count: {report['checks']['production_special_case_count']}"
        )
        print(f"version_drift_risk_count: {report['checks']['version_drift_risk_count']}")
        if report["structural_issues"]:
            print("\nStructural issues:")
            for item in report["structural_issues"]:
                print(f"  - {item}")
        if report["warnings"]:
            print("\nWarnings:")
            for item in report["warnings"]:
                print(f"  - {item}")
        if report["checks"]["production_special_cases"]:
            print("\nProduction special-case hits (report-only):")
            for hit in report["checks"]["production_special_cases"]:
                print(f"  - {hit['path']}:{hit['line']} [{hit['kind']}] {hit['snippet']}")
        print()
        print("RESULT:", report["result"])

    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
