from __future__ import annotations

import pytest

from scripts.check_macos_sidecar_signature import (
    CodeSignature,
    _extract_embedded_python,
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


def test_extract_embedded_python_ignores_framework_symlink_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    payload = b"mach-o-python"

    class FakeArchive:
        toc = {
            "Python.framework/Versions/3.12/Python": (0, 1, 1, 0, "b"),
            "Python": (0, 1, 1, 0, "n"),
            "Python.framework/Python": (0, 1, 1, 0, "n"),
        }

        def __init__(self, _path: str) -> None:
            pass

        def extract(self, name: str) -> bytes:
            assert name == "Python.framework/Versions/3.12/Python"
            return payload

    import PyInstaller.archive.readers

    monkeypatch.setattr(PyInstaller.archive.readers, "CArchiveReader", FakeArchive)
    destination = tmp_path / "Python"
    _extract_embedded_python(tmp_path / "storylens-api", destination)
    assert destination.read_bytes() == payload
