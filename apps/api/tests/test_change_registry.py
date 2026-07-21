"""Tests for scripts/change_registry.py — use isolated temp git fixtures only."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "change_registry.py"


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _seed_registry(root: Path, version: str = "1.0.2") -> str:
    """Create a tiny git repo with baseline + registry scaffolding. Returns baseline sha."""
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _write(root / "VERSION", f"{version}\n")
    _write(root / "apps" / "api" / "app" / "main.py", "print('ok')\n")
    _write(
        root / "release" / "registry_config.json",
        (ROOT / "release" / "registry_config.json").read_text(encoding="utf-8"),
    )
    _write(
        root / "release" / "registry.schema.json",
        (ROOT / "release" / "registry.schema.json").read_text(encoding="utf-8"),
    )
    (root / "release" / "changes").mkdir(parents=True, exist_ok=True)
    (root / "release" / "generated").mkdir(parents=True, exist_ok=True)
    _write(
        root / "scripts" / "version_manager.py",
        (
            "import sys\n"
            "from pathlib import Path\n"
            "root = Path(__file__).resolve().parents[1]\n"
            "cmd = sys.argv[1] if len(sys.argv) > 1 else ''\n"
            "if cmd == 'check':\n"
            "    raise SystemExit(0)\n"
            "if cmd == 'bump' and len(sys.argv) > 2 and sys.argv[2] == 'patch':\n"
            "    ver = (root / 'VERSION').read_text().strip()\n"
            "    major, minor, patch = ver.split('.')\n"
            "    (root / 'VERSION').write_text(f'{major}.{minor}.{int(patch)+1}\\n')\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(2)\n"
        ),
    )
    # Placeholder baseline/unreleased so first commit is complete; sha filled after commit.
    _write(
        root / "release" / "baseline.json",
        json.dumps(
            {
                "version": version,
                "git_tag": None,
                "git_commit": "PENDING",
                "status": "verified",
                "released_at": "2026-07-01T00:00:00Z",
                "channel": "stable",
                "installer_sha256": "abc",
                "updater_sha256": "def",
                "manifest_url": "https://example.invalid/latest.json",
                "notes": "fixture",
            },
            indent=2,
        )
        + "\n",
    )
    _write(
        root / "release" / "unreleased.json",
        json.dumps(
            {
                "base_version": version,
                "target_version": None,
                "status": "collecting",
                "created_at": "2026-07-21T00:00:00Z",
                "frozen_at": None,
                "changes": [],
            },
            indent=2,
        )
        + "\n",
    )
    _git(root, "add", "VERSION", "apps", "release", "scripts")
    _git(root, "commit", "-m", "baseline")
    baseline = _git(root, "rev-parse", "HEAD")
    baseline_json = json.loads((root / "release" / "baseline.json").read_text(encoding="utf-8"))
    baseline_json["git_commit"] = baseline
    _write(root / "release" / "baseline.json", json.dumps(baseline_json, indent=2) + "\n")
    # Amend-free: keep PENDING commit as baseline; update file in working tree only for tests
    # that read baseline.json. Commit the pointer as docs-only style registry update so the
    # unregistered scanner ignores it (release/baseline.json is whitelisted).
    _git(root, "add", "release/baseline.json")
    _git(root, "commit", "-m", "set baseline commit pointer")
    return baseline


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    _seed_registry(tmp_path)
    return tmp_path


def test_register_creates_unique_ids(fixture_repo: Path) -> None:
    r1 = _run(fixture_repo, "register", "--title", "A", "--type", "fix")
    r2 = _run(fixture_repo, "register", "--title", "B", "--type", "fix")
    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr
    id1 = r1.stdout.strip().splitlines()[0]
    id2 = r2.stdout.strip().splitlines()[0]
    assert id1 != id2
    assert (fixture_repo / "release" / "changes" / f"{id1}.json").is_file()
    pool = json.loads((fixture_repo / "release" / "unreleased.json").read_text(encoding="utf-8"))
    assert id1 in pool["changes"] and id2 in pool["changes"]


def test_attach_real_commit_and_reject_missing(fixture_repo: Path) -> None:
    reg = _run(fixture_repo, "register", "--title", "X", "--type", "fix")
    cid = reg.stdout.strip().splitlines()[0]
    _write(fixture_repo / "apps" / "api" / "app" / "main.py", "print('changed')\n")
    _git(fixture_repo, "add", "apps")
    _git(fixture_repo, "commit", "-m", "source change")
    sha = _git(fixture_repo, "rev-parse", "HEAD")
    ok = _run(fixture_repo, "attach-commit", cid, sha)
    assert ok.returncode == 0, ok.stderr
    bad = _run(fixture_repo, "attach-commit", cid, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    assert bad.returncode != 0


def test_status_gates(fixture_repo: Path) -> None:
    reg = _run(fixture_repo, "register", "--title", "Gate", "--type", "fix")
    cid = reg.stdout.strip().splitlines()[0]
    assert _run(fixture_repo, "mark", cid, "implemented").returncode != 0
    assert _run(fixture_repo, "mark", cid, "tested").returncode != 0
    assert _run(fixture_repo, "mark", cid, "verified").returncode != 0
    assert _run(fixture_repo, "mark", cid, "ready").returncode != 0

    _write(fixture_repo / "apps" / "api" / "app" / "main.py", "print('impl')\n")
    _git(fixture_repo, "add", "apps")
    _git(fixture_repo, "commit", "-m", "implement")
    sha = _git(fixture_repo, "rev-parse", "HEAD")
    assert _run(fixture_repo, "attach-commit", cid, sha).returncode == 0
    assert _run(fixture_repo, "mark", cid, "implemented").returncode == 0

    assert _run(fixture_repo, "mark", cid, "tested").returncode != 0
    assert _run(fixture_repo, "update", cid, "--test", "pytest apps/api/tests/t.py").returncode == 0
    assert _run(fixture_repo, "mark", cid, "tested").returncode == 0

    assert _run(fixture_repo, "mark", cid, "verified").returncode != 0
    assert _run(fixture_repo, "update", cid, "--evidence", "manual ok").returncode == 0
    assert _run(fixture_repo, "mark", cid, "verified").returncode == 0
    assert _run(fixture_repo, "mark", cid, "ready").returncode == 0


def test_unregistered_and_docs_only(fixture_repo: Path) -> None:
    _write(fixture_repo / "apps" / "api" / "app" / "main.py", "print('u')\n")
    _git(fixture_repo, "add", "apps")
    _git(fixture_repo, "commit", "-m", "unregistered source")
    _write(fixture_repo / "docs" / "note.md", "hello\n")
    _git(fixture_repo, "add", "docs")
    _git(fixture_repo, "commit", "-m", "[docs-only] notes")
    result = _run(fixture_repo, "unregistered")
    assert "UNREGISTERED" in result.stdout
    assert "unregistered source" in result.stdout
    assert "[docs-only] notes" in result.stdout
    ignored_idx = result.stdout.index("== IGNORED ==")
    unreg_idx = result.stdout.index("== UNREGISTERED ==")
    assert "unregistered source" in result.stdout[unreg_idx:ignored_idx]
    assert "[docs-only] notes" in result.stdout[ignored_idx:]
    assert result.returncode != 0


def test_version_mismatch_fails_check(fixture_repo: Path) -> None:
    _write(fixture_repo / "VERSION", "9.9.9\n")
    result = _run(fixture_repo, "check")
    assert result.returncode != 0
    assert "VERSION" in result.stdout or "VERSION" in result.stderr


def test_collecting_cannot_preset_target(fixture_repo: Path) -> None:
    pool = json.loads((fixture_repo / "release" / "unreleased.json").read_text(encoding="utf-8"))
    pool["target_version"] = "1.0.3"
    _write(fixture_repo / "release" / "unreleased.json", json.dumps(pool, indent=2) + "\n")
    result = _run(fixture_repo, "check")
    assert result.returncode != 0
    assert "target_version" in result.stdout


def test_freeze_requires_ready_and_no_unregistered(fixture_repo: Path) -> None:
    reg = _run(fixture_repo, "register", "--title", "Need ready", "--type", "fix")
    cid = reg.stdout.strip().splitlines()[0]
    _write(fixture_repo / "apps" / "api" / "app" / "main.py", "print('f')\n")
    _git(fixture_repo, "add", "apps")
    _git(fixture_repo, "commit", "-m", "feature")
    sha = _git(fixture_repo, "rev-parse", "HEAD")
    _run(fixture_repo, "attach-commit", cid, sha)
    freeze = _run(fixture_repo, "freeze")
    assert freeze.returncode != 0
    assert "not ready" in freeze.stdout.lower() or "not ready" in freeze.stderr.lower()

    # Separate unregistered commit blocks freeze even if change is ready later
    _write(fixture_repo / "apps" / "api" / "app" / "main.py", "print('extra')\n")
    _git(fixture_repo, "add", "apps")
    _git(fixture_repo, "commit", "-m", "extra unregistered")
    freeze2 = _run(fixture_repo, "freeze")
    assert freeze2.returncode != 0
    assert "unregistered" in (freeze2.stdout + freeze2.stderr).lower()


def test_release_preview_does_not_modify(fixture_repo: Path) -> None:
    before = (fixture_repo / "VERSION").read_text(encoding="utf-8")
    before_pool = (fixture_repo / "release" / "unreleased.json").read_text(encoding="utf-8")
    result = _run(fixture_repo, "release-preview")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["next_patch"] == "1.0.3"
    assert (fixture_repo / "VERSION").read_text(encoding="utf-8") == before
    assert (fixture_repo / "release" / "unreleased.json").read_text(encoding="utf-8") == before_pool


def test_prepare_without_frozen_does_not_bump(fixture_repo: Path) -> None:
    before = (fixture_repo / "VERSION").read_text(encoding="utf-8")
    result = _run(fixture_repo, "prepare-next-release", "--bump", "patch")
    assert result.returncode != 0
    assert (fixture_repo / "VERSION").read_text(encoding="utf-8") == before
    assert before.strip() == "1.0.2"


def test_prepare_preview_when_frozen_no_confirm(fixture_repo: Path) -> None:
    reg = _run(
        fixture_repo,
        "register",
        "--title",
        "Ready item",
        "--type",
        "fix",
        "--user-summary",
        "fix it",
    )
    cid = reg.stdout.strip().splitlines()[0]
    _write(fixture_repo / "apps" / "api" / "app" / "main.py", "print('ready')\n")
    _git(fixture_repo, "add", "apps")
    _git(fixture_repo, "commit", "-m", "ready feature")
    sha = _git(fixture_repo, "rev-parse", "HEAD")
    assert _run(fixture_repo, "attach-commit", cid, sha).returncode == 0
    assert _run(fixture_repo, "update", cid, "--test", "unit").returncode == 0
    assert _run(fixture_repo, "mark", cid, "implemented").returncode == 0
    assert _run(fixture_repo, "mark", cid, "tested").returncode == 0
    assert _run(fixture_repo, "update", cid, "--evidence", "ok").returncode == 0
    assert _run(fixture_repo, "mark", cid, "verified").returncode == 0
    assert _run(fixture_repo, "mark", cid, "ready").returncode == 0
    _git(fixture_repo, "add", "release")
    _git(fixture_repo, "commit", "-m", "register ready change")
    assert _run(fixture_repo, "freeze").returncode == 0, _run(fixture_repo, "freeze").stdout
    _git(fixture_repo, "add", "release")
    _git(fixture_repo, "commit", "-m", "freeze")
    before = (fixture_repo / "VERSION").read_text(encoding="utf-8")
    preview = _run(fixture_repo, "prepare-next-release", "--bump", "patch")
    assert preview.returncode == 0, preview.stderr + preview.stdout
    assert "preview only" in preview.stdout
    assert (fixture_repo / "VERSION").read_text(encoding="utf-8") == before
    assert before.strip() == "1.0.2"
    assert before.strip() != "1.0.3"


def _advance_to_verified(root: Path, cid: str, *, source_line: str = "print('v')\n") -> str:
    _write(root / "apps" / "api" / "app" / "main.py", source_line)
    _git(root, "add", "apps")
    _git(root, "commit", "-m", f"impl {cid}")
    sha = _git(root, "rev-parse", "HEAD")
    assert _run(root, "attach-commit", cid, sha).returncode == 0
    assert _run(root, "update", cid, "--test", "unit").returncode == 0
    assert _run(root, "mark", cid, "implemented").returncode == 0
    assert _run(root, "mark", cid, "tested").returncode == 0
    assert _run(root, "update", cid, "--evidence", "ok").returncode == 0
    assert _run(root, "mark", cid, "verified").returncode == 0
    return sha


def test_adopt_legacy_without_confirm_does_not_write(fixture_repo: Path) -> None:
    baseline_path = fixture_repo / "release" / "baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["status"] = "unverified"
    baseline["installer_sha256"] = None
    baseline["released_at"] = None
    _write(baseline_path, json.dumps(baseline, indent=2) + "\n")
    before = baseline_path.read_text(encoding="utf-8")
    audit = fixture_repo / "release" / "generated" / "legacy-baseline-adoption.json"
    assert not audit.is_file()
    result = _run(fixture_repo, "baseline", "adopt-legacy")
    assert result.returncode == 0, result.stderr
    assert "preview only" in result.stdout
    assert baseline_path.read_text(encoding="utf-8") == before
    assert not audit.is_file()


def test_adopt_legacy_with_confirm_sets_legacy_verified(fixture_repo: Path) -> None:
    baseline_path = fixture_repo / "release" / "baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["status"] = "unverified"
    baseline["installer_sha256"] = None
    baseline["released_at"] = None
    baseline["notes"] = "keep me"
    _write(baseline_path, json.dumps(baseline, indent=2) + "\n")
    result = _run(fixture_repo, "baseline", "adopt-legacy", "--confirm")
    assert result.returncode == 0, result.stderr + result.stdout
    updated = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert updated["status"] == "legacy_verified"
    assert updated["legacy_source_baseline"] is True
    assert updated["legacy_adopted_at"]
    assert "52fd448" in updated["legacy_adoption_notes"]
    assert "does NOT claim" in updated["legacy_adoption_notes"]
    assert updated["notes"] == "keep me"
    assert updated["git_tag"] is None
    assert updated["installer_sha256"] is None
    assert updated["released_at"] is None
    audit = json.loads(
        (fixture_repo / "release" / "generated" / "legacy-baseline-adoption.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["new_status"] == "legacy_verified"
    # verify still fails for legacy_verified
    verify = _run(fixture_repo, "baseline", "verify")
    assert verify.returncode != 0
    assert "legacy_verified" in verify.stdout


def test_cannot_mark_ready_for_staging_without_evidence(fixture_repo: Path) -> None:
    reg = _run(fixture_repo, "register", "--title", "Staging gate", "--type", "updater")
    cid = reg.stdout.strip().splitlines()[0]
    assert _run(fixture_repo, "mark", cid, "ready-for-staging").returncode != 0
    _advance_to_verified(fixture_repo, cid)
    # strip evidence via raw edit to prove gate
    path = fixture_repo / "release" / "changes" / f"{cid}.json"
    change = json.loads(path.read_text(encoding="utf-8"))
    change["verification_evidence"] = []
    change["tests"] = []
    _write(path, json.dumps(change, indent=2) + "\n")
    bad = _run(fixture_repo, "mark", cid, "ready-for-staging")
    assert bad.returncode != 0
    assert "evidence" in (bad.stdout + bad.stderr).lower() or "tests" in (
        bad.stdout + bad.stderr
    ).lower()
    # restore evidence and succeed
    change["tests"] = ["unit"]
    change["verification_evidence"] = ["ok"]
    _write(path, json.dumps(change, indent=2) + "\n")
    assert _run(fixture_repo, "mark", cid, "ready-for-staging").returncode == 0


def test_freeze_accepts_legacy_verified_and_ready_for_staging(fixture_repo: Path) -> None:
    baseline_path = fixture_repo / "release" / "baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["status"] = "unverified"
    baseline["installer_sha256"] = None
    baseline["released_at"] = None
    _write(baseline_path, json.dumps(baseline, indent=2) + "\n")
    assert _run(fixture_repo, "baseline", "adopt-legacy", "--confirm").returncode == 0
    _git(fixture_repo, "add", "release")
    _git(fixture_repo, "commit", "-m", "adopt legacy baseline")

    reg = _run(
        fixture_repo,
        "register",
        "--title",
        "Staging item",
        "--type",
        "updater",
        "--user-summary",
        "updater staging",
    )
    cid = reg.stdout.strip().splitlines()[0]
    _advance_to_verified(fixture_repo, cid, source_line="print('staging')\n")
    assert _run(fixture_repo, "mark", cid, "ready-for-staging").returncode == 0
    _git(fixture_repo, "add", "release")
    _git(fixture_repo, "commit", "-m", "register staging change")

    preview = _run(fixture_repo, "release-preview")
    assert preview.returncode == 0
    payload = json.loads(preview.stdout)
    assert payload["can_freeze"] is True
    assert any("staging verification required" in b for b in payload["blockers"])

    freeze = _run(fixture_repo, "freeze")
    assert freeze.returncode == 0, freeze.stdout + freeze.stderr
    pool = json.loads(
        (fixture_repo / "release" / "unreleased.json").read_text(encoding="utf-8")
    )
    assert pool["status"] == "frozen"
