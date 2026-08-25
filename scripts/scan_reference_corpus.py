"""Scan a local TXT reference corpus without calling a model."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.narrative_core.material_lab.reference_corpus import scan_reference_corpus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_dir():
        parser.error(f"source is not a directory: {source}")
    result = scan_reference_corpus(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "total_txt": result.total_txt,
        "accepted": result.accepted,
        "unsupported_or_uncertain": result.unsupported_or_uncertain,
        "rejected": result.rejected,
        "by_genre": result.by_genre,
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
