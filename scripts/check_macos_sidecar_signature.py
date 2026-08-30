#!/usr/bin/env python3
"""Verify the outer and embedded signatures of a macOS PyInstaller sidecar."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodeSignature:
    team_identifier: str | None
    adhoc: bool


def parse_codesign_details(raw: str) -> CodeSignature:
    team_identifier: str | None = None
    saw_team_identifier = False
    adhoc = False
    for original in raw.splitlines():
        line = original.strip()
        if line.startswith("TeamIdentifier="):
            saw_team_identifier = True
            value = line.partition("=")[2].strip()
            team_identifier = None if value in {"", "not set"} else value
        if line == "Signature=adhoc" or "(adhoc)" in line:
            adhoc = True
    if not saw_team_identifier:
        raise ValueError("codesign output did not contain TeamIdentifier")
    return CodeSignature(team_identifier=team_identifier, adhoc=adhoc)


def validate_signature_pair(
    outer: CodeSignature,
    embedded_python: CodeSignature,
    *,
    signing_mode: str,
) -> None:
    if signing_mode == "adhoc":
        if outer.team_identifier is not None or embedded_python.team_identifier is not None:
            raise ValueError(
                "ad-hoc sidecar must not retain a Team ID in either the outer "
                "executable or embedded Python"
            )
        if not outer.adhoc or not embedded_python.adhoc:
            raise ValueError("ad-hoc sidecar and embedded Python must both be ad-hoc signed")
        return
    if signing_mode != "developer-id":
        raise ValueError(f"unsupported signing mode: {signing_mode}")
    if not outer.team_identifier or not embedded_python.team_identifier:
        raise ValueError("Developer ID build is missing a Team ID")
    if outer.team_identifier != embedded_python.team_identifier:
        raise ValueError(
            "sidecar and embedded Python have different Team IDs: "
            f"{outer.team_identifier!r} != {embedded_python.team_identifier!r}"
        )


def _codesign_details(path: Path) -> CodeSignature:
    verify = subprocess.run(
        ["codesign", "--verify", "--strict", "--verbose=2", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if verify.returncode != 0:
        raise RuntimeError(
            f"invalid code signature for {path}: {(verify.stderr or verify.stdout).strip()}"
        )
    details = subprocess.run(
        ["codesign", "-dv", "--verbose=4", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if details.returncode != 0:
        raise RuntimeError(
            f"cannot inspect code signature for {path}: "
            f"{(details.stderr or details.stdout).strip()}"
        )
    return parse_codesign_details(f"{details.stdout}\n{details.stderr}")


def _extract_embedded_python(sidecar: Path, destination: Path) -> None:
    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(sidecar))
    candidates = [
        name
        for name, (*_, typecode) in archive.toc.items()
        if name == "Python" or name.endswith(("/Python", "\\Python"))
        if typecode != "n"
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "expected one embedded Python shared library, found "
            f"{len(candidates)}: {candidates}"
        )
    destination.write_bytes(archive.extract(candidates[0]))
    destination.chmod(0o755)


def check_sidecar(sidecar: Path, *, signing_mode: str) -> None:
    if sys.platform != "darwin":
        raise RuntimeError("macOS sidecar signature check must run on macOS")
    sidecar = sidecar.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="storylens-signature-check-") as tmp:
        embedded = Path(tmp) / "Python"
        _extract_embedded_python(sidecar, embedded)
        outer_signature = _codesign_details(sidecar)
        python_signature = _codesign_details(embedded)
    validate_signature_pair(
        outer_signature,
        python_signature,
        signing_mode=signing_mode,
    )
    outer_team = outer_signature.team_identifier or "adhoc"
    python_team = python_signature.team_identifier or "adhoc"
    print(
        "macOS sidecar signature check passed: "
        f"outer_team={outer_team} embedded_python_team={python_team}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sidecar", type=Path)
    parser.add_argument("--signing-mode", choices=("adhoc", "developer-id"), required=True)
    args = parser.parse_args()
    try:
        check_sidecar(args.sidecar, signing_mode=args.signing_mode)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"macOS sidecar signature check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
