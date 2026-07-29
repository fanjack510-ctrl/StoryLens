#!/usr/bin/env python3
"""Restore MG running/interrupted fixtures after API startup orphan recovery."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
DEFAULT_DB = (
    Path(os.environ.get("TEMP", "/tmp"))
    / "storylens-mg-chg011-workflow-consistency"
    / "database"
    / "storylens-mg-chg011.db"
)


def main() -> int:
    db_path = Path(os.environ.get("MG_DB_PATH", str(DEFAULT_DB)))
    manifest = json.loads((EVIDENCE / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8"))
    db_url = f"sqlite:///{db_path.as_posix()}"
    os.environ["STORYLENS_DATABASE_URL"] = db_url
    os.environ.setdefault("STORYLENS_APP_ENV", "development")
    sys.path.insert(0, str(REPO / "apps" / "api"))

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import ReaderJourneyRun, Scene, SceneReaderJourneyProfile

    now = datetime.now(timezone.utc)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    b = manifest["fixtures"]["B_interrupted_1_of_6"]
    d = manifest["fixtures"]["running_2_of_6"]

    with Session() as session:
        journey_b = session.get(ReaderJourneyRun, b["journey_run_id"])
        if journey_b is not None:
            scenes_b = list(
                session.scalars(
                    select(Scene)
                    .where(Scene.chapter_id == b["chapter_id"])
                    .order_by(Scene.ordinal)
                )
            )[:6]
            if scenes_b:
                exists = session.scalar(
                    select(SceneReaderJourneyProfile.id).where(
                        SceneReaderJourneyProfile.reader_journey_run_id == journey_b.id,
                        SceneReaderJourneyProfile.scene_id == scenes_b[0].id,
                    )
                )
                if not exists:
                    session.add(
                        SceneReaderJourneyProfile(
                            reader_journey_run_id=journey_b.id,
                            scene_id=scenes_b[0].id,
                            scene_ordinal=1,
                            scene_value_summary="MG interrupted profile S1",
                            dominant_emotion="tension",
                            engagement_score=50,
                            confidence=0.8,
                            validation_status="valid",
                            payload_json="{}",
                        )
                    )
                journey_b.status = "scene_profiles_partial"
                journey_b.completed_scene_count = 1
                journey_b.remaining_scene_count = 5
                journey_b.completed_scene_ids_json = json.dumps([scenes_b[0].id])
                journey_b.remaining_scene_ids_json = json.dumps([s.id for s in scenes_b[1:]])
                journey_b.root_error_code = "JOURNEY_INTERRUPTED"
                journey_b.retryable = True
                journey_b.updated_at = now

        journey_d = session.get(ReaderJourneyRun, d["journey_run_id"])
        if journey_d is not None:
            scenes_d = list(
                session.scalars(
                    select(Scene)
                    .where(Scene.chapter_id == d["chapter_id"])
                    .order_by(Scene.ordinal)
                )
            )[:6]
            for scene in scenes_d[:2]:
                exists = session.scalar(
                    select(SceneReaderJourneyProfile.id).where(
                        SceneReaderJourneyProfile.reader_journey_run_id == journey_d.id,
                        SceneReaderJourneyProfile.scene_id == scene.id,
                    )
                )
                if not exists:
                    session.add(
                        SceneReaderJourneyProfile(
                            reader_journey_run_id=journey_d.id,
                            scene_id=scene.id,
                            scene_ordinal=scene.ordinal,
                            scene_value_summary=f"MG running profile S{scene.ordinal}",
                            dominant_emotion="tension",
                            engagement_score=60,
                            confidence=0.8,
                            validation_status="valid",
                            payload_json="{}",
                        )
                    )
            journey_d.status = "scene_profiles_running"
            journey_d.root_error_code = None
            journey_d.root_error_message = None
            journey_d.retryable = False
            journey_d.completed_scene_count = 2
            journey_d.remaining_scene_count = 4
            journey_d.completed_scene_ids_json = json.dumps([s.id for s in scenes_d[:2]])
            journey_d.remaining_scene_ids_json = json.dumps([s.id for s in scenes_d[2:]])
            journey_d.completed_at = None
            journey_d.updated_at = now
        session.commit()
    print("MG fixtures refreshed after API boot recovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
