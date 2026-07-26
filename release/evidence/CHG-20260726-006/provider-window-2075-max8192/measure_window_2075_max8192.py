"""DIAGNOSTIC ONLY: one Live call for Run #11 window 2075 with max_output_tokens=8192.

Does not modify product defaults, formal DB, or run materialization.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
EVIDENCE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "apps" / "api"))

WINDOW_DB_ID = 2075
RUN_ID = 11
EXPECTED_PARA_COUNT = 40
EXPECTED_BODY_CHARS = 576
MAX_OUTPUT_TOKENS = 8192
COST_GATE_CNY = 0.50
MODEL = "qwen3.7-plus"
PROVIDER = "aliyun_qwen_plus"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _cost_worst_case(input_tokens_est: int, max_out: int) -> float:
    from app.services.cloud_pricing import estimate_cost

    cost, _, _ = estimate_cost(MODEL, input_tokens_est, max_out)
    if cost is None:
        raise RuntimeError("pricing unavailable for cost gate")
    return float(cost)


def main() -> int:
    db_url = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not db_url:
        print("usage: measure_window_2075_max8192.py <sqlite-db-path>", file=sys.stderr)
        return 2

    db_path = Path(db_url)
    if not db_path.is_file():
        print(f"DB missing: {db_path}", file=sys.stderr)
        return 2

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    # --- rebuild formal window input (same path as NativeOverviewService._build_window_input)
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import (
        AnalysisRun,
        BookSnapshotChapter,
        BookSnapshotParagraph,
        WholeBookRunWindow,
    )
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
    from app.narrative_core.services.native_overview_live_transport import (
        AliyunNativeOverviewTransport,
    )
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
        run = session.get(AnalysisRun, RUN_ID)
        window = session.get(WholeBookRunWindow, WINDOW_DB_ID)
        if run is None or window is None:
            print("Run 11 or window 2075 missing", file=sys.stderr)
            return 3
        if int(window.run_id) != RUN_ID or int(window.window_index) != 0:
            print(
                f"window mismatch run={window.run_id} idx={window.window_index}",
                file=sys.stderr,
            )
            return 3

        from sqlalchemy import func

        total_windows = int(
            session.scalar(
                select(func.count())
                .select_from(WholeBookRunWindow)
                .where(WholeBookRunWindow.run_id == RUN_ID)
            )
            or 0
        )

        checkpoint = json.loads(window.checkpoint_json or "{}")
        snap_ids = [int(x) for x in (checkpoint.get("snapshot_paragraph_ids") or [])]
        snaps = BookSnapshotServiceImpl(session)
        snap_paragraphs = list(
            session.scalars(
                select(BookSnapshotParagraph).where(BookSnapshotParagraph.id.in_(snap_ids))
            )
        )
        order_map = {pid: i for i, pid in enumerate(snap_ids)}
        snap_paragraphs.sort(key=lambda p: order_map.get(int(p.id), 0))
        chapters = {
            c.id: c
            for c in session.scalars(
                select(BookSnapshotChapter).where(
                    BookSnapshotChapter.snapshot_id == int(run.book_snapshot_id)
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
        if len(paras) != EXPECTED_PARA_COUNT or len(body) != EXPECTED_BODY_CHARS:
            summary = {
                "measurement": "BLOCKED",
                "reason": "input_alignment_mismatch",
                "paragraph_count": len(paras),
                "input_characters": len(body),
                "expected_paragraph_count": EXPECTED_PARA_COUNT,
                "expected_input_characters": EXPECTED_BODY_CHARS,
                "body_sha256": body_sha,
                "real_provider_calls": 0,
            }
            _write(
                EVIDENCE_DIR / "verification-summary.json",
                json.dumps(summary, ensure_ascii=False, indent=2),
            )
            print(json.dumps(summary, ensure_ascii=False))
            return 4

        window_input = WholeBookOverviewWindowInputV1(
            contract_version=CONTRACT_VERSION,
            run=OverviewRunRef(
                run_id=str(run.id),
                book_id=str(run.book_id),
                snapshot_id=str(run.book_snapshot_id),
                mode=WholeBookAnalysisMode.NATIVE,
                engine_version="native-overview-1",
                prompt_version="native-overview-window-v1",
            ),
            window=WindowSlice(
                window_id=f"w-{window.window_index}",
                window_index=int(window.window_index),
                total_windows=max(1, total_windows),
                start_paragraph_id=window.start_paragraph_id,
                end_paragraph_id=window.end_paragraph_id,
                chapter_refs=chapter_refs,
                paragraphs=paras,
                input_hash=window.input_hash,
                status=WindowStatus.RUNNING,
            ),
            prior_state=empty_prior_state(),
        )

        private_input = PrivateWindowInput.model_validate(
            window_input.model_dump(mode="json")
        )
        prompt = build_window_prompt(private_input)
        prompt_sha = _sha256_text(prompt)
        payload_sha = _sha256_text(
            json.dumps(window_input.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        )

        # Cost gate: use prior measured input tokens (5192) + max out 8192
        prior_input_tokens = 5192
        worst = _cost_worst_case(prior_input_tokens, MAX_OUTPUT_TOKENS)
        if worst > COST_GATE_CNY:
            summary = {
                "measurement": "BLOCKED",
                "reason": "cost_gate",
                "worst_case_cost_cny": worst,
                "gate_cny": COST_GATE_CNY,
                "real_provider_calls": 0,
            }
            _write(
                EVIDENCE_DIR / "verification-summary.json",
                json.dumps(summary, ensure_ascii=False, indent=2),
            )
            print(json.dumps(summary, ensure_ascii=False))
            return 5

        print(
            f"COST_GATE_OK worst_case_cny={worst:.6f} < {COST_GATE_CNY}; "
            f"about to make ONE real Provider call (max_output_tokens={MAX_OUTPUT_TOKENS})",
            flush=True,
        )

        transport = AliyunNativeOverviewTransport(
            provider_name=PROVIDER,
            model=MODEL,
            timeout_seconds=90,
            max_output_tokens=MAX_OUTPUT_TOKENS,  # instance override only — not product file
            max_auto_retries=0,
            temperature=0.2,
        )

        t0 = time.perf_counter()
        try:
            response = transport.request(
                prompt,
                {
                    "stage": "analyze_window",
                    "engine_id": "private-native-overview-v1",
                    "model": MODEL,
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                    "temperature": 0.2,
                },
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = time.perf_counter() - t0
            summary = {
                "measurement": "COMPLETED",
                "result_class": "D_PROVIDER_EXCEPTION",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
                "elapsed_seconds": round(elapsed, 3),
                "real_provider_calls": 1,
                "repair_attempted": False,
                "window_id": WINDOW_DB_ID,
                "body_sha256": body_sha,
                "prompt_sha256": prompt_sha,
                "traceback": traceback.format_exc()[-2000:],
            }
            _write(
                EVIDENCE_DIR / "verification-summary.json",
                json.dumps(summary, ensure_ascii=False, indent=2),
            )
            print(json.dumps({k: v for k, v in summary.items() if k != "traceback"}, ensure_ascii=False))
            return 6

        elapsed = time.perf_counter() - t0
        text = str(response.get("text") or response.get("content") or "")
        finish_reason = response.get("finish_reason")
        input_tokens = int(response.get("input_tokens") or 0)
        output_tokens = int(response.get("output_tokens") or 0)
        http_status = response.get("http_status_code")
        request_id = str(response.get("request_id") or "")
        actual_cost = float(response.get("estimated_cost") or 0.0)

        _write(EVIDENCE_DIR / "raw-response.txt", text)
        _write(EVIDENCE_DIR / "normalized-response.txt", text)

        opens = text.count("{")
        closes = text.count("}")
        json_complete = opens == closes and bool(text.strip()) and text.strip().endswith("}")

        parser_status = "FAIL"
        schema_status = "FAIL"
        parser_internal = None
        parser_reason = None
        parser_message = None
        parsed_dump = None

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
            parser_status = "FAIL"
            details = dict(exc.details or {})
            parser_internal = details.get("internal_class")
            parser_reason = details.get("reason")
            parser_message = exc.message
            if parser_reason == "schema_validation_failed":
                schema_status = "FAIL"
                # extraction may have succeeded; still schema fail
            parsed_dump = {
                "error_code": exc.code,
                "message": exc.message,
                "details": details,
            }
        except Exception as exc:  # noqa: BLE001
            parser_status = "FAIL"
            parser_message = f"{type(exc).__name__}: {exc}"
            parsed_dump = {"error": parser_message}

        _write(
            EVIDENCE_DIR / "parser-result.json",
            json.dumps(
                {
                    "parser": parser_status,
                    "schema": schema_status,
                    "internal_class": parser_internal,
                    "reason": parser_reason,
                    "message": parser_message,
                    "parsed": parsed_dump,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        _write(
            EVIDENCE_DIR / "request-metadata-redacted.json",
            json.dumps(
                {
                    "provider": PROVIDER,
                    "model": MODEL,
                    "window_id": WINDOW_DB_ID,
                    "window_index": 0,
                    "input_characters": len(body),
                    "paragraph_count": len(paras),
                    "body_sha256": body_sha,
                    "window_payload_sha256": payload_sha,
                    "prompt_hash": prompt_sha,
                    "prompt_sha256": prompt_sha,
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "enable_thinking": False,
                    "timeout": 90,
                    "retry": 0,
                    "stream": False,
                    "api_key_present": True,
                    "api_key_value": "REDACTED",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        # Result classes
        if finish_reason == "length" or output_tokens >= MAX_OUTPUT_TOKENS or not json_complete:
            measure_label = "INSUFFICIENT"
            sufficient = False
            result_class = "B_STILL_TRUNCATED"
        elif parser_status == "PASS" and schema_status == "PASS":
            measure_label = "SUFFICIENT FOR THIS WINDOW"
            sufficient = True
            result_class = "A_COMPLETE_SUCCESS"
        elif json_complete and schema_status == "FAIL":
            measure_label = "OUTPUT LIMIT SUFFICIENT / SCHEMA FAILED"
            sufficient = True  # limit ok
            result_class = "C_SCHEMA_FAILED"
        else:
            measure_label = "UNKNOWN"
            sufficient = None
            result_class = "OTHER"

        summary = {
            "measurement": "COMPLETED",
            "result_class": result_class,
            "measurement_8192": measure_label,
            "sufficient_8192": sufficient,
            "source_modified": False,
            "database_writes": 0,
            "window_id": WINDOW_DB_ID,
            "window_index": 0,
            "paragraph_count": len(paras),
            "input_characters": len(body),
            "body_sha256": body_sha,
            "window_payload_sha256": payload_sha,
            "prompt_sha256": prompt_sha,
            "provider": PROVIDER,
            "model": MODEL,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "real_provider_calls": 1,
            "http_status": http_status,
            "provider_response_id": request_id,
            "finish_reason": finish_reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "requested_output_limit": MAX_OUTPUT_TOKENS,
            "raw_response_length": len(text),
            "opening_brace_count": opens,
            "closing_brace_count": closes,
            "json_complete": json_complete,
            "parser": parser_status,
            "schema": schema_status,
            "parser_internal_class": parser_internal,
            "repair_attempted": False,
            "actual_cost_cny": actual_cost,
            "worst_case_estimate_cny": worst,
            "elapsed_seconds": round(elapsed, 3),
            "observed_required_output_range": (
                f">{MAX_OUTPUT_TOKENS}"
                if not json_complete or finish_reason == "length"
                else f"~{output_tokens} (complete under {MAX_OUTPUT_TOKENS})"
            ),
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }
        _write(
            EVIDENCE_DIR / "verification-summary.json",
            json.dumps(summary, ensure_ascii=False, indent=2),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
