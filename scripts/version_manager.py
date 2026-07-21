#!/usr/bin/env python3
"""Centralized StoryLens version management.

Single source of truth: repository-root VERSION (plain SemVer, no \"v\" prefix).

Commands:
  show | check | sync | bump <part> | set <version> | release-info | release-guard
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

STALE_PRODUCT_VERSIONS = ("0.1.0", "0.1.1", "1.0.0-rc1")

# Paths relative to repo root that may legitimately mention historical versions.
HARDCODE_WHITELIST_PREFIXES = (
    "docs/",
    "audits/",
    "artifacts/",
    "apps/api/tests/",
    "apps/desktop/src/services/telemetry/telemetry.test.ts",
    "apps/desktop/e2e/",
    "packaging/updater/",
    "scripts/version_manager.py",
    "scripts/test_version_manager.py",
    "scripts/change_registry.py",
    "apps/api/tests/test_version_manager.py",
    "apps/api/tests/test_change_registry.py",
    "docs/versioning-and-release.md",
    "docs/change-registration-and-release.md",
)


@dataclass(frozen=True)
class VersionRef:
    label: str
    path: str
    reader: Callable[[Path], str]


@dataclass
class Mismatch:
    label: str
    path: str
    expected: str
    actual: str


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def parse_semver(raw: str) -> tuple[int, int, int, tuple[str, ...]]:
    text = raw.strip()
    match = SEMVER_RE.fullmatch(text)
    if not match:
        raise ValueError(f"invalid SemVer: {raw!r}")
    major, minor, patch = (int(match.group(i)) for i in range(1, 4))
    pre = tuple(match.group(4).split(".")) if match.group(4) else ()
    return major, minor, patch, pre


def format_core(version: tuple[int, int, int, tuple[str, ...]]) -> str:
    major, minor, patch, pre = version
    base = f"{major}.{minor}.{patch}"
    return f"{base}-{'.'.join(pre)}" if pre else base


def compare_semver(a: str, b: str) -> int:
    """Return -1 if a<b, 0 if equal, 1 if a>b (SemVer precedence, build ignored)."""
    pa = parse_semver(a)
    pb = parse_semver(b)
    if pa[:3] != pb[:3]:
        return (pa[:3] > pb[:3]) - (pa[:3] < pb[:3])
    # No prerelease > any prerelease
    if not pa[3] and not pb[3]:
        return 0
    if not pa[3]:
        return 1
    if not pb[3]:
        return -1
    for left, right in zip(pa[3], pb[3]):
        if left == right:
            continue
        left_num = left.isdigit()
        right_num = right.isdigit()
        if left_num and right_num:
            return (int(left) > int(right)) - (int(left) < int(right))
        if left_num:
            return -1
        if right_num:
            return 1
        return (left > right) - (left < right)
    return (len(pa[3]) > len(pb[3])) - (len(pa[3]) < len(pb[3]))


def bump_version(current: str, part: str) -> str:
    major, minor, patch, _pre = parse_semver(current)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump part: {part}")


def validate_version_string(raw: str) -> str:
    text = raw.strip()
    if not text:
        raise ValueError("empty version")
    if text.startswith("v") or text.startswith("V"):
        raise ValueError("version must not include a leading 'v'")
    parse_semver(text)
    return text


def read_version_file(root: Path) -> str:
    path = root / "VERSION"
    if not path.is_file():
        raise FileNotFoundError(f"VERSION file missing: {path}")
    lines = [ln.strip() for ln in read_text(path).splitlines() if ln.strip()]
    if len(lines) != 1:
        raise ValueError("VERSION must contain exactly one SemVer line")
    return validate_version_string(lines[0])


def _json_top_version(path: Path) -> str:
    data = json.loads(read_text(path))
    version = data.get("version")
    if not isinstance(version, str):
        raise ValueError(f"missing top-level version in {path}")
    return version


def _package_json_version(path: Path) -> str:
    return _json_top_version(path)


def _tauri_conf_version(path: Path) -> str:
    return _json_top_version(path)


def _toml_package_version(path: Path) -> str:
    in_package = False
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_package = stripped == "[package]" or stripped == "[project]"
            continue
        if in_package:
            match = re.match(r'^version\s*=\s*"([^"]+)"\s*$', stripped)
            if match:
                return match.group(1)
    raise ValueError(f"package/project version not found in {path}")


def _cargo_lock_storylens_version(path: Path) -> str:
    text = read_text(path)
    match = re.search(
        r'(?ms)^name = "storylens-desktop"\nversion = "([^"]+)"',
        text,
    )
    if not match:
        raise ValueError(f'storylens-desktop package not found in {path}')
    return match.group(1)


def _package_lock_root_version(path: Path) -> str:
    data = json.loads(read_text(path))
    top = data.get("version")
    packages = data.get("packages") or {}
    root_pkg = packages.get("") or {}
    root_ver = root_pkg.get("version")
    if not isinstance(top, str) or not isinstance(root_ver, str):
        raise ValueError(f"root versions missing in {path}")
    if top != root_ver:
        raise ValueError(f"package-lock root mismatch: top={top} packages['']={root_ver}")
    return top


def _fastapi_version(path: Path) -> str:
    text = read_text(path)
    # Prefer FastAPI(..., version=__version__) — report the imported constant source.
    if re.search(r'FastAPI\(\s*title="StoryLens API",\s*version=__version__', text):
        init_path = path.parent / "__init__.py"
        return _dunder_version(init_path)
    match = re.search(r'FastAPI\(\s*title="StoryLens API",\s*version="([^"]+)"', text)
    if not match:
        raise ValueError(f"FastAPI StoryLens version not found in {path}")
    return match.group(1)


def _dunder_version(path: Path) -> str:
    text = read_text(path)
    match = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        raise ValueError(f"__version__ not found in {path}")
    return match.group(1)


def _updater_template_version_token(path: Path) -> str:
    text = read_text(path)
    if '"version": "{{VERSION}}"' not in text and '"version":"{{VERSION}}"' not in text:
        raise ValueError("updater template must use {{VERSION}} placeholder")
    # Represent as the expected VERSION value for mismatch reporting via check hook.
    return "{{VERSION}}"


def _set_version_ps1_reads_manager(path: Path) -> str:
    text = read_text(path)
    if "version_manager.py" not in text:
        raise ValueError("set_version.ps1 must delegate to version_manager.py")
    return "delegates"


def _build_windows_release_gate(path: Path) -> str:
    text = read_text(path)
    if "version_manager.py" not in text or "check" not in text:
        raise ValueError("build_windows_release.ps1 must run version_manager.py check")
    return "gated"


def controlled_refs() -> list[VersionRef]:
    return [
        VersionRef("VERSION", "VERSION", lambda p: validate_version_string(read_text(p).strip())),
        VersionRef("tauri.conf.json", "apps/desktop/src-tauri/tauri.conf.json", _tauri_conf_version),
        VersionRef("Cargo.toml", "apps/desktop/src-tauri/Cargo.toml", _toml_package_version),
        VersionRef("Cargo.lock", "apps/desktop/src-tauri/Cargo.lock", _cargo_lock_storylens_version),
        VersionRef("package.json", "apps/desktop/package.json", _package_json_version),
        VersionRef("package-lock.json", "apps/desktop/package-lock.json", _package_lock_root_version),
        VersionRef("pyproject.toml", "pyproject.toml", _toml_package_version),
        VersionRef("FastAPI app", "apps/api/app/main.py", _fastapi_version),
        VersionRef("backend __version__", "apps/api/app/__init__.py", _dunder_version),
        VersionRef(
            "updater template",
            "packaging/updater/latest.json.template",
            _updater_template_version_token,
        ),
        VersionRef("set_version.ps1", "scripts/set_version.ps1", _set_version_ps1_reads_manager),
        VersionRef(
            "build_windows_release.ps1",
            "scripts/build_windows_release.ps1",
            _build_windows_release_gate,
        ),
    ]


def installer_name(version: str) -> str:
    return f"StoryLens_{version}_x64-setup.exe"


def release_info_payload(version: str) -> dict[str, str]:
    return {
        "current_version": version,
        "next_patch": bump_version(version, "patch"),
        "next_minor": bump_version(version, "minor"),
        "next_major": bump_version(version, "major"),
        "tag": f"v{version}",
        "installer_name": installer_name(version),
    }


def _replace_first_json_version(raw: str, new_version: str) -> str:
    updated, count = re.subn(
        r'"version"\s*:\s*"[^"]+"',
        f'"version": "{new_version}"',
        raw,
        count=1,
    )
    if count != 1:
        raise ValueError("failed to replace JSON version field")
    return updated


def _replace_toml_section_version(raw: str, section: str, new_version: str) -> str:
    lines = raw.splitlines(keepends=True)
    in_section = False
    done = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == section
        if not done and in_section and re.match(r"^version\s*=", stripped):
            nl = "\n" if line.endswith("\n") else ""
            # Preserve original newline style lightly: use \n; callers normalize.
            out.append(f'version = "{new_version}"{nl}')
            done = True
        else:
            out.append(line)
    if not done:
        raise ValueError(f"failed to replace {section} version")
    return "".join(out)


def _replace_package_lock_root(raw: str, new_version: str) -> str:
    rx = re.compile(r'"version"\s*:\s*"[^"]+"')
    updated, count = rx.subn(f'"version": "{new_version}"', raw, count=2)
    if count < 2:
        raise ValueError("failed to replace package-lock root versions")
    return updated


def _replace_cargo_lock_storylens(raw: str, new_version: str) -> str:
    updated, count = re.subn(
        r'(?ms)(^name = "storylens-desktop"\nversion = ")[^"]+(")',
        rf"\g<1>{new_version}\2",
        raw,
        count=1,
    )
    if count != 1:
        raise ValueError("failed to replace Cargo.lock storylens-desktop version")
    return updated


def _replace_dunder_version(raw: str, new_version: str) -> str:
    updated, count = re.subn(
        r'^__version__\s*=\s*"[^"]+"\s*$',
        f'__version__ = "{new_version}"',
        raw,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError("failed to replace __version__")
    return updated


def _ensure_fastapi_uses_dunder(raw: str) -> str:
    if re.search(r'FastAPI\(\s*title="StoryLens API",\s*version=__version__', raw):
        return raw
    updated, count = re.subn(
        r'FastAPI\(\s*title="StoryLens API",\s*version="[^"]+"',
        'FastAPI(title="StoryLens API", version=__version__',
        raw,
        count=1,
    )
    if count != 1:
        raise ValueError("failed to point FastAPI version at __version__")
    if "from app import __version__" not in updated and "import __version__" not in updated:
        # Insert import after other app imports if missing.
        if "from app." in updated:
            updated = updated.replace(
                "from app.",
                "from app import __version__\nfrom app.",
                1,
            )
        else:
            updated = "from app import __version__\n" + updated
    return updated


def sync_files(root: Path, version: str) -> list[str]:
    """Write VERSION into all managed files. Returns relative paths touched."""
    changed: list[str] = []

    def apply(rel: str, mutator: Callable[[str], str]) -> None:
        path = root / rel
        before = read_text(path)
        after = mutator(before)
        if after != before:
            write_text(path, after)
            changed.append(rel.replace("\\", "/"))

    version_path = root / "VERSION"
    current = version_path.read_text(encoding="utf-8") if version_path.exists() else ""
    desired = f"{version}\n"
    if current != desired:
        write_text(version_path, desired)
        changed.append("VERSION")

    apply("apps/desktop/package.json", lambda t: _replace_first_json_version(t, version))
    apply("apps/desktop/package-lock.json", lambda t: _replace_package_lock_root(t, version))
    apply(
        "apps/desktop/src-tauri/tauri.conf.json",
        lambda t: _replace_first_json_version(t, version),
    )
    apply(
        "apps/desktop/src-tauri/Cargo.toml",
        lambda t: _replace_toml_section_version(t, "[package]", version),
    )
    apply(
        "apps/desktop/src-tauri/Cargo.lock",
        lambda t: _replace_cargo_lock_storylens(t, version),
    )
    apply("pyproject.toml", lambda t: _replace_toml_section_version(t, "[project]", version))
    apply("apps/api/app/__init__.py", lambda t: _replace_dunder_version(t, version))
    apply("apps/api/app/main.py", _ensure_fastapi_uses_dunder)

    # Updater template keeps {{VERSION}}; ensure placeholder present.
    template = root / "packaging/updater/latest.json.template"
    if template.is_file():
        text = read_text(template)
        if "{{VERSION}}" not in text:
            raise ValueError("updater template missing {{VERSION}}")
    else:
        raise FileNotFoundError(template)

    return changed


def _is_whitelisted(rel: str) -> bool:
    norm = rel.replace("\\", "/")
    for prefix in HARDCODE_WHITELIST_PREFIXES:
        if norm == prefix.rstrip("/") or norm.startswith(prefix):
            return True
    # Unit / component tests may assert against banned literals.
    name = Path(norm).name
    if ".test." in name or ".spec." in name:
        return True
    return False


def scan_ui_hardcodes(root: Path, expected: str) -> list[Mismatch]:
    """Fail if UI product sources hardcode stale or mismatched product versions."""
    mismatches: list[Mismatch] = []
    src_root = root / "apps/desktop/src"
    if not src_root.is_dir():
        return mismatches
    banned = set(STALE_PRODUCT_VERSIONS)
    for path in src_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx", ".css", ".html"}:
            continue
        rel = path.relative_to(root).as_posix()
        if _is_whitelisted(rel):
            continue
        # Build-time injection module may reference the define symbol only.
        if rel in {
            "apps/desktop/src/lib/appVersion.ts",
            "apps/desktop/src/vite-env.d.ts",
        }:
            continue
        text = read_text(path)
        for stale in banned:
            if re.search(rf"(?<![0-9A-Za-z.-]){re.escape(stale)}(?![0-9A-Za-z.-])", text):
                mismatches.append(
                    Mismatch(
                        label="UI hardcode",
                        path=rel,
                        expected="(no product version literal)",
                        actual=stale,
                    )
                )
        # Ban hardcoded current version string in UI display components.
        if rel.startswith("apps/desktop/src/components/") or rel.startswith(
            "apps/desktop/src/pages/"
        ):
            if re.search(rf"(?<![0-9A-Za-z.-]){re.escape(expected)}(?![0-9A-Za-z.-])", text):
                mismatches.append(
                    Mismatch(
                        label="UI hardcode",
                        path=rel,
                        expected="dynamic app version",
                        actual=expected,
                    )
                )
    return mismatches


def check_versions(root: Path) -> list[Mismatch]:
    expected = read_version_file(root)
    mismatches: list[Mismatch] = []
    for ref in controlled_refs():
        path = root / ref.path
        if not path.is_file():
            mismatches.append(
                Mismatch(ref.label, ref.path, expected, "<missing file>")
            )
            continue
        try:
            actual = ref.reader(path)
        except Exception as exc:  # noqa: BLE001 — surface as check failure
            mismatches.append(Mismatch(ref.label, ref.path, expected, f"<error: {exc}>"))
            continue
        if ref.label in {"updater template", "set_version.ps1", "build_windows_release.ps1"}:
            # Structural checks already validated by reader; treat token as ok.
            continue
        if actual != expected:
            mismatches.append(Mismatch(ref.label, ref.path, expected, actual))
    mismatches.extend(scan_ui_hardcodes(root, expected))
    return mismatches


def print_mismatches(mismatches: Sequence[Mismatch]) -> None:
    print("Version check FAILED:")
    for item in mismatches:
        print(f"  - {item.label} ({item.path})")
        print(f"      expected: {item.expected}")
        print(f"      actual:   {item.actual}")


def cmd_show(root: Path) -> int:
    version = read_version_file(root)
    print(f"Current version: {version}")
    print("Managed files:")
    for ref in controlled_refs():
        path = root / ref.path
        if not path.is_file():
            print(f"  - {ref.label}: <missing>")
            continue
        try:
            actual = ref.reader(path)
        except Exception as exc:  # noqa: BLE001
            print(f"  - {ref.label}: <error: {exc}>")
            continue
        print(f"  - {ref.label}: {actual}")
    return 0


def cmd_check(root: Path) -> int:
    mismatches = check_versions(root)
    if mismatches:
        print_mismatches(mismatches)
        return 1
    print(f"Version check passed: {read_version_file(root)}")
    return 0


def cmd_sync(root: Path) -> int:
    version = read_version_file(root)
    changed = sync_files(root, version)
    if changed:
        print("Synced:")
        for rel in changed:
            print(f"  - {rel}")
    else:
        print("Already in sync.")
    return cmd_check(root)


def cmd_set(
    root: Path,
    new_version: str,
    *,
    allow_downgrade: bool = False,
    allow_same: bool = False,
) -> int:
    target = validate_version_string(new_version)
    current = read_version_file(root)
    if target == current and not allow_same:
        print(
            f"Refusing to set identical version {target} "
            "(use --allow-same only for recovery)."
        )
        return 1
    cmp = compare_semver(target, current)
    if cmp < 0 and not allow_downgrade:
        print(
            f"Refusing version downgrade {current} → {target} "
            "(pass --allow-downgrade only for exceptional recovery)."
        )
        return 1
    write_text(root / "VERSION", f"{target}\n")
    print(f"VERSION set to {target}")
    return cmd_sync(root)


def cmd_bump(root: Path, part: str) -> int:
    current = read_version_file(root)
    target = bump_version(current, part)
    write_text(root / "VERSION", f"{target}\n")
    print(f"Bumped {part}: {current} → {target}")
    return cmd_sync(root)


def cmd_release_info(root: Path) -> int:
    version = read_version_file(root)
    print(json.dumps(release_info_payload(version), indent=2, ensure_ascii=False))
    return 0


def _git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    # Do not .strip() — git porcelain lines may start with a leading space (e.g. " M path").
    return result.stdout.rstrip("\n")


def latest_release_tag(root: Path) -> str | None:
    out = _git_output(root, "tag", "-l", "v*.*.*", "--sort=-v:refname")
    if not out.strip():
        return None
    return out.splitlines()[0].strip() or None


def version_files_dirty(root: Path) -> list[str]:
    tracked = [
        "VERSION",
        "apps/desktop/package.json",
        "apps/desktop/package-lock.json",
        "apps/desktop/src-tauri/tauri.conf.json",
        "apps/desktop/src-tauri/Cargo.toml",
        "apps/desktop/src-tauri/Cargo.lock",
        "pyproject.toml",
        "apps/api/app/__init__.py",
        "apps/api/app/main.py",
        "packaging/updater/latest.json.template",
    ]
    dirty: list[str] = []
    status = _git_output(root, "status", "--porcelain", "--", *tracked)
    for line in status.splitlines():
        if not line.strip():
            continue
        # status --porcelain: XY PATH or XY ORIG -> PATH
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        dirty.append(path.replace("\\", "/"))
    return dirty


def git_tag_exists(root: Path, tag: str) -> bool:
    out = _git_output(root, "tag", "-l", tag)
    return any(line.strip() == tag for line in out.splitlines())


def git_is_ancestor(root: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def working_tree_dirty(root: Path) -> list[str]:
    status = _git_output(root, "status", "--porcelain")
    dirty: list[str] = []
    for line in status.splitlines():
        if line.strip():
            dirty.append(line[3:].strip() if len(line) >= 4 else line.strip())
    return dirty


# Feature commits that must be ancestors of HEAD before a formal release.
REQUIRED_RELEASE_COMMITS: tuple[tuple[str, str], ...] = (
    ("e1884c1", "short fragment scene boundary fix"),
    ("6f03010", "consent/nav/risk/phase metrics polish"),
    ("3a516f6", "Reader Journey UI + product subtitle (cherry-pick of 22750ec)"),
    ("8906cd6", "centralized version management"),
)


def _source_contains(root: Path, relative: str, needle: str) -> bool:
    path = root / relative
    if not path.is_file():
        return False
    return needle in read_text(path)


def cmd_release_guard(root: Path, artifacts_dir: Path | None = None) -> int:
    """Block formal release when version/tag/artifacts/updater policy are inconsistent."""
    errors: list[str] = []
    if cmd_check(root) != 0:
        errors.append("version check failed")
        # continue collecting more errors

    registry = root / "scripts" / "change_registry.py"
    if registry.is_file():
        reg = subprocess.run(
            [sys.executable, str(registry), "check", "--release"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if reg.returncode != 0:
            detail = (reg.stdout or reg.stderr or "").strip()
            errors.append(
                "change registry release check failed"
                + (f": {detail.splitlines()[0]}" if detail else "")
            )
    else:
        errors.append("missing scripts/change_registry.py")

    version = read_version_file(root)
    expected_tag = f"v{version}"

    # Exact tag for this VERSION must not already exist.
    if git_tag_exists(root, expected_tag):
        errors.append(f"Git tag already exists: {expected_tag}")

    tag = latest_release_tag(root)
    if tag:
        tag_version = tag[1:] if tag.startswith("v") else tag
        try:
            cmp = compare_semver(version, tag_version)
        except ValueError:
            cmp = 0
            errors.append(f"latest tag is not SemVer: {tag}")
        else:
            if cmp == 0:
                errors.append(
                    f"current VERSION {version} equals latest published tag {tag}"
                )
            elif cmp < 0:
                errors.append(
                    f"current VERSION {version} is behind latest tag {tag}"
                )

    dirty_versions = version_files_dirty(root)
    if dirty_versions:
        errors.append("uncommitted version files: " + ", ".join(dirty_versions))

    dirty_tree = working_tree_dirty(root)
    if dirty_tree:
        errors.append(
            "working tree not clean: " + ", ".join(dirty_tree[:12])
            + ("…" if len(dirty_tree) > 12 else "")
        )

    baseline = root / "docs" / "releases" / f"{version}.md"
    if not baseline.is_file():
        errors.append(
            f"missing release baseline: docs/releases/{version}.md"
        )
    else:
        body = read_text(baseline)
        if "Unreleased" not in body and "已发布" not in body and "Released" not in body:
            errors.append(
                f"release baseline docs/releases/{version}.md missing status marker"
            )

    for commit, label in REQUIRED_RELEASE_COMMITS:
        if not git_is_ancestor(root, commit):
            errors.append(f"required commit MISSING ({commit}: {label})")

    # Updater must not default to auto download / auto install.
    pref_path = "apps/desktop/src/services/updater/preferences.ts"
    if not _source_contains(root, pref_path, "automatic_download: false"):
        errors.append("updater preferences missing automatic_download: false default")
    if not _source_contains(root, pref_path, "automatic_install: false"):
        errors.append("updater preferences missing automatic_install: false default")
    svc = root / "apps/desktop/src/services/updaterService.ts"
    if svc.is_file():
        text = read_text(svc)
        if "await update.downloadAndInstall" in text or "update.downloadAndInstall()" in text:
            errors.append(
                "updaterService must not call update.downloadAndInstall()"
            )
        # checkForAppUpdate body must not relaunch
        if "export async function checkForAppUpdate" in text:
            chunk = text.split("export async function checkForAppUpdate", 1)[1]
            chunk = chunk.split("export async function startDownload", 1)[0]
            if "relaunch(" in chunk:
                errors.append("checkForAppUpdate must not relaunch the app")
    else:
        errors.append("missing updaterService.ts")

    channels = root / "apps/desktop/src/services/updater/channels.ts"
    if channels.is_file():
        ch = read_text(channels)
        if "STABLE_UPDATE_ENDPOINT" not in ch or "STAGING_UPDATE_ENDPOINT" not in ch:
            errors.append("staging/stable updater endpoints not defined")
        elif "latest/download/latest.json" not in ch:
            errors.append("stable updater endpoint missing")
        elif "/staging/" not in ch and "latest-staging" not in ch:
            errors.append("staging updater endpoint missing")
    else:
        errors.append("missing updater channels module")

    # tauri.conf default endpoint must be stable, not staging
    tauri_conf = root / "apps/desktop/src-tauri/tauri.conf.json"
    if tauri_conf.is_file():
        conf = json.loads(read_text(tauri_conf))
        endpoints = (
            conf.get("plugins", {}).get("updater", {}).get("endpoints") or []
        )
        if not endpoints:
            errors.append("tauri.conf.json updater endpoints empty")
        else:
            joined = " ".join(str(u) for u in endpoints)
            if "staging" in joined.lower():
                errors.append(
                    "tauri.conf.json default endpoints must not point at staging"
                )
            if "latest/download/latest.json" not in joined:
                errors.append(
                    "tauri.conf.json default endpoint should be stable latest.json"
                )
        install_mode = (
            conf.get("plugins", {})
            .get("updater", {})
            .get("windows", {})
            .get("installMode")
        )
        if install_mode == "quiet":
            errors.append(
                "updater windows.installMode=quiet is forbidden (silent install)"
            )

    if artifacts_dir is not None and artifacts_dir.is_dir():
        latest = artifacts_dir / "latest.json"
        if latest.is_file():
            try:
                data = json.loads(read_text(latest))
                art_ver = data.get("version")
                if art_ver != version:
                    errors.append(
                        f"latest.json version {art_ver!r} != VERSION {version}"
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"failed to read latest.json: {exc}")
        expected_installer = installer_name(version)
        installers = list(artifacts_dir.glob("StoryLens_*_x64-setup.exe"))
        for inst in installers:
            if version not in inst.name:
                errors.append(
                    f"installer name {inst.name} does not contain VERSION {version}"
                )
        # Prefer exact canonical name when present among candidates.
        if installers and not any(p.name == expected_installer for p in installers):
            # Soft note: Tauri may use slightly different stems; require version token only.
            pass
        for sig_or_bundle in artifacts_dir.rglob("*"):
            if not sig_or_bundle.is_file():
                continue
            name = sig_or_bundle.name.lower()
            if name.endswith(".sig") or "nsis.zip" in name or name.endswith(".nsis.zip"):
                if version not in sig_or_bundle.name and version not in str(
                    sig_or_bundle.relative_to(artifacts_dir)
                ):
                    # Only flag files that embed a different x.y.z product version.
                    found = re.search(
                        r"\b(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\b",
                        sig_or_bundle.name,
                    )
                    if found and found.group(1) != version:
                        errors.append(
                            f"updater artifact version mismatch: {sig_or_bundle.name}"
                        )

    if errors:
        print("Release guard FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"Release guard passed for {version}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="StoryLens version manager")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detect from script location)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show", help="Show current VERSION and managed file values")
    sub.add_parser("check", help="Verify all managed versions match VERSION")
    sub.add_parser("sync", help="Sync all managed files from VERSION, then check")
    sub.add_parser("release-info", help="Print next versions / tag / installer name JSON")

    bump = sub.add_parser("bump", help="Bump VERSION and sync")
    bump.add_argument("part", choices=("patch", "minor", "major"))

    set_p = sub.add_parser("set", help="Set VERSION explicitly and sync")
    set_p.add_argument("version")
    set_p.add_argument(
        "--allow-downgrade",
        action="store_true",
        help="Allow setting a lower version (recovery only)",
    )
    set_p.add_argument(
        "--allow-same",
        action="store_true",
        help="Allow re-setting the current version (recovery only)",
    )

    guard = sub.add_parser(
        "release-guard",
        help="Block release on tag collision, dirty version files, artifact mismatches",
    )
    guard.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Optional dist/release directory to validate",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = (args.root or repo_root_from_here()).resolve()
    try:
        if args.command == "show":
            return cmd_show(root)
        if args.command == "check":
            return cmd_check(root)
        if args.command == "sync":
            return cmd_sync(root)
        if args.command == "bump":
            return cmd_bump(root, args.part)
        if args.command == "set":
            return cmd_set(
                root,
                args.version,
                allow_downgrade=args.allow_downgrade,
                allow_same=args.allow_same,
            )
        if args.command == "release-info":
            return cmd_release_info(root)
        if args.command == "release-guard":
            artifacts = args.artifacts_dir
            if artifacts is not None and not artifacts.is_absolute():
                artifacts = root / artifacts
            return cmd_release_guard(root, artifacts)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
