"""CHG-085 readonly forensic of user WholeBookRun — NO WRITES."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB = Path(r"C:\Users\msi\AppData\Local\StoryLens\database\storylens.db")
OUT = Path(r"D:\Dstorylens-wt-v120-codex-takeover\release\evidence\whole-book\CHG-20260811-085")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    uri = f"file:{DB.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    books = [dict(r) for r in cur.execute("SELECT id, title FROM books ORDER BY id").fetchall()]
    runs = [
        dict(r)
        for r in cur.execute(
            """
            SELECT id, book_id, status, current_stage_code, provider_name, model_name,
                   engine_id, engine_version, contract_version, failure_code, failure_message_safe,
                   result_origin, created_at, started_at, completed_at, failed_at,
                   last_heartbeat_at, resume_count, snapshot_id
            FROM whole_book_runs
            ORDER BY id DESC
            LIMIT 12
            """
        ).fetchall()
    ]
    latest = runs[0] if runs else None
    run_id = int(latest["id"]) if latest else None

    progress = None
    if run_id is not None:
        # progress checkpoints
        prog_rows = [
            dict(r)
            for r in cur.execute(
                """
                SELECT id, stage_code, checkpoint_key, sequence_no, completed_unit_count,
                       checkpoint_payload_json, created_at
                FROM whole_book_checkpoints
                WHERE run_id=? AND stage_code LIKE '%progress%'
                ORDER BY id DESC LIMIT 5
                """,
                (run_id,),
            ).fetchall()
        ]
        # also any progress stage
        all_stages = [
            dict(r)
            for r in cur.execute(
                """
                SELECT stage_code, COUNT(*) AS n
                FROM whole_book_checkpoints
                WHERE run_id=?
                GROUP BY stage_code
                ORDER BY stage_code
                """,
                (run_id,),
            ).fetchall()
        ]
        intermediates = [
            dict(r)
            for r in cur.execute(
                """
                SELECT checkpoint_key, stage_code, length(checkpoint_payload_json) AS payload_len,
                       created_at, substr(checkpoint_payload_json, 1, 400) AS head
                FROM whole_book_checkpoints
                WHERE run_id=? AND (checkpoint_key LIKE 'window:%' OR checkpoint_key LIKE 'topic:%'
                                   OR stage_code LIKE '%intermediate%' OR stage_code LIKE '%progress%')
                ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        ]
        units = [
            dict(r)
            for r in cur.execute(
                """
                SELECT checkpoint_key, stage_code, length(checkpoint_payload_json) AS payload_len, created_at
                FROM whole_book_checkpoints
                WHERE run_id=? AND (stage_code LIKE '%unit%' OR checkpoint_key IN
                      ('overview_type','story','characters','suspense','pacing','assessment'))
                ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        ]
        usage = [
            dict(r)
            for r in cur.execute(
                """
                SELECT checkpoint_key, stage_code, checkpoint_payload_json, created_at
                FROM whole_book_checkpoints
                WHERE run_id=? AND stage_code='provider_usage'
                ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        ]
        # analysis run projection + model_invocations
        proj = cur.execute(
            """
            SELECT id, task_type, status, provider, model, progress_current, progress_total,
                   error_code, error_message, client_request_id, created_at
            FROM analysis_runs
            WHERE client_request_id=? OR (task_type='whole_book_v2' AND book_id=?)
            ORDER BY id DESC LIMIT 5
            """,
            (f"whole_book_v2:{run_id}", latest["book_id"] if latest else None),
        ).fetchall()
        projections = [dict(r) for r in proj]
        invs = []
        for p in projections:
            invs.extend(
                dict(r)
                for r in cur.execute(
                    """
                    SELECT id, run_id, task_type, provider_name, model_name, attempt_no, status,
                           input_tokens, output_tokens, total_tokens, finish_reason, error_code,
                           invocation_kind, request_hash, created_at,
                           substr(input_snapshot_json,1,300) AS snap_head
                    FROM model_invocations
                    WHERE run_id=?
                    ORDER BY id
                    """,
                    (p["id"],),
                ).fetchall()
            )
        # latest progress payload
        for r in reversed(intermediates):
            if "progress" in (r.get("stage_code") or "") or r.get("checkpoint_key") == "progress":
                try:
                    progress = json.loads(
                        cur.execute(
                            "SELECT checkpoint_payload_json FROM whole_book_checkpoints WHERE run_id=? AND checkpoint_key=? LIMIT 1",
                            (run_id, r["checkpoint_key"]),
                        ).fetchone()[0]
                    )
                except Exception:
                    pass
                break
        # parse window assets
        windows = []
        for r in intermediates:
            key = r.get("checkpoint_key") or ""
            if not key.startswith("window:"):
                continue
            raw = cur.execute(
                "SELECT checkpoint_payload_json FROM whole_book_checkpoints WHERE run_id=? AND checkpoint_key=?",
                (run_id, key),
            ).fetchone()
            payload = json.loads(raw[0]) if raw else {}
            windows.append(
                {
                    "checkpoint_key": key,
                    "window_id": payload.get("window_id"),
                    "start_chapter_index": payload.get("start_chapter_index"),
                    "end_chapter_index": payload.get("end_chapter_index"),
                    "origin": payload.get("origin"),
                    "provider": payload.get("provider"),
                    "model": payload.get("model"),
                    "input_tokens": payload.get("input_tokens"),
                    "output_tokens": payload.get("output_tokens"),
                    "evidence_count": len(payload.get("evidence") or []),
                    "events_count": len(payload.get("events") or []),
                    "payload_len": r.get("payload_len"),
                    "created_at": r.get("created_at"),
                }
            )

        report = {
            "books": books,
            "latest_runs": runs,
            "latest_failed": latest,
            "checkpoint_stage_counts": all_stages,
            "progress_rows": prog_rows,
            "progress_payload": progress,
            "windows": windows,
            "units": units,
            "usage_checkpoints": [
                {**u, "payload": json.loads(u["checkpoint_payload_json"])}
                for u in usage
            ],
            "projections": projections,
            "model_invocations": invs,
            "intermediate_keys": [r["checkpoint_key"] for r in intermediates],
        }
        (OUT / "forensic_latest_run.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print("LATEST_RUN_ID", run_id)
        print("STATUS", latest.get("status") if latest else None)
        print("STAGE", latest.get("current_stage_code") if latest else None)
        print("FAILURE", latest.get("failure_code") if latest else None)
        print("WINDOWS", len(windows))
        print("ORIGINS", sorted({w.get("origin") for w in windows}))
        print("USAGE_CKPTS", len(usage))
        print("INVOCATIONS", len(invs))
        print("STAGE_COUNTS", all_stages)
        if invs:
            tin = sum(int(i.get("input_tokens") or 0) for i in invs)
            tout = sum(int(i.get("output_tokens") or 0) for i in invs)
            print("TOKENS_IN", tin, "TOKENS_OUT", tout)
        print("WROTE", OUT / "forensic_latest_run.json")
    con.close()


if __name__ == "__main__":
    main()
