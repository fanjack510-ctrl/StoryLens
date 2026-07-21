#!/usr/bin/env python3
"""Execute one Reader Journey V2 native run against the isolated verify DB.

Thin harness: creates a V2 journey row then calls the official product service
`execute_reader_journey_v2` (same path as default product pipeline).

Does not duplicate finalize / diagnosis / persist logic.
Does not read synthetic fixture scores or diagnoses.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "runtime" / "rj-v2-real-niujiaokao-verify"


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _prepare_env(data_dir: Path) -> str:
    db_path = data_dir / "database" / "storylens.db"
    if not db_path.is_file():
        raise SystemExit(f"Missing verify DB. Run rematerialize first: {db_path}")
    db_url = f"sqlite:///{db_path.as_posix()}"
    os.environ["STORYLENS_DATABASE_URL"] = db_url
    os.environ["STORYLENS_DATA_DIR"] = str(data_dir.resolve())
    os.environ["STORYLENS_APP_ENV"] = "development"
    os.environ["STORYLENS_PROMPT_ROOT"] = str((REPO_ROOT / "packages" / "prompts").resolve())
    os.environ["STORYLENS_READER_JOURNEY_FORMULA_PATH"] = str(
        (REPO_ROOT / "config" / "reader_journey_formulas_v2.json").resolve()
    )
    # V2 level payloads are denser than v1 — force single-scene batches + higher output.
    os.environ["STORYLENS_READER_JOURNEY_BATCH_SIZE"] = "1"
    os.environ["STORYLENS_CLOUD_OUTPUT_READER_JOURNEY_SCENE"] = "4000"
    os.environ["STORYLENS_CLOUD_OUTPUT_READER_JOURNEY_SCHEMA_REPAIR"] = "4000"
    if str(REPO_ROOT / "apps" / "api") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
    return db_url


async def execute(data_dir: Path) -> dict:
    db_url = _prepare_env(data_dir)

    from app.model_gateway.registry import get_model_gateway

    get_model_gateway.cache_clear()

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import (
        AnalysisRun,
        Chapter,
        ChapterReaderJourneySummary,
        ReaderJourneyRun,
        Scene,
        SceneReaderJourneyProfile,
    )
    from app.services.credentials.service import get_credential_store
    from app.services.provider_runtime import bind_gateway_runtime
    from app.services.reader_journey_v2_execution import execute_reader_journey_v2
    from app.services.reader_journey_version import new_journey_version_fields

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    gateway = get_model_gateway()
    store = get_credential_store()

    with SessionLocal() as session:
        bind_gateway_runtime(gateway, session, store)
        provider = gateway.get("aliyun_qwen_plus")
        if not provider.api_key:
            raise SystemExit("Aliyun credential missing from keyring (aliyun_qwen_plus)")
        provider.enabled = True

        chapter = session.scalar(select(Chapter).order_by(Chapter.id).limit(1))
        analysis_run = session.scalar(select(AnalysisRun).order_by(AnalysisRun.id).limit(1))
        if chapter is None or analysis_run is None:
            raise SystemExit("Isolated verify DB missing chapter/analysis_run")
        scenes = list(
            session.scalars(
                select(Scene).where(Scene.chapter_id == chapter.id).order_by(Scene.ordinal)
            )
        )
        for old in session.scalars(
            select(ReaderJourneyRun).where(ReaderJourneyRun.chapter_id == chapter.id)
        ):
            if old.status != "succeeded":
                session.delete(old)
        session.commit()

        version_fields = new_journey_version_fields()
        journey = ReaderJourneyRun(
            analysis_run_id=analysis_run.id,
            book_id=chapter.book_id,
            chapter_id=chapter.id,
            status="queued",
            current_stage=None,
            provider_name="aliyun_qwen_plus",
            model_name=provider.default_model,
            scene_prompt_version=version_fields["scene_prompt_version"],
            chapter_prompt_version=version_fields["chapter_prompt_version"],
            scene_contract_version=version_fields["scene_contract_version"],
            chapter_contract_version=version_fields["chapter_contract_version"],
            formula_version=version_fields["formula_version"],
            genre=version_fields["genre"],
            planner_version="1.1",
            total_scene_count=len(scenes),
            completed_scene_count=0,
            remaining_scene_count=len(scenes),
            completed_scene_ids_json="[]",
            remaining_scene_ids_json=json.dumps([s.id for s in scenes]),
            started_at=_utc(),
            failure_details_json=version_fields["failure_details_json"],
            cloud_consent=True,
            client_request_id=f"v2-native-harness-{_utc().strftime('%Y%m%d%H%M%S')}",
        )
        session.add(journey)
        session.commit()
        journey_id = int(journey.id)
        analysis_run_id = int(analysis_run.id)

    print(f"harness calling official execute_reader_journey_v2 journey_id={journey_id}", flush=True)
    await execute_reader_journey_v2(SessionLocal, gateway, journey_id)

    with SessionLocal() as session:
        journey = session.get(ReaderJourneyRun, journey_id)
        profiles = list(
            session.scalars(
                select(SceneReaderJourneyProfile)
                .where(SceneReaderJourneyProfile.reader_journey_run_id == journey_id)
                .order_by(SceneReaderJourneyProfile.scene_ordinal)
            )
        )
        summary = session.scalar(
            select(ChapterReaderJourneySummary).where(
                ChapterReaderJourneySummary.reader_journey_run_id == journey_id
            )
        )
        stats = {}
        if summary and summary.deterministic_statistics_json:
            try:
                stats = json.loads(summary.deterministic_statistics_json)
            except json.JSONDecodeError:
                stats = {}
        export = {
            "journey_run_id": journey_id,
            "analysis_run_id": analysis_run_id,
            "status": journey.status if journey else None,
            "contract_version": journey.scene_contract_version if journey else None,
            "prompt_version": journey.scene_prompt_version if journey else None,
            "formula_version": journey.formula_version if journey else None,
            "source_mode": stats.get("source_mode"),
            "scores_origin": stats.get("scores_origin"),
            "diagnoses_origin": stats.get("diagnoses_origin"),
            "prewritten_scores": stats.get("prewritten_scores", False),
            "prewritten_diagnoses": stats.get("prewritten_diagnoses", False),
            "scene_count": len(profiles),
            "beat_count": sum(
                1
                for p in profiles
                if "beat" in (json.loads(p.payload_json or "{}").get("scene_value_summary") or "")
            ),
            "via_official_service": True,
            "average_reading_momentum": stats.get("average_reading_momentum"),
            "v2_scene_scores": stats.get("v2_scene_scores") or {},
            "scene_diagnoses": stats.get("scene_diagnoses") or [],
        }
        out = data_dir / "exports" / "v2_native_result.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "journey_run_id": journey_id,
            "analysis_run_id": analysis_run_id,
            "export_path": str(out),
            "status": journey.status if journey else None,
            "scene_count": len(profiles),
            "via_official_service": True,
            "average_reading_momentum": stats.get("average_reading_momentum"),
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    result = asyncio.run(execute(args.data_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
