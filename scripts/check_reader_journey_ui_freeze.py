# -*- coding: utf-8 -*-
"""Reader Journey UI Final Freeze gate (v2.7).

Recomputes raw SHA-256 for each frozen file. No LF normalization tolerance.
Does not modify files, database, or manifests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT
    / "audits"
    / "mvp-functional-baseline-v1"
    / "reader-journey-ui-final-v4.2"
    / "reader-journey-ui-final-freeze-v4.2.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reader Journey UI Final Freeze check")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--explain",
        type=str,
        default=None,
        help="Explain status for a relative path",
    )
    args = parser.parse_args()

    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    if not manifest_path.exists():
        print(f"FAIL: manifest missing: {manifest_path}")
        return 1

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = data.get("files") or []

    modified: list[dict] = []
    missing: list[dict] = []
    ok: list[dict] = []
    by_category: dict[str, dict[str, int]] = {}

    for entry in files:
        rel = entry["path"]
        expected = entry["sha256"]
        category = entry.get("category") or "UNKNOWN"
        path = ROOT / Path(*rel.split("/"))
        bucket = by_category.setdefault(category, {"ok": 0, "modified": 0, "missing": 0})
        if not path.exists():
            missing.append({"path": rel, "category": category, "expected": expected})
            bucket["missing"] += 1
            continue
        actual = sha256_file(path)
        if actual != expected:
            modified.append(
                {
                    "path": rel,
                    "category": category,
                    "expected": expected,
                    "actual": actual,
                }
            )
            bucket["modified"] += 1
        else:
            ok.append({"path": rel, "category": category, "sha256": actual})
            bucket["ok"] += 1

    if args.explain:
        target = args.explain.replace("\\", "/")
        match = next((e for e in files if e["path"] == target), None)
        if not match:
            print(f"not_in_manifest: {target}")
            return 1
        path = ROOT / Path(*target.split("/"))
        if not path.exists():
            print(f"missing: {target}")
            print(f"category: {match.get('category')}")
            print(f"expected: {match['sha256']}")
            return 1
        actual = sha256_file(path)
        status = "unchanged" if actual == match["sha256"] else "modified"
        print(f"path: {target}")
        print(f"category: {match.get('category')}")
        print(f"status: {status}")
        print(f"expected: {match['sha256']}")
        print(f"actual: {actual}")
        print(f"responsibility: {match.get('responsibility')}")
        return 0 if status == "unchanged" else 1

    payload = {
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "baseline": data.get("baseline_name"),
        "file_count": len(files),
        "ok": len(ok),
        "modified": len(modified),
        "missing": len(missing),
        "by_category": by_category,
        "modified_files": modified,
        "missing_files": missing,
        "result": "FAIL" if (modified or missing) else "PASS",
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("StoryLens Reader Journey UI Final Freeze Check")
        print(f"manifest: {payload['manifest']}")
        print(f"baseline: {payload['baseline']}")
        print(f"file_count={payload['file_count']}")
        print()
        for cat, counts in sorted(by_category.items()):
            print(
                f"{cat}: ok={counts['ok']} modified={counts['modified']} missing={counts['missing']}"
            )
        print()
        print(f"ok={payload['ok']}")
        print(f"modified={payload['modified']}")
        print(f"missing={payload['missing']}")
        if modified:
            print("\nModified files:")
            for item in modified:
                print(f"  - {item['path']}")
                print(f"      expected={item['expected']}")
                print(f"      actual  ={item['actual']}")
        if missing:
            print("\nMissing files:")
            for item in missing:
                print(f"  - {item['path']}")
        print()
        print("RESULT:", payload["result"])

    return 1 if (modified or missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
