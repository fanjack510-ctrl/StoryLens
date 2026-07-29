#!/usr/bin/env python3
"""Compare tsc error sets: base HEAD vs current HEAD for CHG-011 scope."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
DESKTOP = REPO / "apps" / "desktop"
BASE = "e59da1238eb2c509b4a05d7a401a6b5a1b2002ee"

CHG011_PATH_HINTS = (
    "chapterAnalysisPresentation",
    "chapterPrimaryAction",
    "BookRoutePage",
    "WorkspaceViewSwitcher",
    "SceneBoundaryReviewPanel.tsx",
    "TasksPage.tsx",
    "HookPayoffTimeline",
    "chapterHookSimplification",
    "JourneyModeSwitcher",
)


def _run_tsc(cwd: Path) -> list[str]:
    cmd = "npx tsc -p tsconfig.app.json --noEmit --pretty false"
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        shell=True,
    )
    lines = []
    for stream in (proc.stdout, proc.stderr):
        for line in (stream or "").splitlines():
            if re.search(r"error TS\d+", line):
                lines.append(line.strip())
    # Normalize absolute/relative path noise
    normalized = []
    for line in lines:
        line = line.replace("\\", "/")
        # Drop worktree absolute prefixes if present
        if "apps/desktop/" in line:
            line = "src/" + line.split("apps/desktop/src/")[-1] if "apps/desktop/src/" in line else line
        if line.startswith("src/") or "/src/" in line:
            if not line.startswith("src/"):
                line = "src/" + line.split("/src/")[-1]
        normalized.append(line)
    return sorted(set(normalized))


def _chg011_errors(errors: list[str]) -> list[str]:
    out = []
    for err in errors:
        if any(h in err for h in CHG011_PATH_HINTS):
            out.append(err)
    return out


def main() -> int:
    # Current HEAD errors
    final_errors = _run_tsc(DESKTOP)

    # Base HEAD: stash worktree files via temporary git worktree if needed.
    # Prefer comparing against recorded baseline file when present, else compute via detached checkout in temp.
    base_file = EVIDENCE / "TYPECHECK_BASE_ERRORS.json"
    if base_file.exists() and os.environ.get("FORCE_RECOMPUTE_BASE") != "1":
        base_errors = json.loads(base_file.read_text(encoding="utf-8"))["errors"]
    else:
        # Compute base by checking out base in a temp worktree
        import tempfile

        with tempfile.TemporaryDirectory(prefix="sl-tsc-base-") as tmp:
            tmp_path = Path(tmp)
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(tmp_path), BASE],
                cwd=REPO,
                check=True,
                capture_output=True,
                text=True,
            )
            try:
                # ensure node_modules via symlink/junction to current desktop node_modules
                base_desktop = tmp_path / "apps" / "desktop"
                nm = DESKTOP / "node_modules"
                link = base_desktop / "node_modules"
                if nm.exists() and not link.exists():
                    if os.name == "nt":
                        subprocess.run(
                            ["cmd", "/c", "mklink", "/J", str(link), str(nm)],
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                    else:
                        link.symlink_to(nm, target_is_directory=True)
                base_errors = _run_tsc(base_desktop)
            finally:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(tmp_path)],
                    cwd=REPO,
                    capture_output=True,
                    text=True,
                )
        base_file.write_text(
            json.dumps({"head": BASE, "errors": base_errors}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

    base_set = set(base_errors)
    final_set = set(final_errors)
    new_errors = sorted(final_set - base_set)
    resolved = sorted(base_set - final_set)
    chg_errors = _chg011_errors(final_errors)

    report = {
        "base_head": BASE,
        "final_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "base_error_count": len(base_errors),
        "final_error_count": len(final_errors),
        "new_error_count": len(new_errors),
        "resolved_error_count": len(resolved),
        "chg011_file_error_count": len(chg_errors),
        "new_errors": new_errors,
        "chg011_file_errors": chg_errors,
        "pass_new_zero": len(new_errors) == 0,
        "pass_chg011_zero": len(chg_errors) == 0,
    }
    (EVIDENCE / "TYPECHECK_BASELINE_COMPARISON.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    md = [
        "# TYPECHECK_BASELINE_COMPARISON — CHG-20260729-011",
        "",
        f"- Base HEAD: `{report['base_head']}`",
        f"- Final HEAD: `{report['final_head']}`",
        f"- Base errors: **{report['base_error_count']}**",
        f"- Final errors: **{report['final_error_count']}**",
        f"- NEW TYPECHECK ERRORS: **{report['new_error_count']}**",
        f"- CHG-011 FILE TYPECHECK ERRORS: **{report['chg011_file_error_count']}**",
        "",
        "## Verdict",
        "",
        f"- NEW TYPECHECK ERRORS == 0: {'PASS' if report['pass_new_zero'] else 'FAIL'}",
        f"- CHG-011 FILE TYPECHECK ERRORS == 0: {'PASS' if report['pass_chg011_zero'] else 'FAIL'}",
        "",
        "Full-project typecheck may still FAIL due to pre-existing debt outside CHG-011.",
        "",
    ]
    if new_errors:
        md.append("## New errors")
        md.extend(f"- `{e}`" for e in new_errors)
        md.append("")
    if chg_errors:
        md.append("## CHG-011 file errors")
        md.extend(f"- `{e}`" for e in chg_errors)
        md.append("")
    (EVIDENCE / "TYPECHECK_BASELINE_COMPARISON.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass_new_zero"] and report["pass_chg011_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
