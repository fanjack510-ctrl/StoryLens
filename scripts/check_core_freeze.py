# -*- coding: utf-8 -*-
"""Core Freeze gate: compare FROZEN_* / REUSABLE_UI_LOGIC file SHA-256 to baseline.

Does not modify production code, does not update the manifest, does not restore files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "audits" / "mvp-functional-baseline-v1" / "core-freeze-manifest.json"
DEFAULT_THAW_V1 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v1.json"
DEFAULT_THAW_V2 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2.json"
DEFAULT_THAW_V2_2 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-2.json"
DEFAULT_THAW_V2_3 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-3.json"
DEFAULT_THAW_V2_4 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-4.json"
DEFAULT_THAW_V2_4_1 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-4-1.json"
DEFAULT_THAW_V2_4_2 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-4-2.json"
DEFAULT_THAW_V2_5 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-5.json"
DEFAULT_THAW_V2_6 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-6.json"
DEFAULT_THAW_V2_7 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-7.json"
DEFAULT_THAW_V2_8 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-8.json"
DEFAULT_THAW_V2_9 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-9.json"
DEFAULT_THAW_V2_10 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-10.json"
DEFAULT_THAW_V2_11 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-11.json"
DEFAULT_THAW_V2_12 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-12.json"
DEFAULT_THAW_V2_13 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-13.json"
DEFAULT_THAW_V2_14 = ROOT / "audits" / "mvp-functional-baseline-v1" / "ui-presentation-thaw-v2-14.json"
CHECKED_CATEGORIES = ("FROZEN_CORE", "FROZEN_CONTRACT", "REUSABLE_UI_LOGIC")
DEFAULT_THAWS = (
    DEFAULT_THAW_V1,
    DEFAULT_THAW_V2,
    DEFAULT_THAW_V2_2,
    DEFAULT_THAW_V2_3,
    DEFAULT_THAW_V2_4,
    DEFAULT_THAW_V2_4_1,
    DEFAULT_THAW_V2_4_2,
    DEFAULT_THAW_V2_5,
    DEFAULT_THAW_V2_6,
    DEFAULT_THAW_V2_7,
    DEFAULT_THAW_V2_8,
    DEFAULT_THAW_V2_9,
    DEFAULT_THAW_V2_10,
    DEFAULT_THAW_V2_11,
    DEFAULT_THAW_V2_12,
    DEFAULT_THAW_V2_13,
    DEFAULT_THAW_V2_14,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def likely_newline_only(path: Path, expected: str) -> bool:
    raw = path.read_bytes()
    return sha256_bytes(raw.replace(b"\r\n", b"\n")) == expected


def main() -> int:
    parser = argparse.ArgumentParser(description="StoryLens Core Freeze check")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to core-freeze-manifest.json",
    )
    parser.add_argument(
        "--ui-thaw",
        type=Path,
        action="append",
        default=None,
        help="Optional UI presentation thaw whitelist (repeatable; default v1+v2+v2-2)",
    )
    parser.add_argument(
        "--ignore-ui-thaw",
        action="store_true",
        help="Ignore ui-presentation-thaw whitelist even if present",
    )
    args = parser.parse_args()
    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    if not manifest_path.exists():
        print(f"FAIL: manifest missing: {manifest_path}")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files") or []

    thaw_allowed: set[str] = set()
    thaw_paths: list[Path] = []
    if not args.ignore_ui_thaw:
        if args.ui_thaw:
            thaw_paths = [p if p.is_absolute() else ROOT / p for p in args.ui_thaw]
        else:
            thaw_paths = list(DEFAULT_THAWS)
        for thaw_path in thaw_paths:
            if not thaw_path.exists():
                continue
            thaw = json.loads(thaw_path.read_text(encoding="utf-8"))
            for entry in thaw.get("allowed_files") or []:
                rel = entry["path"]
                # UI thaw must never claim FROZEN_CORE / FROZEN_CONTRACT paths.
                for core_entry in files:
                    if core_entry.get("path") == rel and core_entry.get("category") in (
                        "FROZEN_CORE",
                        "FROZEN_CONTRACT",
                    ):
                        print(
                            f"FAIL: thaw {thaw_path.name} lists frozen category "
                            f"{core_entry.get('category')}: {rel}"
                        )
                        return 1
                thaw_allowed.add(rel)

    unchanged: list[str] = []
    modified: list[dict[str, str]] = []
    thawed_modified: list[dict[str, str]] = []
    missing: list[str] = []
    unexpected: list[str] = []
    newline_hints: list[str] = []

    by_category = {category: [] for category in CHECKED_CATEGORIES}
    for entry in files:
        category = entry.get("category")
        if category not in by_category:
            continue
        rel = entry["path"]
        expected = entry["sha256"]
        path = ROOT / Path(*rel.split("/"))
        if not path.exists():
            missing.append(rel)
            by_category[category].append(("missing", rel))
            continue
        actual = sha256_file(path)
        if actual == expected:
            unchanged.append(rel)
            by_category[category].append(("unchanged", rel))
        elif category == "REUSABLE_UI_LOGIC" and rel in thaw_allowed:
            thawed_modified.append(
                {
                    "path": rel,
                    "category": category,
                    "expected": expected,
                    "actual": actual,
                }
            )
            by_category[category].append(("thawed", rel))
        else:
            item = {
                "path": rel,
                "category": category,
                "expected": expected,
                "actual": actual,
            }
            modified.append(item)
            by_category[category].append(("modified", rel))
            if likely_newline_only(path, expected):
                newline_hints.append(rel)

    print("StoryLens Core Freeze Check")
    print(f"manifest: {manifest_path.relative_to(ROOT).as_posix()}")
    print(f"baseline: {manifest.get('baseline_name')}")
    if thaw_allowed:
        thaw_labels = ", ".join(
            p.relative_to(ROOT).as_posix() for p in thaw_paths if p.exists()
        )
        print(f"ui_thaw: {thaw_labels} allowed={len(thaw_allowed)}")
    print()
    for category in CHECKED_CATEGORIES:
        rows = by_category[category]
        mod_n = sum(1 for status, _ in rows if status == "modified")
        thaw_n = sum(1 for status, _ in rows if status == "thawed")
        miss_n = sum(1 for status, _ in rows if status == "missing")
        ok_n = sum(1 for status, _ in rows if status == "unchanged")
        print(
            f"{category}: unchanged={ok_n} modified={mod_n} "
            f"thawed={thaw_n} missing={miss_n}"
        )

    print()
    print(f"unchanged={len(unchanged)}")
    print(f"modified={len(modified)}")
    print(f"thawed_modified={len(thawed_modified)}")
    print(f"missing={len(missing)}")
    print(f"unexpected={len(unexpected)}")

    if modified:
        print("\nModified files:")
        for item in modified:
            print(f"  - [{item['category']}] {item['path']}")
            print(f"      expected={item['expected']}")
            print(f"      actual  ={item['actual']}")
            print("      diagnosis=raw mismatch")
            if item["path"] in newline_hints:
                print("      normalized-LF match=yes (likely newline-only drift)")
            else:
                print("      normalized-LF match=no")
    if thawed_modified:
        print("\nThaw-allowed presentation modifications:")
        for item in thawed_modified:
            print(f"  - [{item['category']}] {item['path']}")
    if missing:
        print("\nMissing files:")
        for rel in missing:
            print(f"  - {rel}")
    if unexpected:
        print("\nUnexpected:")
        for rel in unexpected:
            print(f"  - {rel}")

    # Final gate remains raw SHA: newline-only hints never silence FAIL.
    failed = bool(modified or missing)
    print()
    print("RESULT:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
