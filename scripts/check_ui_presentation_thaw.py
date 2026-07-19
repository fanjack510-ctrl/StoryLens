# -*- coding: utf-8 -*-
"""UI presentation thaw gate for Reader Journey view-only refinement.

- FROZEN_CORE / FROZEN_CONTRACT must remain unmodified vs core-freeze-manifest.
- REUSABLE_UI_LOGIC may change only if listed in ui-presentation-thaw-v1…v2-7.
- Does not update any manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORE = ROOT / "audits" / "mvp-functional-baseline-v1" / "core-freeze-manifest.json"
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
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel_path(path: str) -> Path:
    return ROOT / Path(*path.split("/"))


def load_thaw_entries(paths: list[Path]) -> tuple[list[dict], list[str]]:
    entries: list[dict] = []
    labels: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        labels.append(path.relative_to(ROOT).as_posix())
        for entry in data.get("allowed_files") or []:
            entries.append(entry)
    return entries, labels


def thaw_file_limit(thaw_id: str, path: Path) -> int:
    name = path.name
    tid = str(thaw_id)
    if "v2-6" in tid or name.endswith("v2-6.json"):
        return 2
    if "v2-5" in tid or name.endswith("v2-5.json"):
        return 10
    if "v2-4-2" in tid or name.endswith("v2-4-2.json"):
        return 5
    if "v2-4-1" in tid or name.endswith("v2-4-1.json"):
        return 7
    if "v2-4" in tid or name.endswith("v2-4.json"):
        return 8
    if "v2-3" in tid or name.endswith("v2-3.json"):
        return 6
    if "v2-2" in tid or name.endswith("v2-2.json"):
        return 4
    if "v2" in tid or name.endswith("v2.json"):
        return 12
    return 10


def lf_matches_expected(path: Path, expected: str) -> bool:
    raw = path.read_bytes()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == expected


def main() -> int:
    parser = argparse.ArgumentParser(description="StoryLens UI presentation thaw check")
    parser.add_argument("--core-manifest", type=Path, default=DEFAULT_CORE)
    parser.add_argument(
        "--thaw-manifest",
        type=Path,
        action="append",
        default=None,
        help="Thaw whitelist JSON (repeatable). Defaults to v1+v2+v2-2 when present.",
    )
    args = parser.parse_args()

    core_path = args.core_manifest if args.core_manifest.is_absolute() else ROOT / args.core_manifest
    if not core_path.exists():
        print(f"FAIL: core manifest missing: {core_path}")
        return 1

    if args.thaw_manifest:
        thaw_paths = [p if p.is_absolute() else ROOT / p for p in args.thaw_manifest]
    else:
        thaw_paths = list(DEFAULT_THAWS)

    existing_thaws = [p for p in thaw_paths if p.exists()]
    if not existing_thaws:
        print(
            "FAIL: no thaw manifest found (expected v1 and/or v2 and/or v2-2 "
            "and/or v2-3 and/or v2-4 and/or v2-4-1 and/or v2-4-2 and/or v2-5 and/or v2-6)"
        )
        return 1

    core = json.loads(core_path.read_text(encoding="utf-8"))
    frozen_blocked = {
        entry["path"]
        for entry in (core.get("files") or [])
        if entry.get("category") in ("FROZEN_CORE", "FROZEN_CONTRACT")
    }

    for path in existing_thaws:
        data = json.loads(path.read_text(encoding="utf-8"))
        count = len(data.get("allowed_files") or [])
        thaw_id = data.get("thaw_id") or path.name
        limit = thaw_file_limit(thaw_id, path)
        if count > limit:
            print(f"FAIL: {path.name} allowed_files exceeds {limit} ({count})")
            return 1
        for entry in data.get("allowed_files") or []:
            rel = entry["path"]
            if rel in frozen_blocked:
                print(f"FAIL: thaw {path.name} must not list FROZEN_CORE/CONTRACT path: {rel}")
                return 1

    allowed_entries, thaw_labels = load_thaw_entries(existing_thaws)
    # Later thaw wins on duplicate path (v2-2 overrides v2 overrides v1).
    allowed_by_path: dict[str, dict] = {}
    for entry in allowed_entries:
        allowed_by_path[entry["path"]] = entry
    allowed_paths = set(allowed_by_path)

    frozen_core_mod = 0
    frozen_contract_mod = 0
    reusable_non_whitelist_mod = 0
    reusable_whitelist_mod = 0
    unexpected_new: list[str] = []
    missing_required: list[str] = []
    thaw_status: list[str] = []

    for entry in core.get("files") or []:
        category = entry.get("category")
        rel = entry["path"]
        path = rel_path(rel)
        expected = entry["sha256"]
        if not path.exists():
            if category in ("FROZEN_CORE", "FROZEN_CONTRACT"):
                missing_required.append(rel)
            continue
        actual = sha256_file(path)
        modified = actual != expected
        if category == "FROZEN_CORE" and modified:
            frozen_core_mod += 1
            print(f"  FROZEN_CORE modified: {rel}")
            print(
                "    normalized-LF match=yes (likely newline-only drift)"
                if lf_matches_expected(path, expected)
                else "    normalized-LF match=no"
            )
        elif category == "FROZEN_CONTRACT" and modified:
            frozen_contract_mod += 1
            print(f"  FROZEN_CONTRACT modified: {rel}")
            print(
                "    normalized-LF match=yes (likely newline-only drift)"
                if lf_matches_expected(path, expected)
                else "    normalized-LF match=no"
            )
        elif category == "REUSABLE_UI_LOGIC" and modified:
            if rel in allowed_paths:
                reusable_whitelist_mod += 1
            else:
                reusable_non_whitelist_mod += 1
                print(f"  non-whitelist REUSABLE_UI_LOGIC modified: {rel}")
                print(
                    "    normalized-LF match=yes (likely newline-only drift)"
                    if lf_matches_expected(path, expected)
                    else "    normalized-LF match=no"
                )

    for rel, entry in allowed_by_path.items():
        path = rel_path(rel)
        before = entry.get("before_sha256")
        is_new = bool(entry.get("new_file")) or before is None
        if not path.exists():
            if is_new:
                thaw_status.append(f"pending_new {rel}")
            else:
                missing_required.append(rel)
            continue
        actual = sha256_file(path)
        if is_new:
            thaw_status.append(f"new_present {rel}")
        elif actual == before:
            thaw_status.append(f"unchanged {rel}")
        else:
            thaw_status.append(f"allowed_modified {rel}")

    rj_dir = ROOT / "apps" / "desktop" / "src" / "components" / "readerJourney"
    core_paths = {f.get("path") for f in (core.get("files") or [])}
    shell_paths = set(core.get("ui_shell_changeable") or [])
    ignore_names = {"mockVisualization.ts"}
    if rj_dir.exists():
        for path in rj_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".tsx", ".ts", ".css"}:
                continue
            if path.name.endswith(".test.tsx") or path.name.endswith(".test.ts"):
                continue
            if path.name in ignore_names or path.name.startswith("mock"):
                continue
            if (
                path.name.startswith("phase_1cc24")
                or path.name.startswith("phase_1cc25")
                or path.name.startswith("phase_1cc26")
                or path.name.startswith("phase_1cc27")
            ):
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in allowed_paths or rel in core_paths or rel in shell_paths:
                continue
            unexpected_new.append(rel)

    print("StoryLens UI Presentation Thaw Check")
    print(f"core_manifest: {core_path.relative_to(ROOT).as_posix()}")
    print(f"thaw_manifests: {', '.join(thaw_labels)}")
    print(f"union_allowed_files={len(allowed_paths)}")
    print()
    print(f"FROZEN_CORE modified={frozen_core_mod}")
    print(f"FROZEN_CONTRACT modified={frozen_contract_mod}")
    print(f"non-whitelist REUSABLE_UI_LOGIC modified={reusable_non_whitelist_mod}")
    print(f"whitelist REUSABLE_UI_LOGIC modified={reusable_whitelist_mod}")
    print()
    print("thaw file status:")
    for line in thaw_status:
        print(f"  - {line}")
    if unexpected_new:
        print("\nUnexpected new presentation files (not in whitelist):")
        for rel in unexpected_new:
            print(f"  - {rel}")
    if missing_required:
        print("\nMissing required files:")
        for rel in missing_required:
            print(f"  - {rel}")

    failed = bool(
        frozen_core_mod
        or frozen_contract_mod
        or reusable_non_whitelist_mod
        or unexpected_new
        or missing_required
    )
    print()
    print("RESULT:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
