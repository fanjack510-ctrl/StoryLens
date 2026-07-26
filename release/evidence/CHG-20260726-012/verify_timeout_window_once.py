"""CHG-20260726-012: one Live call rebuilding Run #12 Window 3 from fingerprint.

Uses a temp copy of the formal DB (read snapshot paragraphs only).
Does not write the formal DB, does not create whole-book runs, does not materialize.
Forces max_auto_retries=0. Uses product default timeout_seconds and max_output_tokens.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = Path(__file__).resolve().parent
PRIVATE_SRC = Path(r"D:\Dstorylens-private-engine-wt-phase2br1-integration\src")
FINGERPRINT_PATH = EVIDENCE_DIR / "w3-fingerprint.json"

sys.path.insert(0, str(REPO / "apps" / "api"))
sys.path.insert(0, str(PRIVATE_SRC))

COST_GATE_CNY = 0.50
MODEL = "qwen3.7-plus"
PROVIDER = "aliyun_qwen_plus"
PRIOR_INPUT_TOKENS_EST = 5000


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _backup_formal_to_temp() -> Path:
    formal = Path(os.environ["LOCALAPPDATA"]) / "StoryLens" / "database" / "storylens.db"
    if not formal.is_file():
        raise SystemExit(f"formal DB missing: {formal}")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = Path(os.environ["TEMP"]) / f"storylens-chg012-{stamp}" / "storylens.db"
    dst.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(formal))
    try:
        out = sqlite3.connect(str(dst))
        try:
            src.backup(out)
            out.commit()
        finally:
            out.close()
    finally:
        src.close()
    return dst


def main() -> int:
    confirm = "--confirm" in sys.argv
    fp = json.loads(FINGERPRINT_PATH.read_text(encoding="utf-8"))
    window_db_id = int(fp["window_id"])
    window_index = int(fp["window_index"])
    run_id = int(fp["run_id"])
    expected_body = str(fp["body_sha256"])
    expected_prompt = str(fp["prompt_sha256"])
    expected_input_hash = str(fp["input_hash"])
    expected_paras = int(fp["paragraph_count"])
    expected_chars = int(fp["input_characters"])
    snap_ids = [int(x) for x in fp["snapshot_paragraph_ids"]]
    snapshot_id = int(fp["snapshot_id"])
    book_id = int(fp["book_id"])
    start_paragraph_id = str(fp["start_paragraph_id"])
    end_paragraph_id = str(fp["end_paragraph_id"])
    total_windows = 7

    from app.narrative_core.services.native_overview_live_transport import (
        AliyunNativeOverviewTransport,
    )
    from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
    from app.services.cloud_pricing import estimate_cost
    from app.services.credentials.service import get_credential_store

    if AliyunNativeOverviewTransport.timeout_seconds != 180:
        raise SystemExit(
            f"product timeout_seconds="
            f"{AliyunNativeOverviewTransport.timeout_seconds}, expected 180"
        )
    if AliyunNativeOverviewTransport.max_output_tokens != 8192:
        raise SystemExit(
            f"product max_output_tokens="
            f"{AliyunNativeOverviewTransport.max_output_tokens}, expected 8192"
        )

    probe = OpenAICompatibleProvider(
        name="probe",
        base_url="https://example.invalid/v1",
        api_key="x",
        default_model=MODEL,
        timeout_seconds=AliyunNativeOverviewTransport.timeout_seconds,
        max_context_tokens=128_000,
        enabled=True,
        cloud=True,
    )
    timeout = probe._timeout()
    read_timeout = float(timeout.read)
    connect_timeout = float(timeout.connect)

    key = get_credential_store().get(PROVIDER)
    key_configured = bool(key and str(key).strip())
    worst, _, _ = estimate_cost(MODEL, PRIOR_INPUT_TOKENS_EST, 8192)
    worst = float(worst or 0.0)

    print("=== CHG-20260726-012 single-window Live verify (preflight) ===")
    print(f"Window ID：{window_db_id}")
    print(f"Window Index：{window_index}")
    print(f"Run ID：{run_id}")
    print("Timeout Source：PRODUCT DEFAULT")
    print(f"Read Timeout：{int(read_timeout)}")
    print(f"Connect Timeout：{int(connect_timeout)}")
    print("Max Tokens Source：PRODUCT DEFAULT")
    print("Max Tokens：8192")
    print("Retry：0")
    print(f"Provider configured (key present)：{key_configured}")
    print(f"Estimated Maximum Cost：¥{worst:.4f}")
    print(f"Body SHA-256 (expected)：{expected_body}")
    print(f"Prompt SHA-256 (expected)：{expected_prompt}")
    print(f"Paragraph Count：{expected_paras}")
    print(f"Input Characters：{expected_chars}")

    if not confirm:
        print(
            "\nRefusing Live call without --confirm. "
            "Re-run after reviewing values above.",
            flush=True,
        )
        return 0

    if not key_configured:
        print("BLOCKED: Aliyun API key not configured", file=sys.stderr)
        return 2
    if worst > COST_GATE_CNY:
        print(f"BLOCKED: cost gate worst={worst} > {COST_GATE_CNY}", file=sys.stderr)
        return 3

    db_path = _backup_formal_to_temp()
    print(f"Temp DB copy：{db_path} (formal untouched)")

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import BookSnapshotChapter, BookSnapshotParagraph
    from app.narrative_core.contracts.whole_book_overview_v1 import (
        CONTRACT_VERSION,
        ChapterRef,
        OverviewRunRef,
        WholeBookOverviewWindowInputV1,
        WindowParagraph,
        WindowSlice,
    )
    from app.narrative_core.enums import WholeBookAnalysisMode, WindowStatus
    from app.narrative_core.services.native_overview_fixture_adapter import empty_prior_state
    from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
    from storylens_private_engine.contracts.whole_book_overview_v1 import (
        WholeBookOverviewWindowInputV1 as PrivateWindowInput,
    )
    from storylens_private_engine.modules.book_overview.window_prompt import (
        build_window_prompt,
    )
    from storylens_private_engine.modules.book_overview.window_parser import (
        parse_window_result_text,
    )
    from storylens_private_engine.modules.book_overview.errors import (
        NativeOverviewEngineError,
    )

    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session() as session:
        snaps = BookSnapshotServiceImpl(session)
        snap_paragraphs = list(
            session.scalars(
                select(BookSnapshotParagraph).where(BookSnapshotParagraph.id.in_(snap_ids))
            )
        )
        if len(snap_paragraphs) != len(snap_ids):
            print(
                f"snapshot paragraphs missing: got={len(snap_paragraphs)} "
                f"need={len(snap_ids)}",
                file=sys.stderr,
            )
            return 5
        order_map = {pid: i for i, pid in enumerate(snap_ids)}
        snap_paragraphs.sort(key=lambda p: order_map.get(int(p.id), 0))
        chapters = {
            c.id: c
            for c in session.scalars(
                select(BookSnapshotChapter).where(
                    BookSnapshotChapter.snapshot_id == snapshot_id
                )
            )
        }
        chapter_refs: list[ChapterRef] = []
        seen_chapters: set[int] = set()
        paras: list[WindowParagraph] = []
        body_parts: list[str] = []
        for p in snap_paragraphs:
            ch = chapters.get(p.snapshot_chapter_id)
            chapter_id = str(
                ch.source_chapter_id if ch and ch.source_chapter_id else p.snapshot_chapter_id
            )
            if p.snapshot_chapter_id not in seen_chapters:
                seen_chapters.add(p.snapshot_chapter_id)
                chapter_refs.append(
                    ChapterRef(
                        chapter_id=chapter_id,
                        chapter_index=int(ch.chapter_order if ch else 0),
                        title=str(ch.title if ch else ""),
                    )
                )
            text = snaps.get_snapshot_paragraph_text(p.id)
            body_parts.append(text)
            paras.append(
                WindowParagraph(
                    paragraph_id=p.stable_paragraph_id or p.source_paragraph_id or str(p.id),
                    chapter_id=chapter_id,
                    paragraph_index=int(p.paragraph_order),
                    text=text,
                )
            )

        body = "".join(body_parts)
        body_sha = _sha256_text(body)
        if len(paras) != expected_paras or len(body) != expected_chars:
            print(
                f"alignment mismatch paras={len(paras)} chars={len(body)}",
                file=sys.stderr,
            )
            return 5
        if body_sha != expected_body:
            print(f"BODY HASH MISMATCH got={body_sha}", file=sys.stderr)
            return 5

        window_input = WholeBookOverviewWindowInputV1(
            contract_version=CONTRACT_VERSION,
            run=OverviewRunRef(
                run_id=str(run_id),
                book_id=str(book_id),
                snapshot_id=str(snapshot_id),
                mode=WholeBookAnalysisMode.NATIVE,
                engine_version="native-overview-1",
                prompt_version="native-overview-window-v1",
            ),
            window=WindowSlice(
                window_id=f"w-{window_index}",
                window_index=window_index,
                total_windows=total_windows,
                start_paragraph_id=start_paragraph_id,
                end_paragraph_id=end_paragraph_id,
                chapter_refs=chapter_refs,
                paragraphs=paras,
                input_hash=expected_input_hash,
                status=WindowStatus.RUNNING,
            ),
            prior_state=empty_prior_state(),
        )
        private_input = PrivateWindowInput.model_validate(
            window_input.model_dump(mode="json")
        )
        prompt = build_window_prompt(private_input)
        prompt_sha = _sha256_text(prompt)
        if prompt_sha != expected_prompt:
            print(f"PROMPT HASH MISMATCH got={prompt_sha}", file=sys.stderr)
            return 5

        print(f"Hash check PASS body={body_sha[:12]}… prompt={prompt_sha[:12]}…")
        print("About to make ONE real Provider call (retry=0)…", flush=True)

        transport = AliyunNativeOverviewTransport(
            provider_name=PROVIDER,
            model=MODEL,
            max_auto_retries=0,
        )
        assert transport.timeout_seconds == 180
        assert transport.max_output_tokens == 8192

        t0 = time.perf_counter()
        try:
            response = transport.request(
                prompt,
                {
                    "stage": "analyze_window",
                    "engine_id": "private-native-overview-v1",
                    "model": MODEL,
                    "temperature": 0.2,
                },
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = time.perf_counter() - t0
            msg = str(exc)
            read_timeout_hit = "ReadTimeout" in msg or "PROVIDER_TIMEOUT" in msg
            summary = {
                "verification": "FAILED",
                "error_type": type(exc).__name__,
                "error_message": msg[:500],
                "read_timeout": bool(read_timeout_hit),
                "elapsed_seconds": round(elapsed, 3),
                "real_provider_calls": 1,
                "window_id": window_db_id,
                "body_sha256": body_sha,
                "prompt_sha256": prompt_sha,
                "timeout_source": "PRODUCT DEFAULT",
                "read_timeout_seconds": 180,
                "max_tokens_source": "PRODUCT DEFAULT",
                "max_output_tokens": 8192,
                "retry": 0,
                "database_writes": 0,
                "traceback": traceback.format_exc()[-2000:],
            }
            _write(
                EVIDENCE_DIR / "live-verification-summary.json",
                json.dumps(summary, ensure_ascii=False, indent=2),
            )
            print(
                json.dumps(
                    {k: v for k, v in summary.items() if k != "traceback"},
                    ensure_ascii=False,
                )
            )
            return 6

        elapsed = time.perf_counter() - t0
        text = str(response.get("text") or response.get("content") or "")
        finish_reason = response.get("finish_reason")
        input_tokens = int(response.get("input_tokens") or 0)
        output_tokens = int(response.get("output_tokens") or 0)
        http_status = response.get("http_status_code")
        actual_cost = float(response.get("estimated_cost") or 0.0)

        _write(EVIDENCE_DIR / "raw-response.txt", text)

        opens = text.count("{")
        closes = text.count("}")
        json_complete = (
            opens == closes and bool(text.strip()) and text.strip().endswith("}")
        )

        parser_status = "FAIL"
        schema_status = "FAIL"
        parsed_dump: dict | None = None
        try:
            parsed = parse_window_result_text(
                text,
                private_input,
                finish_reason=str(finish_reason) if finish_reason is not None else None,
            )
            parser_status = "PASS"
            schema_status = "PASS"
            parsed_dump = parsed.model_dump(mode="json")
        except NativeOverviewEngineError as exc:
            details = dict(exc.details or {})
            parsed_dump = {
                "error_code": exc.code,
                "message": exc.message,
                "details": details,
            }
            parser_status = "FAIL"
            if details.get("reason") == "schema_validation_failed":
                schema_status = "FAIL"
        except Exception as exc:  # noqa: BLE001
            parsed_dump = {"error": f"{type(exc).__name__}: {exc}"}

        _write(
            EVIDENCE_DIR / "parser-result.json",
            json.dumps(parsed_dump, ensure_ascii=False, indent=2),
        )

        passed = (
            int(http_status or 0) == 200
            and str(finish_reason) == "stop"
            and json_complete
            and parser_status == "PASS"
            and schema_status == "PASS"
            and actual_cost <= COST_GATE_CNY
        )
        summary = {
            "verification": "PASSED" if passed else "FAILED",
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "window_id": window_db_id,
            "window_index": window_index,
            "run_id": run_id,
            "paragraph_count": len(paras),
            "input_characters": len(body),
            "body_sha256": body_sha,
            "prompt_sha256": prompt_sha,
            "timeout_source": "PRODUCT DEFAULT",
            "read_timeout_seconds": 180,
            "connect_timeout_seconds": 30,
            "max_tokens_source": "PRODUCT DEFAULT",
            "max_output_tokens": 8192,
            "retry": 0,
            "real_provider_calls": 1,
            "http_status": http_status,
            "finish_reason": finish_reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "elapsed_seconds": round(elapsed, 3),
            "elapsed_gt_90s": elapsed > 90.0,
            "read_timeout": False,
            "json": "PASS" if json_complete else "FAIL",
            "parser": parser_status,
            "schema": schema_status,
            "actual_cost_cny": actual_cost,
            "database_writes": 0,
            "request_id": str(response.get("request_id") or ""),
        }
        _write(
            EVIDENCE_DIR / "live-verification-summary.json",
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
        _write(
            EVIDENCE_DIR / "request-metadata-redacted.json",
            json.dumps(
                {
                    "provider": PROVIDER,
                    "model": MODEL,
                    "timeout_seconds": 180,
                    "max_output_tokens": 8192,
                    "max_auto_retries": 0,
                    "api_key": "REDACTED",
                },
                indent=2,
            ),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if passed else 7


if __name__ == "__main__":
    raise SystemExit(main())
