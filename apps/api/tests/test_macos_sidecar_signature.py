from __future__ import annotations

import pytest

from scripts.check_macos_sidecar_signature import (
    CodeSignature,
    parse_codesign_details,
    validate_signature_pair,
)


def test_parse_adhoc_codesign_details() -> None:
    details = parse_codesign_details(
        "CodeDirectory v=20500 size=1 flags=0x2(adhoc) hashes=1\n"
        "Signature=adhoc\n"
        "TeamIdentifier=not set\n"
    )
    assert details == CodeSignature(team_identifier=None, adhoc=True)


def test_adhoc_pair_rejects_embedded_python_team_id() -> None:
    with pytest.raises(ValueError, match="must not retain a Team ID"):
        validate_signature_pair(
            CodeSignature(team_identifier=None, adhoc=True),
            CodeSignature(team_identifier="PYTHONTEAM", adhoc=False),
            signing_mode="adhoc",
        )


def test_developer_id_pair_requires_same_team() -> None:
    validate_signature_pair(
        CodeSignature(team_identifier="STORYTEAM", adhoc=False),
        CodeSignature(team_identifier="STORYTEAM", adhoc=False),
        signing_mode="developer-id",
    )
    with pytest.raises(ValueError, match="different Team IDs"):
        validate_signature_pair(
            CodeSignature(team_identifier="STORYTEAM", adhoc=False),
            CodeSignature(team_identifier="PYTHONTEAM", adhoc=False),
            signing_mode="developer-id",
        )
