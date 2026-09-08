#!/usr/bin/env python3
"""Verify every Mach-O in the macOS PyInstaller onedir sidecar runtime."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodeSignature:
    team_identifier: str | None
    adhoc: bool
    hardened_runtime: bool


def parse_codesign_details(raw: str) -> CodeSignature:
    team_identifier: str | None = None
    saw_team_identifier = False
    adhoc = False
    hardened_runtime = False
    for original in raw.splitlines():
        line = original.strip()
        if line.startswith("TeamIdentifier="):
            saw_team_identifier = True
            value = line.partition("=")[2].strip()
            team_identifier = None if value in {"", "not set"} else value
        if line == "Signature=adhoc" or "(adhoc)" in line:
            adhoc = True
        if line.startswith("CodeDirectory ") and "(runtime)" in line:
            hardened_runtime = True
    if not saw_team_identifier:
        raise ValueError("codesign output did not contain TeamIdentifier")
    return CodeSignature(
        team_identifier=team_identifier,
        adhoc=adhoc,
        hardened_runtime=hardened_runtime,
    )


def validate_signature_pair(
    outer: CodeSignature,
    python_runtime: CodeSignature,
    *,
    signing_mode: str,
) -> None:
    if signing_mode == "adhoc":
        if outer.team_identifier is not None or python_runtime.team_identifier is not None:
            raise ValueError(
                "ad-hoc sidecar must not retain a Team ID in either the outer "
                "executable or Python runtime"
            )
        if not outer.adhoc or not python_runtime.adhoc:
            raise ValueError("ad-hoc sidecar and Python runtime must both be ad-hoc signed")
        return
    if signing_mode != "developer-id":
        raise ValueError(f"unsupported signing mode: {signing_mode}")
    if not outer.team_identifier or not python_runtime.team_identifier:
        raise ValueError("Developer ID build is missing a Team ID")
    if outer.team_identifier != python_runtime.team_identifier:
        raise ValueError(
            "sidecar and Python runtime have different Team IDs: "
            f"{outer.team_identifier!r} != {python_runtime.team_identifier!r}"
        )


def validate_runtime_signatures(
    signatures: dict[Path, CodeSignature],
    *,
    executable: Path,
    python_runtime: Path,
    signing_mode: str,
) -> None:
    if executable not in signatures:
        raise ValueError("sidecar executable is missing from the Mach-O signature set")
    if python_runtime not in signatures:
        raise ValueError("Python runtime is missing from the Mach-O signature set")
    outer = signatures[executable]
    if signing_mode == "adhoc" and outer.hardened_runtime:
        raise ValueError("ad-hoc candidate sidecar must not enable hardened runtime")
    if signing_mode == "developer-id" and not outer.hardened_runtime:
        raise ValueError("Developer ID sidecar must enable hardened runtime")
    validate_signature_pair(outer, signatures[python_runtime], signing_mode=signing_mode)
    for signature in signatures.values():
        validate_signature_pair(outer, signature, signing_mode=signing_mode)


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


def _is_macho(path: Path) -> bool:
    result = subprocess.run(
        ["file", "-b", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "Mach-O" in result.stdout


def _runtime_macho_paths(runtime: Path) -> list[Path]:
    paths = [
        path
        for path in sorted(runtime.rglob("*"))
        if path.is_file() and not path.is_symlink() and _is_macho(path)
    ]
    if not paths:
        raise RuntimeError("sidecar runtime contains no Mach-O files")
    return paths


def _find_python_runtime(paths: list[Path]) -> Path:
    framework = [
        path
        for path in paths
        if path.name == "Python" and any(part == "Python.framework" for part in path.parts)
    ]
    if len(framework) == 1:
        return framework[0]
    plain = [path for path in paths if path.name == "Python"]
    if len(plain) == 1:
        return plain[0]
    raise RuntimeError(
        f"expected one Python runtime Mach-O, found framework={len(framework)} plain={len(plain)}"
    )


def check_sidecar(runtime: Path, *, signing_mode: str) -> None:
    if sys.platform != "darwin":
        raise RuntimeError("macOS sidecar signature check must run on macOS")
    runtime = runtime.resolve(strict=True)
    if not runtime.is_dir():
        raise RuntimeError("macOS sidecar must use an onedir runtime")
    executable = runtime / "storylens-api"
    if not executable.is_file():
        raise RuntimeError("macOS sidecar runtime is missing its executable")
    paths = _runtime_macho_paths(runtime)
    python_runtime = _find_python_runtime(paths)
    signatures = {path: _codesign_details(path) for path in paths}
    validate_runtime_signatures(
        signatures,
        executable=executable,
        python_runtime=python_runtime,
        signing_mode=signing_mode,
    )
    outer_team = signatures[executable].team_identifier or "adhoc"
    python_team = signatures[python_runtime].team_identifier or "adhoc"
    print(
        "macOS sidecar onedir signature check passed: "
        f"mach_o_count={len(paths)} outer_team={outer_team} python_team={python_team}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--signing-mode", choices=("adhoc", "developer-id"), required=True)
    args = parser.parse_args()
    try:
        check_sidecar(args.runtime, signing_mode=args.signing_mode)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"macOS sidecar signature check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
