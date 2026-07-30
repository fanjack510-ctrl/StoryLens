#!/usr/bin/env python3
"""Append a fresh legal Recoverable Interrupted fixture to the isolated MG DB.

Does NOT wipe existing fixtures or rewrite Journey Run 2 / 5.
Does NOT touch formal AppData storylens.db.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
EVIDENCE = Path(__file__).resolve().parent
CHG_EVIDENCE = EVIDENCE.parent
DEFAULT_DATA = Path(os.environ.get("TEMP", "/tmp")) / "storylens-mg-chg015-rc4-failure"
DEFAULT_DB = DEFAULT_DATA / "database" / "storylens-mg-chg015.db"
FORMAL_DB = Path.home() / "AppData" / "Local" / "StoryLens" / "database" / "storylens.db"
API_PORT = 18049
FE_PORT = 1428


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _assert_isolated_db(db_path: Path) -> None:
    resolved = db_path.resolve()
    if resolved == FORMAL_DB.resolve():
        raise SystemExit(f"Refusing formal AppData DB: {resolved}")
    local = Path.home() / "AppData" / "Local" / "StoryLens"
    try:
        resolved.relative_to(local.resolve())
        raise SystemExit(f"Refusing write under formal StoryLens tree: {resolved}")
    except ValueError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    db_path = args.db_path
    _assert_isolated_db(db_path)
    if not db_path.exists():
        raise SystemExit(f"DB missing: {db_path}")

    os.environ["STORYLENS_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["STORYLENS_REAL_PROVIDER_ENABLED"] = "0"
    os.environ["STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE"] = "1"

    sys.path.insert(0, str(REPO / "apps" / "api"))
    # Import seed helpers from sibling module
    import importlib.util

    seed_path = CHG_EVIDENCE / "seed_mg_chg015_fixtures.py"
    spec = importlib.util.spec_from_file_location("seed_mg_chg015_fixtures", seed_path)
    assert spec and spec.loader
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Book, ReaderJourneyRun
    from app.core import config as config_mod

    config_mod.get_settings.cache_clear()
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False}
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    fe = f"http://127.0.0.1:{FE_PORT}"
    with Session() as session:
        book = session.scalar(select(Book).order_by(Book.id.asc()))
        if book is None:
            raise SystemExit("No book in isolated DB")

        # Preserve existing JR2/JR5; append new chapter fixture.
        fx = seed._seed_fixture_c(session, book)
        # Retitle to mark C2
        from app.db.models import Chapter

        chapter = session.get(Chapter, fx["chapter_id"])
        if chapter is not None:
            chapter.title = "可恢复中断 C2（合法 Fixture）"
            chapter.chapter_index = max(chapter.chapter_index or 0, 6)
        journey = session.get(ReaderJourneyRun, fx["journey_run_id"])
        if journey is not None:
            journey.client_request_id = f"chg015-recoverable-c2-{fx['chapter_id']}"
            # Ensure result_status stays current and not superseded.
            journey.result_status = "current"
        session.commit()

        # Guard: no second journey on this analysis run
        siblings = list(
            session.scalars(
                select(ReaderJourneyRun).where(
                    ReaderJourneyRun.analysis_run_id == fx["run_id"]
                )
            )
        )
        if len(siblings) != 1:
            raise SystemExit(f"C2 must have exactly one journey, got {len(siblings)}")

        url = (
            f"{fe}/books/{book.id}?chapter={fx['chapter_id']}"
            f"&analysisRun={fx['run_id']}&journeyRun={fx['journey_run_id']}"
            f"&view=progress"
        )
        payload = {
            "change_id": "CHG-20260730-015",
            "label": "C2_legal_recoverable",
            "database": str(db_path),
            "fixture": fx,
            "url": url,
            "notes": "Appended without rewriting Journey 2/5; product fixes must keep single current run.",
        }
        out = EVIDENCE / "C2_LEGAL_RECOVERABLE_FIXTURE.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
