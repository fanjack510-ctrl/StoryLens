import argparse
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisEvidence,
    AnalysisRun,
    Base,
    Book,
    Chapter,
    ModelInvocation,
    Paragraph,
    Scene,
)
from app.model_gateway.base import ModelRequest
from app.model_gateway.registry import get_model_gateway
from app.schemas.scene import SceneBoundaryResult
from app.services.prompt_service import load_prompt
from app.services.scene_pipeline import execute_scene_pipeline
from app.services.structured_output import extract_json_object


class MinimalJson(BaseModel):
    status: str


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--level", choices=("health", "minimal", "fixture", "pipeline"), required=True
    )
    parser.add_argument("--max-output-tokens", type=int, default=32)
    parser.add_argument(
        "--fixture", default="data/fixtures/local_model_calibration/no_boundary.txt"
    )
    parser.add_argument("--request-timeout", type=int, default=300)
    parser.add_argument("--cooldown-seconds", type=int, default=90)
    parser.add_argument("--skip-full-pipeline", action="store_true")
    parser.add_argument("--provider", default="local_llama")
    parser.add_argument("--prompt-version", default="v2")
    return parser.parse_args()


def fixture_payload(path: Path) -> tuple[str, list[dict[str, str]]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines[0], [
        {"id": f"B0001-C0001-P{index:04d}", "text": text} for index, text in enumerate(lines[1:], 1)
    ]


def seed(
    session, fixture: Path, provider_name: str, prompt_version: str
) -> tuple[Chapter, AnalysisRun]:
    title, items = fixture_payload(fixture)
    book = Book(
        title="原创安全校准", source_file_name=fixture.name, source_file_hash="safe-" + fixture.stem
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title=title,
        word_count=sum(len(item["text"]) for item in items),
    )
    session.add(chapter)
    session.flush()
    for index, item in enumerate(items, 1):
        identifier = f"B{book.id:04d}-C0001-P{index:04d}"
        session.add(
            Paragraph(
                id=identifier,
                book_id=book.id,
                chapter_id=chapter.id,
                paragraph_index=index,
                raw_text=item["text"],
                normalized_text=item["text"],
                char_start=0,
                char_end=len(item["text"]),
            )
        )
        chapter.start_paragraph_id = chapter.start_paragraph_id or identifier
        chapter.end_paragraph_id = identifier
    provider = get_model_gateway().get(provider_name)
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider=provider.name,
        model=provider.default_model,
        prompt_version=prompt_version,
        schema_version="v1",
        prompt_hash="safe-smoke",
        input_hash="safe-smoke",
        status="queued",
    )
    session.add(run)
    session.commit()
    return chapter, run


async def run() -> int:
    args = arguments()
    if os.getenv("STORYLENS_RUN_LOCAL_MODEL_TESTS") != "1":
        print("Set STORYLENS_RUN_LOCAL_MODEL_TESTS=1.")
        return 3
    gateway = get_model_gateway()
    provider = gateway.get(args.provider)
    health = await provider.health()
    print(
        json.dumps(
            {"level": "health", "status": health.status, "provider": health.provider_name},
            ensure_ascii=False,
        )
    )
    if health.status != "healthy":
        return 2
    if args.level == "health":
        return 0
    if args.max_output_tokens > 128:
        print("max-output-tokens cannot exceed 128 in safe calibration.")
        return 3

    if args.level == "minimal":
        started = time.perf_counter()
        response = await asyncio.wait_for(
            gateway.generate(
                args.provider,
                ModelRequest(
                    messages=[
                        {
                            "role": "system",
                            "content": "Return only the requested JSON. Do not explain.",
                        },
                        {"role": "user", "content": 'Return exactly {"status":"ok"}'},
                    ],
                    temperature=0,
                    max_tokens=min(args.max_output_tokens, 32),
                    response_schema=MinimalJson.model_json_schema(),
                    response_format_mode=provider.capabilities().structured_output_mode,
                    enable_thinking=False,
                ),
            ),
            timeout=args.request_timeout,
        )
        value = MinimalJson.model_validate_json(extract_json_object(response.text))
        print(
            json.dumps(
                {
                    "level": "minimal",
                    "status": value.status,
                    "model": response.model,
                    "http_status": response.http_status_code,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "raw_preview": response.text[:120],
                },
                ensure_ascii=False,
            )
        )
        return 0

    fixture = Path(args.fixture)
    title, paragraphs = fixture_payload(fixture)
    if args.level == "fixture":
        prompt = load_prompt("scene_boundary", args.prompt_version)
        snapshot = {"chapter_id": "B0001-C0001", "title": title, "paragraphs": paragraphs}
        request = ModelRequest(
            messages=[
                {"role": "system", "content": prompt.system},
                {
                    "role": "user",
                    "content": prompt.user_template.format(
                        input_json=json.dumps(snapshot, ensure_ascii=False)
                    ),
                },
            ],
            temperature=0,
            max_tokens=min(args.max_output_tokens, 128),
            response_schema=SceneBoundaryResult.model_json_schema(),
            response_format_mode=provider.capabilities().structured_output_mode,
            enable_thinking=False,
        )
        started = time.perf_counter()
        response = await asyncio.wait_for(
            gateway.generate(args.provider, request), timeout=args.request_timeout
        )
        result = SceneBoundaryResult.model_validate_json(extract_json_object(response.text))
        valid_ids = {item["id"] for item in paragraphs}
        if any(item.after_paragraph_id not in valid_ids for item in result.boundaries):
            raise ValueError("fixture returned invalid paragraph ID")
        expected_path = fixture.with_suffix(".expected.json")
        if expected_path.exists():
            expected = json.loads(expected_path.read_text(encoding="utf-8"))
            expected_ids = expected.get(
                "expected_internal_boundaries", expected.get("expected_boundaries", [])
            )
            actual_ids = [item.after_paragraph_id for item in result.boundaries]
            if actual_ids != expected_ids:
                raise ValueError(
                    f"fixture boundary mismatch: expected={expected_ids}, actual={actual_ids}"
                )
        print(
            json.dumps(
                {
                    "level": "fixture",
                    "fixture": fixture.name,
                    "boundaries": [item.after_paragraph_id for item in result.boundaries],
                    "overall_confidence": result.overall_confidence,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.skip_full_pipeline:
        return 0
    with tempfile.TemporaryDirectory(prefix="storylens-safe-") as directory:
        engine = create_engine(f"sqlite:///{Path(directory) / 'smoke.db'}")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with factory() as session:
            chapter, run_record = seed(session, fixture, args.provider, args.prompt_version)
            run_id = run_record.id
        await asyncio.wait_for(
            execute_scene_pipeline(factory, gateway, run_id), timeout=args.request_timeout
        )
        with factory() as session:
            run_record = session.get(AnalysisRun, run_id)
            scenes = list(
                session.scalars(
                    select(Scene).where(Scene.created_by_run_id == run_id).order_by(Scene.ordinal)
                )
            )
            invocations = list(
                session.scalars(select(ModelInvocation).where(ModelInvocation.run_id == run_id))
            )
            if run_record is None or run_record.status != "succeeded":
                raise RuntimeError(run_record.error_message if run_record else "missing run")
            print(
                json.dumps(
                    {
                        "level": "pipeline",
                        "status": run_record.status,
                        "scene_count": len(scenes),
                        "artifact_count": session.scalar(
                            select(func.count())
                            .select_from(AnalysisArtifact)
                            .where(AnalysisArtifact.run_id == run_id)
                        ),
                        "evidence_count": session.scalar(
                            select(func.count())
                            .select_from(AnalysisEvidence)
                            .join(AnalysisArtifact)
                            .where(AnalysisArtifact.run_id == run_id)
                        ),
                        "invocation_count": len(invocations),
                        "repair_count": sum(
                            item.invocation_kind == "repair" for item in invocations
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
