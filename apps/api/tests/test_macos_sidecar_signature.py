from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_macos_sidecar_signature import (
    CodeSignature,
    parse_codesign_details,
    validate_runtime_signatures,
    validate_signature_pair,
)


def test_parse_adhoc_codesign_details() -> None:
    details = parse_codesign_details(
        "CodeDirectory v=20500 size=1 flags=0x2(adhoc) hashes=1\n"
        "Signature=adhoc\n"
        "TeamIdentifier=not set\n"
    )
    assert details == CodeSignature(
        team_identifier=None,
        adhoc=True,
        hardened_runtime=False,
    )


def test_adhoc_pair_rejects_python_team_id() -> None:
    with pytest.raises(ValueError, match="must not retain a Team ID"):
        validate_signature_pair(
            CodeSignature(team_identifier=None, adhoc=True, hardened_runtime=False),
            CodeSignature(team_identifier="PYTHONTEAM", adhoc=False, hardened_runtime=False),
            signing_mode="adhoc",
        )


def test_developer_id_pair_requires_same_team() -> None:
    validate_signature_pair(
        CodeSignature(team_identifier="STORYTEAM", adhoc=False, hardened_runtime=True),
        CodeSignature(team_identifier="STORYTEAM", adhoc=False, hardened_runtime=False),
        signing_mode="developer-id",
    )
    with pytest.raises(ValueError, match="different Team IDs"):
        validate_signature_pair(
            CodeSignature(team_identifier="STORYTEAM", adhoc=False, hardened_runtime=True),
            CodeSignature(team_identifier="PYTHONTEAM", adhoc=False, hardened_runtime=False),
            signing_mode="developer-id",
        )


def test_runtime_signature_set_checks_every_macho() -> None:
    executable = Path("runtime/storylens-api")
    python = Path("runtime/_internal/Python.framework/Versions/3.12/Python")
    extension = Path("runtime/_internal/extension.so")
    signatures = {
        executable: CodeSignature(team_identifier=None, adhoc=True, hardened_runtime=False),
        python: CodeSignature(team_identifier=None, adhoc=True, hardened_runtime=False),
        extension: CodeSignature(
            team_identifier="FOREIGNTEAM", adhoc=False, hardened_runtime=False
        ),
    }
    with pytest.raises(ValueError, match="must not retain a Team ID"):
        validate_runtime_signatures(
            signatures,
            executable=executable,
            python_runtime=python,
            signing_mode="adhoc",
        )


def test_runtime_signature_set_requires_python_and_executable() -> None:
    executable = Path("runtime/storylens-api")
    python = Path("runtime/_internal/Python")
    with pytest.raises(ValueError, match="Python runtime is missing"):
        validate_runtime_signatures(
            {executable: CodeSignature(team_identifier=None, adhoc=True, hardened_runtime=False)},
            executable=executable,
            python_runtime=python,
            signing_mode="adhoc",
        )


def test_runtime_signature_set_rejects_hardened_adhoc_executable() -> None:
    executable = Path("runtime/storylens-api")
    python = Path("runtime/_internal/Python")
    signatures = {
        executable: CodeSignature(team_identifier=None, adhoc=True, hardened_runtime=True),
        python: CodeSignature(team_identifier=None, adhoc=True, hardened_runtime=False),
    }
    with pytest.raises(ValueError, match="must not enable hardened runtime"):
        validate_runtime_signatures(
            signatures,
            executable=executable,
            python_runtime=python,
            signing_mode="adhoc",
        )
