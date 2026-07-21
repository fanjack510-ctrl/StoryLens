#!/usr/bin/env python3
"""Real 《牛角坳》 Reader Journey V2 native E2E (no synthetic fixture scores).

Reads real paragraphs from an existing StoryLens DB (read-only), rematerializes
Scene/Beat with V2 consolidation rules into an isolated SQLite, estimates cloud
cost, then optionally runs one V2 native journey (model levels → program derive).

Never writes to %LOCALAPPDATA%\\StoryLens or the source development DB.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DB = REPO_ROOT / "data" / "storylens.db"
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "runtime" / "rj-v2-real-niujiaokao-verify"
FORBIDDEN_PROD = Path.home() / "AppData" / "Local" / "StoryLens"
NEEDLE = "周山禾年轻时就是一个打熬郎"
DISPLAY_BANNER = "V2真实正文分析"
SOURCE_MODE = "v2_native"


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assert_safe_db(path: Path) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(FORBIDDEN_PROD.resolve())
        raise SystemExit(f"Refusing formal StoryLens path: {resolved}")
    except ValueError:
        pass
    if "rj-v2-real-niujiaokao-verify" not in str(resolved).replace("\\", "/"):
        raise SystemExit(f"Unexpected verify DB path: {resolved}")


def _export_source_chapter(source_db: Path) -> dict:
    import sqlite3

    con = sqlite3.connect(f"file:{source_db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    row = con.execute(
        """
        SELECT p.book_id, p.chapter_id, b.title AS book_title, b.source_file_name,
               c.title AS chapter_title, c.display_title, c.word_count
        FROM paragraphs p
        JOIN books b ON b.id = p.book_id
        JOIN chapters c ON c.id = p.chapter_id
        WHERE p.raw_text LIKE ?
        LIMIT 1
        """,
        (f"%{NEEDLE}%",),
    ).fetchone()
    if row is None:
        con.close()
        raise SystemExit(
            "真实《牛角坳》正文未找到。请提供本地 TXT 路径后重试。\n"
            f"已搜索：{source_db}"
        )
    paras = con.execute(
        """
        SELECT paragraph_index, raw_text, normalized_text
        FROM paragraphs WHERE chapter_id=? ORDER BY paragraph_index
        """,
        (row["chapter_id"],),
    ).fetchall()
    scenes = con.execute(
        """
        SELECT ordinal, start_paragraph_id, end_paragraph_id, boundary_source, boundary_confidence
        FROM scenes WHERE chapter_id=? ORDER BY ordinal
        """,
        (row["chapter_id"],),
    ).fetchall()
    # Map old paragraph ids → index for boundary rematerialization
    id_to_index = {
        r["id"]: r["paragraph_index"]
        for r in con.execute(
            "SELECT id, paragraph_index FROM paragraphs WHERE chapter_id=?",
            (row["chapter_id"],),
        )
    }
    old_boundary_ends = []
    for s in scenes[:-1]:
        old_boundary_ends.append(id_to_index[s["end_paragraph_id"]])
    journey = con.execute(
        """
        SELECT id, scene_contract_version, scene_prompt_version, formula_version, total_scene_count
        FROM reader_journey_runs WHERE chapter_id=? ORDER BY id DESC LIMIT 1
        """,
        (row["chapter_id"],),
    ).fetchone()
    con.close()
    return {
        "source_db": str(source_db),
        "source_book_id": row["book_id"],
        "source_chapter_id": row["chapter_id"],
        "source_book_title": row["book_title"],
        "source_file_name": row["source_file_name"],
        "chapter_title": row["chapter_title"],
        "display_title": row["display_title"],
        "word_count": row["word_count"],
        "paragraphs": [
            {
                "paragraph_index": p["paragraph_index"],
                "raw_text": p["raw_text"],
                "normalized_text": p["normalized_text"] or p["raw_text"],
            }
            for p in paras
        ],
        "old_scene_count": len(scenes),
        "old_boundary_end_indexes": old_boundary_ends,
        "old_journey": dict(journey) if journey else None,
    }


def _role_guess(texts: list[str], ordinal: int, total: int) -> str:
    blob = "".join(texts)
    if ordinal == 1:
        return "setup"
    if "这分明是替" in blob or "哪里是镇" in blob:
        return "reveal"
    if "跪" in blob and "顶" in blob and "洞" in blob:
        return "climax"
    if "脚印" in blob or "蹄印" in blob:
        return "investigation"
    if "牛叫" in blob or "犬吠" in blob:
        return "escalation"
    if "老人" in blob:
        return "aftermath"
    if "扶正" in blob or "补了两凿" in blob:
        return "closed_end"
    if "温风" in blob or "钻了进去" in blob:
        return "escalation"
    if ordinal == total:
        return "closed_end"
    return "transition"


def setup_isolated_db(source: dict, data_dir: Path, *, reset: bool) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
    db_path = data_dir / "database" / "storylens.db"
    _assert_safe_db(db_path)
    if reset and db_path.exists():
        db_path.unlink()
    for sub in ("database", "logs", "uploads", "exports", "config"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)

    # Ensure pricing file exists for estimates
    pricing_src = REPO_ROOT / "config" / "cloud_pricing.default.json"
    pricing_dst = data_dir / "config" / "cloud_pricing.json"
    if pricing_src.is_file() and not pricing_dst.is_file():
        shutil.copy2(pricing_src, pricing_dst)

    db_url = f"sqlite:///{db_path.as_posix()}"
    os.environ["STORYLENS_DATABASE_URL"] = db_url
    os.environ["STORYLENS_DATA_DIR"] = str(data_dir.resolve())
    os.environ.setdefault("STORYLENS_APP_ENV", "development")
    os.environ.setdefault("STORYLENS_PROMPT_ROOT", str((REPO_ROOT / "packages" / "prompts").resolve()))
    os.environ.setdefault(
        "STORYLENS_READER_JOURNEY_FORMULA_PATH",
        str((REPO_ROOT / "config" / "reader_journey_formulas_v2.json").resolve()),
    )

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.models import (
        AnalysisArtifact,
        AnalysisEvidence,
        AnalysisRun,
        ApplicationSetting,
        Base,
        Book,
        BoundaryReviewSession,
        BoundaryRevision,
        Chapter,
        Paragraph,
        ProviderConfiguration,
        Scene,
    )
    from app.db.session import (
        migrate_phase_1b,
        migrate_phase_1c_a,
        migrate_phase_1c_a3,
        migrate_phase_1c_a4,
        migrate_phase_1c_a7,
        migrate_phase_1c_c1,
        migrate_phase_1d_c1_uat05,
        migrate_phase_2a1,
        migrate_phase_2b1,
        migrate_phase_2b2,
    )
    from app.services.scene_fragment_consolidation import consolidate_boundary_ids
    from app.services.scene_pipeline import scene_ranges

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    for migrate in (
        migrate_phase_1b,
        migrate_phase_2a1,
        migrate_phase_2b1,
        migrate_phase_2b2,
        migrate_phase_1c_a,
        migrate_phase_1c_a3,
        migrate_phase_1c_a4,
        migrate_phase_1c_a7,
        migrate_phase_1c_c1,
        migrate_phase_1d_c1_uat05,
    ):
        migrate(engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    paras_ns = [
        SimpleNamespace(
            id=f"TMP-P{p['paragraph_index']:04d}",
            paragraph_index=p["paragraph_index"],
            raw_text=p["raw_text"],
            normalized_text=p["normalized_text"],
        )
        for p in source["paragraphs"]
    ]
    # Rematerialize: map old end-indexes → temp ids, then consolidate.
    old_ends = source["old_boundary_end_indexes"]
    boundary_ids = [f"TMP-P{idx:04d}" for idx in old_ends]
    kept = consolidate_boundary_ids(paras_ns, boundary_ids, None)
    ranges = scene_ranges(paras_ns, kept, consolidate_short_fragments=False)

    with SessionLocal() as session:
        book = Book(
            title="牛角坳",
            source_file_name=source["source_file_name"],
            source_file_hash=_sha(NEEDLE + str(len(source["paragraphs"]))),
            fixture_name=None,
            fixture_version=None,
        )
        session.add(book)
        session.flush()
        chapter = Chapter(
            book_id=book.id,
            chapter_index=1,
            title=source["chapter_title"] or "第1章 牛角坳",
            display_title=source["display_title"] or "第1章｜牛角坳",
            section_type="chapter",
            word_count=int(source["word_count"] or 0),
        )
        session.add(chapter)
        session.flush()

        paragraphs: list[Paragraph] = []
        for item in source["paragraphs"]:
            pid = f"B{book.id:04d}-C0001-P{item['paragraph_index']:04d}"
            row = Paragraph(
                id=pid,
                book_id=book.id,
                chapter_id=chapter.id,
                paragraph_index=item["paragraph_index"],
                raw_text=item["raw_text"],
                normalized_text=item["normalized_text"],
                char_start=0,
                char_end=len(item["raw_text"]),
            )
            session.add(row)
            paragraphs.append(row)
            if chapter.start_paragraph_id is None:
                chapter.start_paragraph_id = pid
            chapter.end_paragraph_id = pid
        session.flush()

        # Rebuild ranges against real paragraph ids
        index_to_para = {p.paragraph_index: p for p in paragraphs}
        real_boundary_ids = []
        for tmp_id in kept:
            idx = int(tmp_id.split("P")[-1])
            real_boundary_ids.append(index_to_para[idx].id)
        real_ns = [
            SimpleNamespace(
                id=p.id,
                paragraph_index=p.paragraph_index,
                raw_text=p.raw_text,
                normalized_text=p.normalized_text,
            )
            for p in paragraphs
        ]
        real_ranges = scene_ranges(real_ns, real_boundary_ids, consolidate_short_fragments=False)

        run = AnalysisRun(
            task_type="scene_pipeline",
            provider="aliyun_qwen_plus",
            model="qwen3.7-plus",
            prompt_version="v3.5",
            schema_version="v1",
            input_hash=_sha("niujiaokao-v2-native"),
            status="succeeded",
            subject_type="chapter",
            subject_id=str(chapter.id),
            prompt_hash=_sha("niujiaokao"),
            progress_current=len(real_ranges),
            progress_total=len(real_ranges),
            analysis_mode="assisted_boundary_review",
            execution_mode="cloud",
            cloud_consent=True,
            cloud_consent_at=_utc(),
            sends_content_to_cloud=True,
            completed_at=_utc(),
        )
        session.add(run)
        session.flush()

        review = BoundaryReviewSession(
            book_id=book.id,
            chapter_id=chapter.id,
            analysis_run_id=run.id,
            prompt_version="v3.5",
            provider="aliyun_qwen_plus",
            model="qwen3.7-plus",
            status="confirmed",
            confirmed_by="v2-native-rematerialize",
            completed_at=_utc(),
        )
        session.add(review)
        session.flush()
        revision = BoundaryRevision(
            review_session_id=review.id,
            chapter_id=chapter.id,
            analysis_run_id=run.id,
            revision_number=1,
            final_boundaries_json=json.dumps(real_boundary_ids, ensure_ascii=False),
            confirmed_by="v2-native-rematerialize",
            confirmed_at=_utc(),
            coverage_rate=1.0,
        )
        session.add(revision)
        session.flush()

        scene_report = []
        scenes: list[Scene] = []
        for ordinal, (start, end) in enumerate(real_ranges, start=1):
            chunk = [
                p
                for p in paragraphs
                if start.paragraph_index <= p.paragraph_index <= end.paragraph_index
            ]
            texts = [p.normalized_text for p in chunk]
            role = _role_guess(texts, ordinal, len(real_ranges))
            # Extremely short single-sentence residues → beat candidate for report
            node_guess = "beat" if len(chunk) == 1 and len(texts[0]) <= 24 else "scene"
            scene = Scene(
                scene_key=f"B{book.id:04d}-C0001-R0001-S{ordinal:04d}",
                book_id=book.id,
                chapter_id=chapter.id,
                ordinal=ordinal,
                start_paragraph_id=start.id,
                end_paragraph_id=end.id,
                content_hash=_sha("|".join(p.id for p in chunk)),
                created_by_run_id=run.id,
                boundary_confidence=0.9,
                boundary_detected=True,
                boundary_revision_id=revision.id,
                boundary_source="model_accepted",
                boundary_reason_json=json.dumps(
                    ["v2_rematerialize_consolidation"], ensure_ascii=False
                ),
            )
            session.add(scene)
            session.flush()
            scenes.append(scene)
            # Minimal scene_analysis stub so RJ context is non-empty (not RJ scores).
            payload = {
                "scene_id": scene.scene_key,
                "entry_state": {
                    "summary": texts[0][:80],
                    "evidence_paragraph_ids": [chunk[0].id],
                },
                "goal": {
                    "summary": f"推进至场景{ordinal}",
                    "evidence_paragraph_ids": [chunk[0].id],
                },
                "obstacle": {"summary": "", "evidence_paragraph_ids": []},
                "key_actions": [
                    {
                        "summary": texts[min(1, len(texts) - 1)][:80],
                        "evidence_paragraph_ids": [chunk[min(1, len(chunk) - 1)].id],
                    }
                ],
                "turning_point": {"summary": "", "evidence_paragraph_ids": []},
                "outcome": {
                    "summary": texts[-1][:80],
                    "evidence_paragraph_ids": [chunk[-1].id],
                },
                "unresolved_question": {"summary": "", "evidence_paragraph_ids": []},
                "function_tags": ["事件推进"],
                "confidence": 0.85,
            }
            artifact = AnalysisArtifact(
                run_id=run.id,
                artifact_type="scene_analysis",
                subject_type="scene",
                subject_id=str(scene.id),
                schema_version="v1",
                prompt_version="v3.2",
                payload_json=json.dumps(payload, ensure_ascii=False),
                confidence=0.85,
                validation_status="valid",
            )
            session.add(artifact)
            session.flush()
            session.add(
                AnalysisEvidence(
                    artifact_id=artifact.id,
                    field_path="goal.evidence",
                    paragraph_id=chunk[0].id,
                    paragraph_hash=_sha(chunk[0].id),
                )
            )
            scene_report.append(
                {
                    "ordinal": ordinal,
                    "paragraph_range": [chunk[0].id, chunk[-1].id],
                    "paragraph_indexes": [chunk[0].paragraph_index, chunk[-1].paragraph_index],
                    "paragraph_count": len(chunk),
                    "char_count": sum(len(t) for t in texts),
                    "scene_role_guess": role,
                    "node_type_guess": node_guess,
                    "boundary_evidence": "v2_rematerialize_consolidation",
                    "confidence": 0.9,
                    "preview": texts[0][:48],
                }
            )

        # Provider + budget settings for cloud calls
        session.add(
            ProviderConfiguration(
                provider_name="aliyun_qwen_plus",
                display_name="阿里云百炼",
                region="cn-beijing",
                workspace_id="",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                plus_model="qwen3.7-plus",
                max_model="qwen3.7-max",
                flash_model="qwen3.6-flash",
                timeout_seconds=300,
                max_retries=3,
                enabled=True,
                disconnected=False,
                allow_auto_route=False,
                raw_logging_enabled=False,
                credential_reference="keyring:aliyun_qwen_plus",
            )
        )
        session.add(
            ApplicationSetting(
                key="cloud_budget",
                value_json=json.dumps(
                    {
                        "cloud_request_budget_enabled": True,
                        "cloud_max_input_tokens_per_request": 16000,
                        "cloud_max_output_tokens_per_request": 4000,
                        "cloud_max_requests_per_run": 50,
                        "cloud_daily_request_limit": 50,
                        "cloud_daily_token_limit": 200000,
                        "cloud_daily_estimated_cost_limit": 1.0,
                        "currency": "CNY",
                        "cloud_stop_on_unknown_pricing": True,
                        "cloud_confirm_each_paid_test": False,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        session.add(
            ApplicationSetting(key="cloud_enabled", value_json="true")
        )
        session.commit()

        txt_path = data_dir / "exports" / "niujiaokao.txt"
        txt_path.write_text(
            "\n".join(p["raw_text"] for p in source["paragraphs"]), encoding="utf-8"
        )

        return {
            "data_dir": str(data_dir.resolve()),
            "database_path": str(db_path.resolve()),
            "database_url": db_url,
            "txt_path": str(txt_path),
            "book_id": book.id,
            "book_title": book.title,
            "chapter_id": chapter.id,
            "chapter_title": chapter.title,
            "analysis_run_id": run.id,
            "scene_count": len(scenes),
            "beat_guess_count": sum(1 for s in scene_report if s["node_type_guess"] == "beat"),
            "old_scene_count": source["old_scene_count"],
            "reused_old_scene_rows": False,
            "scene_report": scene_report,
            "source_meta": {
                "source_db": source["source_db"],
                "source_book_id": source["source_book_id"],
                "source_chapter_id": source["source_chapter_id"],
                "old_journey": source["old_journey"],
            },
        }


def estimate_cost(setup: dict) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import Paragraph, Scene
    from app.services.staged_budget import (
        estimate_reader_journey_chapter_synthesis,
        estimate_reader_journey_scene_profiles,
    )

    pricing = Path(setup["data_dir"]) / "config" / "cloud_pricing.json"
    engine = create_engine(setup["database_url"], connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        scenes = list(
            session.scalars(select(Scene).where(Scene.chapter_id == setup["chapter_id"]).order_by(Scene.ordinal))
        )
        paragraphs = list(
            session.scalars(
                select(Paragraph)
                .where(Paragraph.chapter_id == setup["chapter_id"])
                .order_by(Paragraph.paragraph_index)
            )
        )
        s1 = estimate_reader_journey_scene_profiles(scenes, paragraphs, pricing_path=pricing)
        s2 = estimate_reader_journey_chapter_synthesis(scenes, pricing_path=pricing)
    return {
        "pricing_path": str(pricing),
        "scene_count": len(scenes),
        "stage1_reader_journey_scene": {
            "expected_requests": s1.expected_request_count,
            "worst_case_requests": s1.worst_case_request_count,
            "estimated_input_tokens": s1.estimated_input_tokens,
            "estimated_output_tokens": s1.estimated_output_tokens,
            "estimated_cost_cny": s1.estimated_cost,
            "worst_case_cost_cny": s1.worst_case_cost,
        },
        "stage2_chapter_synthesis": {
            "expected_requests": s2.expected_request_count,
            "worst_case_requests": s2.worst_case_request_count,
            "estimated_input_tokens": s2.estimated_input_tokens,
            "estimated_output_tokens": s2.estimated_output_tokens,
            "estimated_cost_cny": s2.estimated_cost,
            "worst_case_cost_cny": s2.worst_case_cost,
        },
        "total_expected_requests": s1.expected_request_count + s2.expected_request_count,
        "total_estimated_input_tokens": s1.estimated_input_tokens + s2.estimated_input_tokens,
        "total_estimated_output_tokens": s1.estimated_output_tokens + s2.estimated_output_tokens,
        "total_estimated_cost_cny": round(s1.estimated_cost + s2.estimated_cost, 6),
        "total_worst_case_cost_cny": round(s1.worst_case_cost + s2.worst_case_cost, 6),
        "daily_cost_limit_cny": 1.0,
        "within_daily_limit": (s1.estimated_cost + s2.estimated_cost) <= 1.0,
        "note": "V2 native: model outputs levels only; mapped_score/derive/diagnosis are local (no model fee).",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    args = parser.parse_args()
    if not args.source_db.is_file():
        raise SystemExit(f"Source DB missing: {args.source_db}")
    source = _export_source_chapter(args.source_db)
    print("=== SOURCE FOUND ===")
    print(json.dumps({k: source[k] for k in source if k != "paragraphs"}, ensure_ascii=False, indent=2))
    setup = setup_isolated_db(source, args.data_dir, reset=args.reset)
    print("=== REMATERIALIZE ===")
    print(json.dumps({k: setup[k] for k in setup if k != "scene_report"}, ensure_ascii=False, indent=2))
    print(json.dumps({"scenes": setup["scene_report"]}, ensure_ascii=False, indent=2))
    estimate = estimate_cost(setup)
    print("=== BUDGET ESTIMATE (before model call) ===")
    print(json.dumps(estimate, ensure_ascii=False, indent=2))
    manifest = {"setup": {k: setup[k] for k in setup if k != "scene_report"}, "scenes": setup["scene_report"], "estimate": estimate}
    out = Path(setup["data_dir"]) / "exports" / "setup_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("manifest:", out)
    if args.estimate_only:
        return
    if not estimate["within_daily_limit"]:
        raise SystemExit("Estimated cost exceeds daily limit; aborting without model call.")
    print("Estimate within daily limit. Use --execute-v2 in follow-up runner to call model once.")


if __name__ == "__main__":
    main()
