"""Deterministic Reader Journey V2 re-finalize / repair (no Provider calls).

Default is dry-run. Explicit --apply writes derived fields only after optional backup.

Example:
  python scripts/repair_reader_journey_v2_refinalize.py --db PATH --run-id 1
  python scripts/repair_reader_journey_v2_refinalize.py --db PATH --run-id 1 --apply --backup
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_api_path() -> None:
    api_root = _repo_root() / "apps" / "api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))


def _extract_scores(deterministic_json: str | None) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(deterministic_json or "{}")
    except json.JSONDecodeError:
        return {}
    scores = payload.get("v2_scene_scores") or {}
    return scores if isinstance(scores, dict) else {}


def _diff_fits(
    before: dict[str, dict[str, Any]],
    after_profiles: list[Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile in after_profiles:
        key = str(profile.scene_ordinal)
        prev = before.get(key) or {}
        rows.append(
            {
                "scene_ordinal": profile.scene_ordinal,
                "scene_id": profile.scene_id,
                "scene_role": profile.scene_role,
                "pacing_speed_before": prev.get("pacing_speed"),
                "pacing_speed_after": float(
                    profile.pacing_speed.mapped_score
                    if profile.pacing_speed.mapped_score is not None
                    else profile.pacing_speed.level
                ),
                "pacing_fit_before": prev.get("pacing_fit"),
                "pacing_fit_after": profile.pacing_fit,
                "pacing_fit_status": profile.pacing_fit_status,
                "pacing_fit_reason_code": profile.pacing_fit_reason_code,
                "changed": prev.get("pacing_fit") != profile.pacing_fit,
            }
        )
    return rows


def repair_run(
    *,
    db_path: Path,
    run_id: int,
    apply: bool,
    backup: bool,
) -> dict[str, Any]:
    _ensure_api_path()
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import (
        Chapter,
        ChapterReaderJourneySummary,
        Paragraph,
        ReaderJourneyRun,
        Scene,
    )
    from app.services.reader_journey_v2_execution import _load_v2_profiles_from_artifacts
    from app.services.reader_journey_v2_finalize import finalize_v2_profiles
    from app.services.reader_journey_v2_mapping import mapped_or_zero
    from app.services.reader_journey_v2_persist import persist_finalized_v2_profiles

    if not db_path.is_file():
        raise FileNotFoundError(f"database not found: {db_path}")

    backup_path = None
    if apply and backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = db_path.with_name(f"{db_path.stem}.bak-{stamp}{db_path.suffix}")
        shutil.copy2(db_path, backup_path)

    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    report: dict[str, Any] = {
        "run_id": run_id,
        "db_path": str(db_path),
        "apply": apply,
        "backup_path": str(backup_path) if backup_path else None,
        "provider_calls": 0,
    }

    with SessionLocal() as session:
        journey = session.get(ReaderJourneyRun, run_id)
        if journey is None:
            raise ValueError(f"reader_journey_run id={run_id} not found")
        if (journey.scene_contract_version or "").startswith("1."):
            raise ValueError("refinalize supports V2 contract runs only")

        chapter = session.get(Chapter, journey.chapter_id)
        summary = session.scalar(
            select(ChapterReaderJourneySummary).where(
                ChapterReaderJourneySummary.reader_journey_run_id == journey.id
            )
        )
        before_scores = _extract_scores(
            summary.deterministic_statistics_json if summary else None
        )
        raw_profiles = _load_v2_profiles_from_artifacts(session, journey)
        if not raw_profiles:
            raise ValueError("no reader_journey_scene_profile_v2 artifacts found")

        derived, stats = finalize_v2_profiles(raw_profiles)
        # Fix mapped_or_zero display for speed after derive (profiles have mapped scores).
        for profile in derived:
            _ = mapped_or_zero(profile.pacing_speed)

        diffs = _diff_fits(before_scores, derived)
        # Correct pacing_speed_after using mapped_or_zero
        for row, profile in zip(diffs, sorted(derived, key=lambda p: p.scene_ordinal)):
            row["pacing_speed_after"] = mapped_or_zero(profile.pacing_speed)
            row["scene_role"] = profile.scene_role

        report.update(
            {
                "chapter_id": journey.chapter_id,
                "chapter_title": getattr(chapter, "title", None) if chapter else None,
                "scene_count": len(derived),
                "config_provenance": stats.get("config_provenance"),
                "fits_after": [item.pacing_fit for item in sorted(derived, key=lambda p: p.scene_ordinal)],
                "speeds_after": [
                    mapped_or_zero(item.pacing_speed)
                    for item in sorted(derived, key=lambda p: p.scene_ordinal)
                ],
                "roles_after": [
                    item.scene_role for item in sorted(derived, key=lambda p: p.scene_ordinal)
                ],
                "scene_diffs": diffs,
                "changed_scene_count": sum(1 for row in diffs if row["changed"]),
            }
        )

        if not apply:
            report["status"] = "dry_run"
            return report

        scenes = list(
            session.scalars(
                select(Scene)
                .where(Scene.chapter_id == journey.chapter_id)
                .order_by(Scene.ordinal)
            )
        )
        paragraphs = list(
            session.scalars(
                select(Paragraph)
                .where(Paragraph.chapter_id == journey.chapter_id)
                .order_by(Paragraph.paragraph_index)
            )
        )
        # Prefer artifact evidence; fall back to scene paragraph span via ids on profile.
        paragraph_ids_by_scene: dict[int, list[str]] = {}
        for profile in derived:
            pids = list(profile.evidence_paragraph_ids or [])
            if not pids and paragraphs:
                pids = [paragraphs[0].stable_id] if hasattr(paragraphs[0], "stable_id") else []
            paragraph_ids_by_scene[int(profile.scene_id)] = pids or ["P0001"]

        persist_finalized_v2_profiles(
            session,
            journey_run=journey,
            derived=derived,
            finalize_stats=stats,
            paragraph_ids_by_scene=paragraph_ids_by_scene,
        )
        # Keep existing phases; do not wipe narrative phase titles.
        details = {}
        try:
            details = json.loads(journey.failure_details_json or "{}")
        except json.JSONDecodeError:
            details = {}
        details["config_provenance"] = stats.get("config_provenance")
        details["refinalize"] = {
            "at": datetime.now(timezone.utc).isoformat(),
            "tool": "repair_reader_journey_v2_refinalize",
            "provider_calls": 0,
        }
        journey.failure_details_json = json.dumps(details, ensure_ascii=False)
        session.commit()
        report["status"] = "applied"
        report["scenes_touched"] = len(scenes)
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="SQLite database path")
    parser.add_argument("--run-id", type=int, required=True, help="reader_journey_runs.id")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist derived fields (default: dry-run only)",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Copy DB beside original before apply (recommended)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the report JSON",
    )
    args = parser.parse_args(argv)

    if args.apply and not args.backup:
        print(
            "Refusing --apply without --backup. Re-run with --backup, or use dry-run.",
            file=sys.stderr,
        )
        return 2

    report = repair_run(
        db_path=args.db.resolve(),
        run_id=args.run_id,
        apply=bool(args.apply),
        backup=bool(args.backup),
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
