#!/usr/bin/env python3
"""StoryLens change registration pool and next-release aggregation.

Daily development registers changes without bumping VERSION.
Only ``prepare-next-release --confirm`` (after freeze) may bump.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

CHANGE_ID_RE = re.compile(r"^CHG-(\d{8})-(\d{3})$")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
)
TRAILER_RE = re.compile(
    r"^StoryLens-Change:\s*(CHG-\d{8}-\d{3})\s*$",
    re.MULTILINE | re.IGNORECASE,
)

VALID_TYPES = frozenset(
    {
        "feature",
        "improvement",
        "fix",
        "security",
        "performance",
        "database",
        "build",
        "updater",
        "documentation",
    }
)
VALID_STATUSES = frozenset(
    {
        "registered",
        "implemented",
        "tested",
        "verified",
        "ready-for-staging",
        "ready",
        "deferred",
        "released",
    }
)
PROGRESS_STATUSES = (
    "registered",
    "implemented",
    "tested",
    "verified",
    "ready-for-staging",
    "ready",
    "released",
)
# Acceptable for freeze / release inclusion (code-level ready; staging may still be pending).
FREEZE_READY_STATUSES = frozenset({"ready", "ready-for-staging"})
# Baseline statuses that satisfy freeze / release-mode gates (not full artifact verify).
BASELINE_ACCEPTABLE_STATUSES = frozenset({"verified", "legacy_verified"})


def is_freeze_ready_status(status: Any) -> bool:
    return status in FREEZE_READY_STATUSES


def is_baseline_acceptable(status: Any) -> bool:
    return status in BASELINE_ACCEPTABLE_STATUSES


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_version(root: Path) -> str:
    path = root / "VERSION"
    if not path.is_file():
        raise ValueError("VERSION file missing")
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(lines) != 1:
        raise ValueError("VERSION must contain exactly one SemVer line")
    if not SEMVER_RE.fullmatch(lines[0]):
        raise ValueError(f"invalid VERSION: {lines[0]!r}")
    return lines[0]


def bump_patch(version: str) -> str:
    major, minor, patch = (int(p) for p in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def git(root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    # Force UTF-8: commit subjects may contain arrows/CJK that break Windows locale (GBK).
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def git_ok(root: Path, *args: str) -> bool:
    return git(root, *args).returncode == 0


def git_out(root: Path, *args: str) -> str:
    proc = git(root, *args)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git failed")
    return proc.stdout.strip()


def resolve_commit(root: Path, rev: str) -> str | None:
    proc = git(root, "rev-parse", "--verify", f"{rev}^{{commit}}")
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def commit_subject(root: Path, sha: str) -> str:
    return git_out(root, "log", "-1", "--format=%s", sha)


def commit_body(root: Path, sha: str) -> str:
    return git_out(root, "log", "-1", "--format=%B", sha)


def is_ancestor(root: Path, commit: str, head: str = "HEAD") -> bool:
    return git_ok(root, "merge-base", "--is-ancestor", commit, head)


def resolved_integration_commit(root: Path, change: dict[str, Any]) -> str | None:
    """Return full sha when change.integrated_into resolves and is reachable from HEAD."""
    integrated_into = change.get("integrated_into")
    if not isinstance(integrated_into, str) or not integrated_into.strip():
        return None
    resolved = resolve_commit(root, integrated_into.strip())
    if not resolved or not is_ancestor(root, resolved):
        return None
    return resolved


def commit_included_in_head(root: Path, change: dict[str, Any], sha: str) -> bool:
    """True when sha is in HEAD history or explicitly integrated via integrated_into."""
    if is_ancestor(root, sha):
        return True
    return resolved_integration_commit(root, change) is not None


def working_tree_dirty(root: Path) -> list[str]:
    proc = git(root, "status", "--porcelain")
    if proc.returncode != 0:
        return ["<git status failed>"]
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def release_dir(root: Path) -> Path:
    return root / "release"


def changes_dir(root: Path) -> Path:
    return release_dir(root) / "changes"


def load_config(root: Path) -> dict[str, Any]:
    path = release_dir(root) / "registry_config.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing {path}")
    return read_json(path)


def load_baseline(root: Path) -> dict[str, Any]:
    path = release_dir(root) / "baseline.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing {path}")
    return read_json(path)


def save_baseline(root: Path, data: dict[str, Any]) -> None:
    write_json(release_dir(root) / "baseline.json", data)


def load_unreleased(root: Path) -> dict[str, Any]:
    path = release_dir(root) / "unreleased.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing {path}")
    return read_json(path)


def save_unreleased(root: Path, data: dict[str, Any]) -> None:
    write_json(release_dir(root) / "unreleased.json", data)


def load_change(root: Path, change_id: str) -> dict[str, Any]:
    path = changes_dir(root) / f"{change_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"change not found: {change_id}")
    return read_json(path)


def save_change(root: Path, change: dict[str, Any]) -> None:
    write_json(changes_dir(root) / f"{change['id']}.json", change)


def list_change_files(root: Path) -> list[Path]:
    directory = changes_dir(root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("CHG-*.json"))


def load_all_changes(root: Path) -> list[dict[str, Any]]:
    return [read_json(path) for path in list_change_files(root)]


def load_release_pool_changes(root: Path) -> list[dict[str, Any]]:
    """Return only changes that belong to the current baseline's release pool.

    Historical records remain in ``release/changes`` for traceability and older
    repositories may also keep their ids in ``unreleased.json``.  They must not
    block a later baseline merely because their legacy
    ``include_in_next_release`` flag was never cleared.
    """
    unreleased = load_unreleased(root)
    pool_ids = set(unreleased.get("changes") or [])
    base_version = unreleased.get("base_version")
    return [
        change
        for change in load_all_changes(root)
        if change.get("id") in pool_ids and change.get("base_version") == base_version
    ]


def validate_change_shape(change: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "id",
        "title",
        "type",
        "base_version",
        "status",
        "include_in_next_release",
        "commits",
        "modules",
        "files",
        "user_summary",
        "technical_summary",
        "acceptance_criteria",
        "tests",
        "verification_evidence",
        "data_compatibility",
        "release_impact",
        "created_at",
        "updated_at",
    ]
    for key in required:
        if key not in change:
            errors.append(f"missing field: {key}")
    change_id = change.get("id")
    if isinstance(change_id, str) and not CHANGE_ID_RE.fullmatch(change_id):
        errors.append(f"invalid change id: {change_id}")
    if change.get("type") not in VALID_TYPES:
        errors.append(f"invalid type: {change.get('type')}")
    if change.get("status") not in VALID_STATUSES:
        errors.append(f"invalid status: {change.get('status')}")
    if not isinstance(change.get("include_in_next_release"), bool):
        errors.append("include_in_next_release must be bool")
    for list_key in (
        "commits",
        "modules",
        "files",
        "acceptance_criteria",
        "tests",
        "verification_evidence",
    ):
        if list_key in change and not isinstance(change[list_key], list):
            errors.append(f"{list_key} must be a list")
    compat = change.get("data_compatibility")
    if isinstance(compat, dict):
        for key in (
            "database_changed",
            "migration_required",
            "user_data_compatible",
            "notes",
        ):
            if key not in compat:
                errors.append(f"data_compatibility missing {key}")
    else:
        errors.append("data_compatibility must be object")
    impact = change.get("release_impact")
    if isinstance(impact, dict):
        for key in (
            "requires_reanalysis",
            "requires_restart",
            "updater_impact",
            "breaking_change",
        ):
            if key not in impact:
                errors.append(f"release_impact missing {key}")
    else:
        errors.append("release_impact must be object")
    return errors


def next_change_id(root: Path, when: datetime | None = None) -> str:
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%d")
    prefix = f"CHG-{stamp}-"
    max_n = 0
    for path in list_change_files(root):
        match = CHANGE_ID_RE.fullmatch(path.stem)
        if match and match.group(1) == stamp:
            max_n = max(max_n, int(match.group(2)))
    return f"{prefix}{max_n + 1:03d}"


def path_requires_registration(path: str, config: dict[str, Any]) -> bool:
    normalized = path.replace("\\", "/")
    for prefix in config.get("ignore_path_prefixes", []):
        if normalized == prefix.rstrip("/") or normalized.startswith(prefix):
            return False
    if normalized in set(config.get("ignore_path_exact", [])):
        return False
    for prefix in config.get("required_registration_prefixes", []):
        if normalized == prefix.rstrip("/") or normalized.startswith(prefix):
            return True
        # bare filenames listed as prefixes (package.json etc.)
        if "/" not in prefix.rstrip("/") and normalized.endswith("/" + prefix):
            return True
        if normalized == prefix:
            return True
    for needle in config.get("required_registration_path_substrings", []):
        if needle in normalized:
            return True
    return False


def commit_changed_paths(root: Path, sha: str) -> list[str]:
    out = git_out(root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
    return [ln.replace("\\", "/") for ln in out.splitlines() if ln.strip()]


def is_docs_only_commit(root: Path, sha: str, config: dict[str, Any]) -> bool:
    subject = commit_subject(root, sha)
    for marker in config.get("docs_only_subject_markers", []):
        if marker.lower() in subject.lower():
            return True
    paths = commit_changed_paths(root, sha)
    if not paths:
        return True
    return not any(path_requires_registration(p, config) for p in paths)


def trailers_for_commit(root: Path, sha: str) -> list[str]:
    body = commit_body(root, sha)
    return [m.group(1).upper().replace("CHG-", "CHG-") for m in TRAILER_RE.finditer(body)]


def normalize_trailer_ids(ids: list[str]) -> list[str]:
    result: list[str] = []
    for raw in ids:
        match = CHANGE_ID_RE.fullmatch(raw.strip())
        if match:
            result.append(f"CHG-{match.group(1)}-{match.group(2)}")
    return result


def commit_entry_sha(entry: Any) -> str | None:
    """Normalize legacy bare-SHA commit entries and dict entries to a sha string."""
    if isinstance(entry, str):
        return entry or None
    if isinstance(entry, dict):
        sha = entry.get("sha")
        return sha if isinstance(sha, str) and sha else None
    return None


def registered_commit_map(root: Path) -> dict[str, list[str]]:
    """Map full sha -> list of change ids."""
    mapping: dict[str, list[str]] = {}
    for change in load_release_pool_changes(root):
        for entry in change.get("commits") or []:
            sha = commit_entry_sha(entry)
            if isinstance(sha, str) and sha:
                mapping.setdefault(sha, []).append(change["id"])
                # also short
                mapping.setdefault(sha[:7], []).append(change["id"])
    return mapping


def classify_commits(
    root: Path,
    baseline_commit: str | None,
    head: str = "HEAD",
) -> dict[str, list[dict[str, Any]]]:
    config = load_config(root)
    result: dict[str, list[dict[str, Any]]] = {
        "REGISTERED": [],
        "UNREGISTERED": [],
        "IGNORED": [],
    }
    if not baseline_commit:
        return result
    if not resolve_commit(root, baseline_commit):
        return result
    rev_range = f"{baseline_commit}..{head}"
    proc = git(root, "rev-list", "--reverse", rev_range)
    if proc.returncode != 0:
        return result
    shas = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    change_by_commit = registered_commit_map(root)
    for sha in shas:
        subject = commit_subject(root, sha)
        trailer_ids = normalize_trailer_ids(
            [m.group(1) for m in TRAILER_RE.finditer(commit_body(root, sha))]
        )
        registry_ids = change_by_commit.get(sha, []) + change_by_commit.get(sha[:7], [])
        linked = sorted(set(registry_ids + trailer_ids))
        entry = {
            "sha": sha,
            "short": sha[:7],
            "subject": subject,
            "change_ids": linked,
        }
        if linked:
            # ensure trailer ids exist as files when claimed
            missing = [cid for cid in trailer_ids if not (changes_dir(root) / f"{cid}.json").is_file()]
            if missing:
                entry["missing_change_files"] = missing
                result["UNREGISTERED"].append(entry)
            else:
                result["REGISTERED"].append(entry)
            continue
        if is_docs_only_commit(root, sha, config):
            result["IGNORED"].append(entry)
        else:
            result["UNREGISTERED"].append(entry)
    return result


def status_rank(status: str) -> int:
    if status == "deferred":
        return -1
    try:
        return PROGRESS_STATUSES.index(status)
    except ValueError:
        return -2


def can_mark_status(change: dict[str, Any], new_status: str) -> list[str]:
    errors: list[str] = []
    current = change.get("status")
    if new_status not in VALID_STATUSES:
        return [f"invalid status: {new_status}"]
    if new_status == current:
        return []
    if new_status == "deferred":
        return []
    if current == "released":
        return ["released changes are immutable"]
    if new_status == "released":
        if current != "ready":
            errors.append("only ready changes can be marked released")
        return errors
    if current == "deferred" and new_status != "registered":
        return ["deferred changes must return to registered before progressing"]
    if new_status == "registered":
        return []
    if new_status == "implemented":
        if not change.get("commits"):
            errors.append("cannot mark implemented without attached commits")
    elif new_status == "tested":
        if status_rank(current) < status_rank("implemented"):
            errors.append("must be implemented before tested")
        if not change.get("tests"):
            errors.append("cannot mark tested without tests evidence")
    elif new_status == "verified":
        if status_rank(current) < status_rank("tested"):
            errors.append("must be tested before verified")
        if not change.get("verification_evidence"):
            errors.append("cannot mark verified without verification evidence")
    elif new_status == "ready-for-staging":
        if current != "verified":
            errors.append("only verified changes can be marked ready-for-staging")
        if not change.get("tests"):
            errors.append("ready-for-staging requires tests evidence")
        if not change.get("verification_evidence"):
            errors.append("ready-for-staging requires verification evidence")
        if change.get("head_inclusion") in {"EXISTS_NOT_INCLUDED", "NOT_FOUND"}:
            errors.append("change not included in HEAD cannot be ready-for-staging")
        # Prefer updater-scoped changes for staging; soft preference (not a hard gate).
        impact = change.get("release_impact") or {}
        if change.get("type") != "updater" and not impact.get("updater_impact"):
            pass  # preferably updater / updater_impact; do not block
    elif new_status == "ready":
        if current not in {"verified", "ready-for-staging"}:
            errors.append(
                "only verified or ready-for-staging changes can be marked ready"
            )
        if not change.get("tests"):
            errors.append("ready requires tests evidence")
        if not change.get("verification_evidence"):
            errors.append("ready requires verification evidence")
        if change.get("head_inclusion") in {"EXISTS_NOT_INCLUDED", "NOT_FOUND"}:
            errors.append("change not included in HEAD cannot be ready")
    return list(dict.fromkeys(errors))


def default_change_payload(
    change_id: str,
    title: str,
    change_type: str,
    base_version: str,
    user_summary: str = "",
) -> dict[str, Any]:
    now = utc_now()
    return {
        "id": change_id,
        "title": title,
        "type": change_type,
        "base_version": base_version,
        "status": "registered",
        "include_in_next_release": True,
        "commits": [],
        "modules": [],
        "files": [],
        "user_summary": user_summary,
        "technical_summary": "",
        "acceptance_criteria": [],
        "tests": [],
        "verification_evidence": [],
        "data_compatibility": {
            "database_changed": False,
            "migration_required": False,
            "user_data_compatible": True,
            "notes": "",
        },
        "release_impact": {
            "requires_reanalysis": False,
            "requires_restart": False,
            "updater_impact": False,
            "breaking_change": False,
        },
        "blocker_level": None,
        "head_inclusion": None,
        "created_at": now,
        "updated_at": now,
    }


def collect_blockers(root: Path) -> list[str]:
    """Hard blockers for freeze / prepare. Soft staging notes are collected separately."""
    blockers: list[str] = []
    baseline = load_baseline(root)
    if not is_baseline_acceptable(baseline.get("status")):
        blockers.append("baseline status is not verified")
    unreleased = load_unreleased(root)
    if unreleased.get("target_version") is not None and unreleased.get("status") == "collecting":
        blockers.append("collecting pool must not preset target_version")
    classified = classify_commits(root, baseline.get("git_commit"))
    for item in classified["UNREGISTERED"]:
        blockers.append(f"unregistered commit {item['short']}: {item['subject']}")
    for change in load_release_pool_changes(root):
        if not change.get("include_in_next_release", True):
            continue
        if change.get("status") == "deferred":
            for entry in change.get("commits") or []:
                sha = commit_entry_sha(entry)
                if isinstance(sha, str) and resolve_commit(root, sha) and is_ancestor(root, sha):
                    # deferred code present in HEAD without feature-flag evidence
                    flag_notes = (change.get("technical_summary") or "") + " ".join(
                        change.get("verification_evidence") or []
                    )
                    if "feature flag" not in flag_notes.lower() and "feature_flag" not in flag_notes.lower():
                        blockers.append(
                            f"deferred change {change['id']} still has commits in HEAD"
                        )
                        break
        if change.get("blocker_level") in {"P0", "P1"}:
            if not is_freeze_ready_status(change.get("status")):
                blockers.append(
                    f"{change.get('blocker_level')} blocker {change['id']}: status={change.get('status')}"
                )
        if change.get("include_in_next_release") and change.get("status") not in {
            "ready",
            "ready-for-staging",
            "released",
            "deferred",
        }:
            # not a hard freeze blocker list item unless preparing; recorded for preview
            pass
    return blockers


def collect_staging_notes(root: Path) -> list[str]:
    """Soft notes for release-preview; must not block freeze / can_prepare alone."""
    notes: list[str] = []
    for change in load_release_pool_changes(root):
        if not change.get("include_in_next_release", True):
            continue
        if change.get("status") == "ready-for-staging":
            notes.append(
                f"{change['id']}: staging verification required "
                f"(status=ready-for-staging)"
            )
    return notes


def preview_payload(root: Path) -> dict[str, Any]:
    version = read_version(root)
    baseline = load_baseline(root)
    unreleased = load_unreleased(root)
    changes = load_release_pool_changes(root)
    included = [c for c in changes if c.get("include_in_next_release") and c.get("status") != "deferred"]
    ready = [c for c in included if is_freeze_ready_status(c.get("status"))]
    classified = classify_commits(root, baseline.get("git_commit"))
    blockers = collect_blockers(root)
    staging_notes = collect_staging_notes(root)
    not_ready = [
        f"{c['id']} status={c['status']}"
        for c in included
        if not is_freeze_ready_status(c.get("status"))
    ]
    dirty = working_tree_dirty(root)
    can_freeze = (
        not classified["UNREGISTERED"]
        and not not_ready
        and not dirty
        and is_baseline_acceptable(baseline.get("status"))
        and unreleased.get("status") == "collecting"
        and not any(
            c.get("blocker_level") in {"P0", "P1"} and not is_freeze_ready_status(c.get("status"))
            for c in changes
        )
    )
    # can_prepare needs frozen + ready etc.
    can_prepare_release = (
        unreleased.get("status") == "frozen"
        and not classified["UNREGISTERED"]
        and not not_ready
        and is_baseline_acceptable(baseline.get("status"))
        and not dirty
    )
    return {
        "base_version": unreleased.get("base_version") or baseline.get("version") or version,
        "next_patch": bump_patch(version),
        "change_count": len(included),
        "ready_count": len(ready),
        "unregistered_commits": [
            {"sha": i["short"], "subject": i["subject"]} for i in classified["UNREGISTERED"]
        ],
        "blockers": blockers + not_ready + staging_notes,
        "can_freeze": bool(can_freeze),
        "can_prepare_release": bool(can_prepare_release),
    }


def cmd_status(root: Path) -> int:
    version = read_version(root)
    baseline = load_baseline(root)
    unreleased = load_unreleased(root)
    changes = load_release_pool_changes(root)
    included = [c for c in changes if c.get("include_in_next_release")]
    ready = [c for c in included if is_freeze_ready_status(c.get("status"))]
    deferred = [c for c in changes if c.get("status") == "deferred"]
    incomplete = [
        c
        for c in included
        if c.get("status") not in {"ready", "ready-for-staging", "released", "deferred"}
    ]
    classified = classify_commits(root, baseline.get("git_commit"))
    preview = preview_payload(root)
    print(f"base_version (baseline): {baseline.get('version')}")
    print(f"VERSION: {version}")
    print(f"unreleased.status: {unreleased.get('status')}")
    print(f"next_patch_preview: {bump_patch(version)}")
    print(f"registered_count: {len(changes)}")
    print(f"ready_count: {len(ready)}")
    print(f"incomplete_count: {len(incomplete)}")
    print(f"deferred_count: {len(deferred)}")
    print(f"unregistered_commit_count: {len(classified['UNREGISTERED'])}")
    print(f"can_prepare_next_release: {preview['can_prepare_release']}")
    return 0


def cmd_baseline_show(root: Path) -> int:
    baseline = load_baseline(root)
    print(json.dumps(baseline, ensure_ascii=False, indent=2))
    return 0


LEGACY_ADOPTION_NOTES = (
    "1. 1.0.2 version commit exists (52fd44894b41fa48192fc06ef1e189acb517b8f5).\n"
    "2. current HEAD is a descendant of that baseline commit.\n"
    "3. Historical Git tag and complete release artifacts are missing.\n"
    "4. 1.0.3 will be the first fully traceable version after enabling release baseline management.\n"
    "5. User explicitly authorized generating the next version.\n"
    "6. This adoption does NOT claim historical installer/tag/manifest artifacts were verified."
)


def cmd_baseline_adopt_legacy(root: Path, *, confirm: bool = False) -> int:
    baseline = load_baseline(root)
    preview = {
        "current_status": baseline.get("status"),
        "would_set_status": "legacy_verified",
        "legacy_source_baseline": True,
        "legacy_adoption_notes": LEGACY_ADOPTION_NOTES,
        "preserved_notes": baseline.get("notes"),
        "confirm": confirm,
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if not confirm:
        print("preview only — pass --confirm to write legacy_verified adoption")
        return 0
    if baseline.get("status") != "unverified":
        print(
            "error: adopt-legacy only allowed when baseline.status is unverified, "
            f"got {baseline.get('status')!r}",
            file=sys.stderr,
        )
        return 1
    now = utc_now()
    baseline["status"] = "legacy_verified"
    baseline["legacy_source_baseline"] = True
    baseline["legacy_adopted_at"] = now
    baseline["legacy_adoption_notes"] = LEGACY_ADOPTION_NOTES
    # Keep existing notes; do not invent tag/sha256/released_at
    save_baseline(root, baseline)
    audit = {
        "adopted_at": now,
        "previous_status": "unverified",
        "new_status": "legacy_verified",
        "baseline_version": baseline.get("version"),
        "baseline_git_commit": baseline.get("git_commit"),
        "legacy_source_baseline": True,
        "legacy_adoption_notes": LEGACY_ADOPTION_NOTES,
        "notes_preserved": baseline.get("notes"),
        "git_tag": baseline.get("git_tag"),
        "installer_sha256": baseline.get("installer_sha256"),
        "released_at": baseline.get("released_at"),
    }
    write_json(release_dir(root) / "generated" / "legacy-baseline-adoption.json", audit)
    print("baseline adopted as legacy_verified")
    print("wrote release/generated/legacy-baseline-adoption.json")
    return 0


def cmd_baseline_verify(root: Path) -> int:
    errors: list[str] = []
    baseline = load_baseline(root)
    version = read_version(root)
    if baseline.get("version") != version:
        errors.append(
            f"baseline.version {baseline.get('version')!r} != VERSION {version!r}"
        )
    commit = baseline.get("git_commit")
    if not commit:
        errors.append("baseline.git_commit is empty")
    else:
        resolved = resolve_commit(root, commit)
        if not resolved:
            errors.append(f"baseline.git_commit not found: {commit}")
        else:
            if resolved != commit and not commit.startswith(resolved[:7]):
                # accept abbreviated if unique
                pass
            if not is_ancestor(root, resolved):
                errors.append("baseline.git_commit is not an ancestor of HEAD")
            # VERSION at baseline commit
            show = git(root, "show", f"{resolved}:VERSION")
            if show.returncode == 0:
                base_ver = show.stdout.strip().splitlines()[0].strip() if show.stdout.strip() else ""
                if base_ver != baseline.get("version"):
                    errors.append(
                        f"VERSION at baseline commit is {base_ver!r}, baseline.version is {baseline.get('version')!r}"
                    )
    tag = baseline.get("git_tag")
    expected_tag = f"v{baseline.get('version')}"
    if tag:
        if not git_ok(root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}"):
            errors.append(f"baseline.git_tag missing: {tag}")
    else:
        if git_ok(root, "rev-parse", "-q", "--verify", f"refs/tags/{expected_tag}"):
            errors.append(
                f"tag {expected_tag} exists but baseline.git_tag is null — update baseline"
            )
    status = baseline.get("status")
    if status == "legacy_verified":
        errors.append(
            "baseline.status is legacy_verified — not fully verified "
            "(legacy adoption satisfies freeze gates only; full verify still fails until "
            "artifacts/tag evidence exist and status becomes verified)"
        )
    elif status != "verified":
        errors.append(f"baseline.status is {status!r}, not verified")
    # release evidence
    if not baseline.get("installer_sha256"):
        errors.append("baseline.installer_sha256 missing (no installer attestation)")
    if not baseline.get("released_at"):
        errors.append("baseline.released_at missing")
    if errors:
        print("baseline verify FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("baseline verify passed")
    return 0


def cmd_register(
    root: Path,
    title: str,
    change_type: str,
    user_summary: str = "",
) -> int:
    unreleased = load_unreleased(root)
    if unreleased.get("status") == "frozen":
        print("error: unreleased pool is frozen; refuse new feature registration", file=sys.stderr)
        return 1
    if unreleased.get("status") == "released":
        print("error: unreleased pool is released; create a new pool first", file=sys.stderr)
        return 1
    if change_type not in VALID_TYPES:
        print(f"error: invalid type {change_type}", file=sys.stderr)
        return 1
    version = read_version(root)
    change_id = next_change_id(root)
    change = default_change_payload(
        change_id, title, change_type, version, user_summary=user_summary
    )
    save_change(root, change)
    changes = list(unreleased.get("changes") or [])
    if change_id not in changes:
        changes.append(change_id)
    unreleased["changes"] = changes
    save_unreleased(root, unreleased)
    print(change_id)
    print(f"wrote release/changes/{change_id}.json")
    return 0


def cmd_attach_commit(
    root: Path,
    change_id: str,
    rev: str,
    *,
    primary: bool = True,
    multi_reason: str | None = None,
) -> int:
    resolved = resolve_commit(root, rev)
    if not resolved:
        print(f"error: commit not found: {rev}", file=sys.stderr)
        return 1
    change = load_change(root, change_id)
    # same commit primary uniqueness
    for other in load_all_changes(root):
        if other["id"] == change_id:
            continue
        for entry in other.get("commits") or []:
            if commit_entry_sha(entry) == resolved and (isinstance(entry, str) or entry.get("primary", True)):
                if primary and not multi_reason:
                    print(
                        "error: commit already primary for "
                        f"{other['id']}; pass --multi-change-reason to share",
                        file=sys.stderr,
                    )
                    return 1
    commits = list(change.get("commits") or [])
    if any(commit_entry_sha(c) == resolved for c in commits):
        print(f"already attached: {resolved}")
        return 0
    commits.append(
        {
            "sha": resolved,
            "message": commit_subject(root, resolved),
            "primary": primary,
            "multi_change_reason": multi_reason,
        }
    )
    change["commits"] = commits
    if is_ancestor(root, resolved):
        change["head_inclusion"] = "INCLUDED"
    else:
        change["head_inclusion"] = "EXISTS_NOT_INCLUDED"
    change["updated_at"] = utc_now()
    save_change(root, change)
    print(f"attached {resolved} to {change_id} ({change['head_inclusion']})")
    return 0


def cmd_mark(root: Path, change_id: str, new_status: str) -> int:
    change = load_change(root, change_id)
    errors = can_mark_status(change, new_status)
    if errors:
        print("error: status transition rejected:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    change["status"] = new_status
    change["updated_at"] = utc_now()
    save_change(root, change)
    print(f"{change_id} -> {new_status}")
    return 0


def cmd_update(root: Path, change_id: str, args: argparse.Namespace) -> int:
    change = load_change(root, change_id)
    if args.status:
        errors = can_mark_status(change, args.status)
        if errors:
            print("error: status transition rejected:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        change["status"] = args.status
    if args.user_summary is not None:
        change["user_summary"] = args.user_summary
    if args.technical_summary is not None:
        change["technical_summary"] = args.technical_summary
    if args.module:
        change["modules"] = list(dict.fromkeys((change.get("modules") or []) + list(args.module)))
    if args.file:
        change["files"] = list(dict.fromkeys((change.get("files") or []) + list(args.file)))
    if args.test:
        change["tests"] = list(dict.fromkeys((change.get("tests") or []) + list(args.test)))
    if args.evidence:
        change["verification_evidence"] = list(
            dict.fromkeys((change.get("verification_evidence") or []) + list(args.evidence))
        )
    if args.acceptance:
        change["acceptance_criteria"] = list(
            dict.fromkeys((change.get("acceptance_criteria") or []) + list(args.acceptance))
        )
    if args.database_changed is not None:
        change["data_compatibility"]["database_changed"] = args.database_changed
    if args.migration_required is not None:
        change["data_compatibility"]["migration_required"] = args.migration_required
    if args.user_data_compatible is not None:
        change["data_compatibility"]["user_data_compatible"] = args.user_data_compatible
    if args.compat_notes is not None:
        change["data_compatibility"]["notes"] = args.compat_notes
    if args.requires_reanalysis is not None:
        change["release_impact"]["requires_reanalysis"] = args.requires_reanalysis
    if args.requires_restart is not None:
        change["release_impact"]["requires_restart"] = args.requires_restart
    if args.updater_impact is not None:
        change["release_impact"]["updater_impact"] = args.updater_impact
    if args.breaking_change is not None:
        change["release_impact"]["breaking_change"] = args.breaking_change
    if args.blocker_level is not None:
        change["blocker_level"] = None if args.blocker_level == "none" else args.blocker_level
    if args.head_inclusion is not None:
        change["head_inclusion"] = args.head_inclusion
    if args.include_in_next_release is not None:
        change["include_in_next_release"] = args.include_in_next_release
    change["updated_at"] = utc_now()
    save_change(root, change)
    print(f"updated {change_id}")
    return 0


def check_registry(root: Path, *, release_mode: bool = False) -> list[str]:
    errors: list[str] = []
    try:
        version = read_version(root)
    except ValueError as exc:
        return [str(exc)]
    try:
        baseline = load_baseline(root)
        unreleased = load_unreleased(root)
        config = load_config(root)
    except FileNotFoundError as exc:
        return [str(exc)]

    target = unreleased.get("target_version")
    frozen_prepared = (
        unreleased.get("status") == "frozen" and isinstance(target, str) and bool(target)
    )
    if frozen_prepared:
        # After prepare-next-release: VERSION tracks target; baseline stays on prior base.
        if version != target:
            errors.append(
                f"VERSION {version} != unreleased.target_version {target}"
            )
        if unreleased.get("base_version") != baseline.get("version"):
            errors.append(
                "frozen prepared pool: unreleased.base_version must match baseline.version"
            )
    else:
        if unreleased.get("base_version") != version:
            errors.append(
                f"VERSION {version} != unreleased.base_version {unreleased.get('base_version')}"
            )
        if baseline.get("version") != version:
            errors.append(
                f"VERSION {version} != baseline.version {baseline.get('version')}"
            )
    if unreleased.get("status") == "collecting" and unreleased.get("target_version") is not None:
        errors.append("collecting pool must keep target_version null")
    if unreleased.get("status") not in {"collecting", "frozen", "released"}:
        errors.append(f"invalid unreleased.status: {unreleased.get('status')}")

    # baseline structural validity
    if not baseline.get("git_commit"):
        errors.append("baseline.git_commit missing")
    elif not resolve_commit(root, baseline["git_commit"]):
        errors.append(f"baseline.git_commit invalid: {baseline['git_commit']}")

    if release_mode and not is_baseline_acceptable(baseline.get("status")):
        errors.append("release mode requires baseline.status=verified or legacy_verified")

    ids: list[str] = []
    changes = load_all_changes(root)
    for change in changes:
        shape_errors = validate_change_shape(change)
        for err in shape_errors:
            errors.append(f"{change.get('id', '<unknown>')}: {err}")
        cid = change.get("id")
        if isinstance(cid, str):
            if cid in ids:
                errors.append(f"duplicate change id: {cid}")
            ids.append(cid)
        for entry in change.get("commits") or []:
            # Legacy entries may be bare SHA strings; new entries are {sha, ...}.
            sha = commit_entry_sha(entry)
            if not isinstance(sha, str) or not resolve_commit(root, sha):
                errors.append(f"{cid}: commit missing: {sha}")
                continue
            if not commit_included_in_head(root, change, sha):
                # allowed for EXISTS_NOT_INCLUDED but flag if marked freeze-ready
                if is_freeze_ready_status(change.get("status")):
                    errors.append(
                        f"{cid}: {change.get('status')} but commit {sha[:7]} not in HEAD"
                    )
                if change.get("head_inclusion") not in {
                    "EXISTS_NOT_INCLUDED",
                    "NOT_FOUND",
                    None,
                }:
                    if change.get("head_inclusion") == "INCLUDED":
                        errors.append(
                            f"{cid}: head_inclusion=INCLUDED but commit not ancestor of HEAD"
                        )
            # status legality
        st = change.get("status")
        if st == "implemented" and not change.get("commits"):
            errors.append(f"{cid}: implemented without commits")
        if st == "tested" and not change.get("tests"):
            errors.append(f"{cid}: tested without tests evidence")
        if st == "verified" and not change.get("verification_evidence"):
            errors.append(f"{cid}: verified without verification evidence")
        if st in {"ready", "ready-for-staging"}:
            if not change.get("tests") or not change.get("verification_evidence"):
                errors.append(
                    f"{cid}: {st} without tests/verification evidence"
                )
            if not change.get("commits"):
                errors.append(f"{cid}: {st} without attached commits")
        if st == "deferred" and change.get("include_in_next_release"):
            for entry in change.get("commits") or []:
                sha = commit_entry_sha(entry)
                if isinstance(sha, str) and resolve_commit(root, sha) and is_ancestor(root, sha):
                    blob = (
                        (change.get("technical_summary") or "")
                        + " "
                        + " ".join(change.get("verification_evidence") or [])
                    ).lower()
                    if "feature flag" not in blob and "feature_flag" not in blob:
                        errors.append(
                            f"{cid}: deferred but commits still in HEAD without feature-flag evidence"
                        )
                        break

    # unreleased.changes consistency
    listed = list(unreleased.get("changes") or [])
    for cid in listed:
        if not (changes_dir(root) / f"{cid}.json").is_file():
            errors.append(f"unreleased.changes references missing file: {cid}")
    for change in changes:
        if (
            change["id"] not in listed
            and change.get("status") != "released"
            and change.get("include_in_next_release", True)
        ):
            # Included work is expected to be collected automatically. Explicitly
            # excluded work may live on an isolated product branch while another
            # release pool is frozen.
            errors.append(f"change {change['id']} not listed in unreleased.changes")

    classified = classify_commits(root, baseline.get("git_commit"))
    for item in classified["UNREGISTERED"]:
        errors.append(
            f"unregistered commit {item['short']}: {item['subject']}"
        )

    if release_mode:
        if unreleased.get("status") != "frozen":
            errors.append("release mode requires unreleased.status=frozen")
        for change in load_release_pool_changes(root):
            if not change.get("include_in_next_release"):
                continue
            if change.get("status") == "deferred":
                continue
            if not is_freeze_ready_status(change.get("status")):
                errors.append(
                    f"release mode: {change['id']} not ready ({change.get('status')})"
                )
        dirty = working_tree_dirty(root)
        if dirty:
            errors.append("release mode requires clean working tree")
        target = unreleased.get("target_version")
        if target and target != version:
            errors.append(f"VERSION {version} != unreleased.target_version {target}")

    _ = config  # loaded for future extension / ensures file exists
    return errors


def cmd_check(root: Path, *, release_mode: bool = False) -> int:
    errors = check_registry(root, release_mode=release_mode)
    if release_mode:
        baseline = load_baseline(root)
        if baseline.get("status") == "legacy_verified":
            print(
                "note: baseline.status=legacy_verified "
                "(legacy adoption; not fully artifact-verified)"
            )
    if errors:
        label = "Release registry check FAILED" if release_mode else "Change registry check FAILED"
        print(f"{label}:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Change registry check passed" + (" (release mode)" if release_mode else ""))
    return 0


def cmd_unregistered(root: Path) -> int:
    baseline = load_baseline(root)
    classified = classify_commits(root, baseline.get("git_commit"))
    for label in ("REGISTERED", "UNREGISTERED", "IGNORED"):
        print(f"== {label} ==")
        items = classified[label]
        if not items:
            print("(none)")
            continue
        for item in items:
            ids = ",".join(item.get("change_ids") or []) or "-"
            print(f"{item['short']}  {item['subject']}  [{ids}]")
    return 1 if classified["UNREGISTERED"] else 0


def cmd_freeze(root: Path) -> int:
    errors = check_registry(root, release_mode=False)
    baseline = load_baseline(root)
    unreleased = load_unreleased(root)
    if unreleased.get("status") != "collecting":
        print(f"error: cannot freeze from status {unreleased.get('status')}", file=sys.stderr)
        return 1
    if not is_baseline_acceptable(baseline.get("status")):
        errors.append("baseline must be verified or legacy_verified before freeze")
    dirty = working_tree_dirty(root)
    if dirty:
        errors.append("working tree not clean")
    changes = load_release_pool_changes(root)
    for change in changes:
        if not change.get("include_in_next_release"):
            continue
        if change.get("status") == "deferred":
            continue
        if not is_freeze_ready_status(change.get("status")):
            errors.append(f"{change['id']} not ready ({change.get('status')})")
        if change.get("blocker_level") in {"P0", "P1"} and not is_freeze_ready_status(
            change.get("status")
        ):
            errors.append(f"blocker {change['id']} unresolved")
    classified = classify_commits(root, baseline.get("git_commit"))
    for item in classified["UNREGISTERED"]:
        errors.append(f"unregistered commit {item['short']}")
    # VERSION check
    try:
        version = read_version(root)
        if version != unreleased.get("base_version"):
            errors.append("VERSION mismatch with base_version")
    except ValueError as exc:
        errors.append(str(exc))
    if errors:
        print("freeze FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    unreleased["status"] = "frozen"
    unreleased["frozen_at"] = utc_now()
    save_unreleased(root, unreleased)
    freeze_list = {
        "frozen_at": unreleased["frozen_at"],
        "base_version": unreleased["base_version"],
        "changes": [
            {
                "id": c["id"],
                "title": c["title"],
                "status": c["status"],
                "commits": [commit_entry_sha(x) for x in c.get("commits") or []],
            }
            for c in changes
            if c.get("include_in_next_release") and c.get("status") != "deferred"
        ],
    }
    write_json(release_dir(root) / "generated" / "freeze-manifest.json", freeze_list)
    print("unreleased pool frozen")
    return 0


def generate_release_notes(root: Path, version: str, changes: list[dict[str, Any]]) -> str:
    lines = [
        f"# StoryLens {version} Release Notes",
        "",
        "Status: **Unreleased**",
        "",
        "## 用户更新说明",
        "",
    ]
    for change in changes:
        summary = change.get("user_summary") or change.get("title")
        lines.append(f"- {summary}")
    lines.extend(["", "## 技术变更清单", ""])
    for change in changes:
        tech = change.get("technical_summary") or change.get("title")
        lines.append(f"- `{change['id']}` ({change.get('type')}): {tech}")
    lines.extend(["", "## Commit 清单", ""])
    for change in changes:
        for entry in change.get("commits") or []:
            lines.append(
                f"- `{entry.get('sha', '')[:7]}` — {entry.get('message')} ({change['id']})"
            )
    lines.extend(["", "## 数据库兼容说明", ""])
    for change in changes:
        compat = change.get("data_compatibility") or {}
        if compat.get("database_changed") or compat.get("migration_required"):
            lines.append(
                f"- `{change['id']}`: changed={compat.get('database_changed')} "
                f"migration={compat.get('migration_required')} — {compat.get('notes') or ''}"
            )
    if not any(
        (c.get("data_compatibility") or {}).get("database_changed")
        or (c.get("data_compatibility") or {}).get("migration_required")
        for c in changes
    ):
        lines.append("- 无破坏性数据库迁移预期；用户本地数据应可继续使用。")
    lines.append("")
    return "\n".join(lines)


def cmd_prepare_next_release(
    root: Path,
    bump: str,
    *,
    confirm: bool = False,
) -> int:
    unreleased = load_unreleased(root)
    if unreleased.get("status") != "frozen":
        print("error: unreleased.status must be frozen", file=sys.stderr)
        return 1
    if bump != "patch":
        print("error: only --bump patch is supported currently", file=sys.stderr)
        return 1
    if cmd_check(root, release_mode=True) != 0:
        return 1
    vm = root / "scripts" / "version_manager.py"
    vm_check = subprocess.run(
        [sys.executable, str(vm), "check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if vm_check.returncode != 0:
        print(vm_check.stdout)
        print(vm_check.stderr, file=sys.stderr)
        print("error: version_manager.py check failed", file=sys.stderr)
        return 1
    current = read_version(root)
    next_version = bump_patch(current)
    changes = [
        c
        for c in load_release_pool_changes(root)
        if c.get("include_in_next_release") and is_freeze_ready_status(c.get("status"))
    ]
    print(
        json.dumps(
            {
                "current_version": current,
                "next_version": next_version,
                "change_count": len(changes),
                "confirm": confirm,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not confirm:
        print("preview only — pass --confirm to bump VERSION and write release notes")
        return 0
    bump_proc = subprocess.run(
        [sys.executable, str(vm), "bump", "patch"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if bump_proc.returncode != 0:
        print(bump_proc.stdout)
        print(bump_proc.stderr, file=sys.stderr)
        return 1
    unreleased["target_version"] = next_version
    save_unreleased(root, unreleased)
    notes = generate_release_notes(root, next_version, changes)
    notes_path = root / "docs" / "releases" / f"{next_version}.md"
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(notes, encoding="utf-8", newline="\n")
    write_json(
        release_dir(root) / "generated" / f"release-{next_version}.json",
        {
            "version": next_version,
            "base_version": current,
            "changes": [c["id"] for c in changes],
            "generated_at": utc_now(),
        },
    )
    print(f"bumped VERSION to {next_version}")
    print(f"wrote {notes_path.relative_to(root).as_posix()}")
    print("did not build, upload, publish, or auto-upgrade")
    return 0


def cmd_release_preview(root: Path) -> int:
    print(json.dumps(preview_payload(root), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="StoryLens change registry")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detect)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show registry status (read-only)")
    sub.add_parser("release-preview", help="JSON preview for next release (read-only)")
    sub.add_parser("unregistered", help="List registered/unregistered/ignored commits")
    sub.add_parser("freeze", help="Freeze the unreleased change pool")

    check_p = sub.add_parser("check", help="Validate registry (daily mode by default)")
    check_p.add_argument(
        "--release",
        action="store_true",
        help="Strict formal release checks",
    )

    baseline_p = sub.add_parser("baseline", help="Show or verify release baseline")
    baseline_sub = baseline_p.add_subparsers(dest="baseline_command", required=True)
    baseline_sub.add_parser("show")
    baseline_sub.add_parser("verify")
    adopt_p = baseline_sub.add_parser(
        "adopt-legacy",
        help="Adopt unverified baseline as legacy_verified (preview unless --confirm)",
    )
    adopt_p.add_argument(
        "--confirm",
        action="store_true",
        help="Write legacy_verified status and audit fields",
    )

    register_p = sub.add_parser("register", help="Create a new change record")
    register_p.add_argument("--title", required=True)
    register_p.add_argument("--type", required=True, dest="change_type")
    register_p.add_argument("--user-summary", default="")

    attach_p = sub.add_parser("attach-commit", help="Attach a git commit to a change")
    attach_p.add_argument("change_id")
    attach_p.add_argument("commit")
    attach_p.add_argument("--primary", action="store_true", default=True)
    attach_p.add_argument("--not-primary", action="store_true")
    attach_p.add_argument("--multi-change-reason", default=None)

    mark_p = sub.add_parser("mark", help="Update change status with gate checks")
    mark_p.add_argument("change_id")
    mark_p.add_argument("status")

    update_p = sub.add_parser("update", help="Update change metadata")
    update_p.add_argument("change_id")
    update_p.add_argument("--status")
    update_p.add_argument("--user-summary")
    update_p.add_argument("--technical-summary")
    update_p.add_argument("--module", action="append", default=[])
    update_p.add_argument("--file", action="append", default=[])
    update_p.add_argument("--test", action="append", default=[])
    update_p.add_argument("--evidence", action="append", default=[])
    update_p.add_argument("--acceptance", action="append", default=[])
    update_p.add_argument("--database-changed", type=lambda s: s.lower() == "true")
    update_p.add_argument("--migration-required", type=lambda s: s.lower() == "true")
    update_p.add_argument("--user-data-compatible", type=lambda s: s.lower() == "true")
    update_p.add_argument("--compat-notes")
    update_p.add_argument("--requires-reanalysis", type=lambda s: s.lower() == "true")
    update_p.add_argument("--requires-restart", type=lambda s: s.lower() == "true")
    update_p.add_argument("--updater-impact", type=lambda s: s.lower() == "true")
    update_p.add_argument("--breaking-change", type=lambda s: s.lower() == "true")
    update_p.add_argument("--blocker-level", choices=["P0", "P1", "P2", "none"])
    update_p.add_argument(
        "--head-inclusion",
        choices=["INCLUDED", "EXISTS_NOT_INCLUDED", "NOT_FOUND"],
    )
    update_p.add_argument(
        "--include-in-next-release",
        type=lambda s: s.lower() == "true",
    )

    prep = sub.add_parser(
        "prepare-next-release",
        help="Freeze-gated bump + release notes (requires --confirm to modify)",
    )
    prep.add_argument("--bump", choices=["patch"], required=True)
    prep.add_argument(
        "--confirm",
        action="store_true",
        help="Actually bump VERSION and write release docs",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = (args.root or repo_root_from_here()).resolve()
    try:
        if args.command == "status":
            return cmd_status(root)
        if args.command == "baseline":
            if args.baseline_command == "show":
                return cmd_baseline_show(root)
            if args.baseline_command == "verify":
                return cmd_baseline_verify(root)
            if args.baseline_command == "adopt-legacy":
                return cmd_baseline_adopt_legacy(root, confirm=bool(args.confirm))
        if args.command == "register":
            return cmd_register(root, args.title, args.change_type, args.user_summary)
        if args.command == "attach-commit":
            primary = not args.not_primary
            return cmd_attach_commit(
                root,
                args.change_id,
                args.commit,
                primary=primary,
                multi_reason=args.multi_change_reason,
            )
        if args.command == "mark":
            return cmd_mark(root, args.change_id, args.status)
        if args.command == "update":
            return cmd_update(root, args.change_id, args)
        if args.command == "check":
            return cmd_check(root, release_mode=bool(args.release))
        if args.command == "unregistered":
            return cmd_unregistered(root)
        if args.command == "freeze":
            return cmd_freeze(root)
        if args.command == "prepare-next-release":
            return cmd_prepare_next_release(root, args.bump, confirm=bool(args.confirm))
        if args.command == "release-preview":
            return cmd_release_preview(root)
    except (OSError, ValueError, RuntimeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
