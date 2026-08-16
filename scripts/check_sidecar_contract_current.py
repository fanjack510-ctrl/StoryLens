"""Fail if the packaged sidecar was built before the current result contract.

The failure this guards against has happened twice and cost a paid run each time: a field is
added to ``WholeBookAnalysisV2``, the source-run development API accepts it, and the packaged
sidecar — built earlier and validating with ``extra='forbid'`` — answers 500 on every request
carrying that field. Nothing in the build says so; the binary simply predates the schema.

The check compares the source contract against a manifest the build writes beside the
executable. Asking the executable itself was tried first and abandoned: an older binary does
not recognise a diagnostic flag, starts serving instead, and holds the stdout pipe open
through a grandchild process, so the probe hangs rather than answering. A manifest written by
the build is both simpler and honest about what it proves — it describes the source tree the
binary was compiled from, which is exactly the thing that goes stale.

Exit codes: 0 current, 1 stale (rebuild required), 2 no sidecar present — not an error, since
development runs from source.

    python scripts/check_sidecar_contract_current.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "apps" / "api" / "dist-sidecar"
BINARIES = (
    DIST / "storylens-api.exe",
    DIST / "storylens-api" / "storylens-api.exe",
    ROOT / "apps" / "desktop" / "src-tauri" / "binaries" / "storylens-api.exe",
)
MANIFEST_NAME = "contract-fields.json"


def source_fields() -> list[str]:
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    from app.narrative_core.whole_book_v2.contracts import WholeBookAnalysisV2

    return sorted(WholeBookAnalysisV2.model_fields)


def write_manifest(path: Path) -> list[str]:
    """Record the contract as it stands. Called by ``build_sidecar.ps1`` after a build."""
    fields = source_fields()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"whole_book_analysis_v2": fields}, indent=2), encoding="utf-8")
    return fields


def main(argv: list[str]) -> int:
    manifest = DIST / MANIFEST_NAME
    if "--write" in argv:
        fields = write_manifest(manifest)
        print(f"wrote {manifest.relative_to(ROOT)} with {len(fields)} contract fields")
        return 0

    binary = next((path for path in BINARIES if path.is_file()), None)
    if binary is None:
        print("no packaged sidecar found — nothing to check (development runs from source)")
        return 2

    if not manifest.is_file():
        # A binary with no manifest predates this check, so its age cannot be established.
        # Reported as stale rather than passed: a check that cannot see what it checks must
        # not return success.
        print(f"FAIL  {binary.name} has no {MANIFEST_NAME} beside it — age unknown, treat as stale",
              file=sys.stderr)
        print("      rebuild with  .\\scripts\\build_sidecar.ps1", file=sys.stderr)
        return 1

    built = json.loads(manifest.read_text(encoding="utf-8")).get("whole_book_analysis_v2") or []
    expected = source_fields()
    missing = [field for field in expected if field not in built]
    if missing:
        print(f"FAIL  packaged sidecar predates {len(missing)} contract field(s): "
              f"{', '.join(missing)}", file=sys.stderr)
        print("      it would answer 500 on any document carrying them (extra='forbid')",
              file=sys.stderr)
        print("      rebuild with  .\\scripts\\build_sidecar.ps1", file=sys.stderr)
        return 1
    print(f"OK    packaged sidecar covers all {len(expected)} contract fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
