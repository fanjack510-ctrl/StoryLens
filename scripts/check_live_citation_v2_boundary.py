#!/usr/bin/env python3
"""Static gate: V2 Live citation path must not import banned quote fallbacks (CHG-058).

AST / import-oriented checks (not only string scan). Legacy V1 modules may keep
quote_resolution symbols; V2 modules listed below must not.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

V2_MODULES = (
    "apps/api/app/narrative_core/services/citation_catalog_v2.py",
    "apps/api/app/narrative_core/services/citation_evidence_enrichment_v2.py",
)

# Symbols / modules forbidden on the V2 Live citation path.
BANNED_IMPORT_MODULES = frozenset(
    {
        "quote_resolution",
        "app.narrative_core.services.quote_resolution",
    }
)
BANNED_NAMES = frozenset(
    {
        "resolve_evidence_locator",
        "SnapshotQuoteIndex",
        "resolve_by_quote_key",
        "resolve_by_unique_quote",
        "fallback_quote_match",
        "fuzzy_quote_match",
        "paragraph_id_guess",
        "stable_id_guess",
        "EvidenceRefLite",  # V1 evidence binding — not for V2 enrich path modules
    }
)

# Allow EvidenceRefLite only outside citation_evidence_enrichment_v2 / catalog.
ALLOW_EVIDENCE_REF_LITE_IN = frozenset(
    {
        "apps/api/app/narrative_core/services/citation_catalog_v2.py",
    }
)


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _check_file(path: Path, rel: str) -> list[str]:
    violations: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{rel}: syntax error: {exc}"]

    banned_names = set(BANNED_NAMES)
    if rel in ALLOW_EVIDENCE_REF_LITE_IN:
        banned_names.discard("EvidenceRefLite")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name in BANNED_IMPORT_MODULES or name.endswith(".quote_resolution"):
                    violations.append(f"{rel}: banned import {name}")
                leaf = name.split(".")[-1]
                if leaf in banned_names:
                    violations.append(f"{rel}: banned import name {leaf}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod in BANNED_IMPORT_MODULES or mod.endswith(".quote_resolution"):
                violations.append(f"{rel}: banned import-from {mod}")
            for alias in node.names:
                if alias.name in banned_names:
                    violations.append(f"{rel}: banned symbol import {alias.name}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in banned_names:
                violations.append(f"{rel}: banned call {func.id}")
            if isinstance(func, ast.Attribute) and func.attr in banned_names:
                violations.append(f"{rel}: banned call {func.attr}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args()
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()

    violations: list[str] = []
    for rel in V2_MODULES:
        path = root / rel
        if not path.is_file():
            violations.append(f"{rel}: missing V2 module")
            continue
        violations.extend(_check_file(path, rel))

    # Also ensure private_whole_book_analysis_runtime V2 branch does not call
    # resolve_evidence_locator when evidence_contract_version is v2 — structural
    # heuristic: citation_evidence_enrichment_v2 must be imported.
    runtime = root / "apps/api/app/narrative_core/services/private_whole_book_analysis_runtime.py"
    if runtime.is_file():
        text = runtime.read_text(encoding="utf-8")
        if "citation_evidence_enrichment_v2" not in text:
            violations.append(
                "private_whole_book_analysis_runtime.py: missing V2 enrichment import"
            )
        if "evidence_contract_version" not in text and "_is_evidence_contract_v2" not in text:
            violations.append(
                "private_whole_book_analysis_runtime.py: missing V2 contract detection"
            )

    if violations:
        print("LIVE CITATION V2 BOUNDARY FAILED")
        for row in violations[:50]:
            print(row)
        if len(violations) > 50:
            print(f"... and {len(violations) - 50} more")
        return 1
    print("LIVE CITATION V2 BOUNDARY OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
