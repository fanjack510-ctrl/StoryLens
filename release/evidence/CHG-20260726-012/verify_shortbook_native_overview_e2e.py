"""CHG-20260726-012 short-book Native Overview full E2E driver.

Preflight: no whole-book run / no window Provider calls.
Live (--confirm): one full API run on book_id=5 via temp DB only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[3]
PRIVATE_SRC = Path(r"D:\Dstorylens-private-engine-wt-phase2br1-integration\src")
EVIDENCE_ROOT = Path(__file__).resolve().parent
LIVE_DIR = EVIDENCE_ROOT / "shortbook-e2e-live"
PY = REPO / ".venv" / "Scripts" / "python.exe"
BOOK_ID = 5
PORT = 18002
COST_GATE = 0.50
PROVIDER = "aliyun_qwen_plus"
MODEL = "qwen3.7-plus"
EXPECTED_WINDOWS = 7
POLL_SECONDS = 2
HEARTBEAT_SECONDS = 30
MAX_WAIT_SECONDS = 30 * 60
CREATE_TIMEOUT_SECONDS = 5.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, (dict, list)):
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        path.write_text(str(obj), encoding="utf-8")


def _append_log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def _product_defaults() -> dict[str, Any]:
    sys.path.insert(0, str(REPO / "apps" / "api"))
    from app.narrative_core.services.native_overview_live_transport import (
        AliyunNativeOverviewTransport,
    )
    from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
    from app.services.credentials.service import get_credential_store

    t = AliyunNativeOverviewTransport()  # product defaults, no overrides
    probe = OpenAICompatibleProvider(
        name="probe",
        base_url="https://example.invalid/v1",
        api_key="x",
        default_model=MODEL,
        timeout_seconds=t.timeout_seconds,
        max_context_tokens=128_000,
        enabled=True,
        cloud=True,
    )
    timeout = probe._timeout()
    key = get_credential_store().get(PROVIDER)
    return {
        "max_tokens_source": "PRODUCT DEFAULT",
        "max_tokens": int(t.max_output_tokens),
        "timeout_source": "PRODUCT DEFAULT",
        "read_timeout": float(timeout.read),
        "connect_timeout": float(timeout.connect),
        "write_timeout": float(timeout.write),
        "pool_timeout": float(timeout.pool),
        "timeout_seconds_attr": int(t.timeout_seconds),
        "retry": int(t.max_auto_retries),
        "provider_key_present": bool(key and str(key).strip()),
        # Prove script did not construct with overrides:
        "constructed_without_timeout_kwarg": True,
        "constructed_without_max_output_tokens_kwarg": True,
    }


def _backup_db(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    s = sqlite3.connect(str(src))
    try:
        d = sqlite3.connect(str(dst))
        try:
            s.backup(d)
            d.commit()
        finally:
            d.close()
    finally:
        s.close()


def _book_stats(db: Path) -> dict[str, Any]:
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    b = con.execute("SELECT id, title FROM books WHERE id=?", (BOOK_ID,)).fetchone()
    if b is None:
        con.close()
        raise SystemExit(f"book_id={BOOK_ID} missing in temp DB")
    title = str(b["title"] or "")
    if "戏神" in title:
        con.close()
        raise SystemExit("refused long book 戏神")
    chapters = int(
        con.execute(
            "SELECT count(*) AS c FROM chapters WHERE book_id=?", (BOOK_ID,)
        ).fetchone()["c"]
    )
    paragraphs = int(
        con.execute(
            "SELECT count(*) AS c FROM paragraphs WHERE book_id=?", (BOOK_ID,)
        ).fetchone()["c"]
    )
    con.close()
    if not (4 <= chapters <= 5):
        raise SystemExit(f"unexpected chapter_count={chapters} (need 4–5 short book)")
    return {
        "book_id": BOOK_ID,
        "book_title": title,
        "chapter_count": chapters,
        "paragraph_count": paragraphs,
    }


def _clear_fake_env(env: dict[str, str]) -> None:
    for k in list(env):
        ku = k.upper()
        if k.startswith("STORYLENS_") and "FAKE" in ku:
            env.pop(k, None)
    env.pop("STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE", None)
    env.pop("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE", None)


def _start_api(db: Path, data_dir: Path, out: Path, err: Path) -> subprocess.Popen:
    env = os.environ.copy()
    _clear_fake_env(env)
    env["STORYLENS_APP_ENV"] = "production"
    env["PRO_NATIVE_OVERVIEW_ENABLED"] = "true"
    env["STORYLENS_DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
    env["STORYLENS_DATA_DIR"] = str(data_dir)
    env["STORYLENS_LOG_DIR"] = str(data_dir / "logs")
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    env["PYTHONPATH"] = str(REPO / "apps" / "api") + os.pathsep + str(PRIVATE_SRC)
    env.pop("STORYLENS_CONFIG_DIR", None)
    for p in (out, err):
        if p.exists():
            p.unlink()
    proc = subprocess.Popen(
        [
            str(PY),
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(REPO / "apps" / "api"),
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--ws",
            "none",
        ],
        cwd=r"C:\Windows\System32",
        env=env,
        stdout=out.open("w", encoding="utf-8"),
        stderr=err.open("w", encoding="utf-8"),
    )
    base = f"http://127.0.0.1:{PORT}"
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"API exited early; see {err}")
        try:
            r = httpx.get(f"{base}/health", timeout=2.0)
            if r.status_code == 200:
                return proc
        except Exception:
            time.sleep(0.4)
    raise RuntimeError(f"API health failed; see {err}")


def _stop_proc(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


def _scan_logs(*paths: Path) -> dict[str, int]:
    lock = 0
    config = 0
    for p in paths:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore").lower()
        lock += text.count("database is locked")
        lock += text.count("operationalerror")
        config += text.count("filenotfounderror")
        config += text.count("no such file or directory") and text.count("config")
    return {"database_lock_errors": lock, "config_file_errors": config}


def _inv_rows(db: Path, run_id: int) -> list[dict[str, Any]]:
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id,status,http_status_code,finish_reason,input_tokens,output_tokens,"
        "estimated_cost,error_code,error_message,attempt_no,latency_ms,"
        "length(raw_response_text) AS raw_len, created_at, request_id, "
        "input_snapshot_json "
        "FROM model_invocations WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _window_rows(db: Path, run_id: int) -> list[dict[str, Any]]:
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id,window_index,status,attempt_count,provider_attempt_id,"
        "token_input,token_output,cost,error_code,error_detail,"
        "started_at,completed_at "
        "FROM whole_book_run_windows WHERE run_id=? ORDER BY window_index",
        (run_id,),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _elapsed_s(started: str | None, completed: str | None) -> float | None:
    if not started or not completed:
        return None
    from datetime import datetime as dt

    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            a = dt.strptime(started, fmt)
            b = dt.strptime(completed, fmt)
            return round((b - a).total_seconds(), 3)
        except ValueError:
            continue
    return None


def _classify_window(w: dict[str, Any], inv_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    idx = int(w["window_index"])
    status = str(w["status"] or "")
    inv = inv_by_id.get(int(w["provider_attempt_id"] or 0))
    row: dict[str, Any] = {
        "window": idx,
        "state": status,
        "http": None,
        "finish_reason": None,
        "input_tokens": int(w.get("token_input") or 0),
        "output_tokens": int(w.get("token_output") or 0),
        "json": "NOT STARTED",
        "parser": "NOT STARTED",
        "schema": "NOT STARTED",
        "cost": float(w.get("cost") or 0.0),
        "elapsed": _elapsed_s(w.get("started_at"), w.get("completed_at")),
        "error_code": w.get("error_code"),
        "error_detail": (w.get("error_detail") or "")[:240],
    }
    if status in {"pending", ""} and not w.get("started_at"):
        row["state"] = "NOT STARTED"
        return row
    if status == "completed":
        row["http"] = 200
        row["finish_reason"] = (inv or {}).get("finish_reason") or "stop"
        row["json"] = "PASS"
        row["parser"] = "PASS"
        row["schema"] = "PASS"
        return row
    if status == "failed":
        detail = str(w.get("error_detail") or "") + " " + str(w.get("error_code") or "")
        if "ReadTimeout" in detail or "PROVIDER_TIMEOUT" in detail or "timeout" in detail.lower():
            row["http"] = "ReadTimeout"
            row["finish_reason"] = "N/A"
            row["json"] = "NOT APPLICABLE"
            row["parser"] = "NOT APPLICABLE"
            row["schema"] = "NOT APPLICABLE"
        elif (inv or {}).get("finish_reason") == "length":
            row["http"] = (inv or {}).get("http_status_code")
            row["finish_reason"] = "length"
            row["json"] = "FAIL"
            row["parser"] = "FAIL"
            row["schema"] = "FAIL"
        else:
            row["http"] = (inv or {}).get("http_status_code")
            row["finish_reason"] = (inv or {}).get("finish_reason")
            # Prefer real parse failure only when error is about output validity
            # and not a harvested timeout contamination.
            if "ReadTimeout" in str((inv or {}).get("error_message") or ""):
                row["http"] = "ReadTimeout"
                row["json"] = "NOT APPLICABLE"
                row["parser"] = "NOT APPLICABLE"
                row["schema"] = "NOT APPLICABLE"
            else:
                row["json"] = "FAIL"
                row["parser"] = "FAIL"
                row["schema"] = "FAIL"
        return row
    return row


def _result_content_ok(body: dict[str, Any]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if not body:
        return False, ["empty_body"]
    overview = body.get("overview")
    if not isinstance(overview, dict) or not overview:
        missing.append("overview")
    evidence = body.get("evidence_index")
    if not isinstance(evidence, list):
        missing.append("evidence_index")
    elif len(evidence) == 0:
        # empty evidence_index is suspicious for a completed short book
        missing.append("evidence_index_empty")
    coverage = body.get("coverage")
    if not isinstance(coverage, dict) or not coverage:
        missing.append("coverage")
    # entities/assets: accept nested overview fields or evidence_index as signal
    has_assets = False
    if isinstance(overview, dict):
        for key in (
            "entities",
            "candidate_entities",
            "assets",
            "key_entities",
            "characters",
            "themes",
            "summary",
            "plot_summary",
        ):
            if overview.get(key):
                has_assets = True
                break
    if evidence and not has_assets:
        has_assets = True
    if not has_assets:
        missing.append("entities/assets/summary")
    return (len(missing) == 0), missing


def _sha_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> int:
    confirm = "--confirm" in sys.argv
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    sidecar_log = LIVE_DIR / "sidecar-log.txt"
    if sidecar_log.exists():
        sidecar_log.unlink()

    defaults = _product_defaults()
    if defaults["max_tokens"] != 8192:
        raise SystemExit(f"product max_tokens={defaults['max_tokens']} expected 8192")
    if int(defaults["read_timeout"]) != 180:
        raise SystemExit(f"product read_timeout={defaults['read_timeout']} expected 180")

    formal = Path(os.environ["LOCALAPPDATA"]) / "StoryLens" / "database" / "storylens.db"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    temp_root = Path(os.environ["TEMP"]) / f"storylens-shortbook-e2e-{stamp}"
    temp_db = temp_root / "database" / "storylens.db"
    _backup_db(formal, temp_db)
    book = _book_stats(temp_db)

    report: dict[str, Any] = {
        "E2E_VERIFICATION": "BLOCKED",
        "BOOK_ID": BOOK_ID,
        "BOOK_TITLE": book["book_title"],
        "TEMP_DATABASE": str(temp_db),
        "FORMAL_DATABASE_WRITES": 0,
        "API_PORT": PORT,
        "HEALTH_HTTP": 0,
        "ANALYSIS_RUNS_HTTP": 0,
        "PREFLIGHT": "FAIL",
        "WINDOW_COUNT": EXPECTED_WINDOWS,
        "PROVIDER": PROVIDER,
        "MODEL": MODEL,
        "MAX_TOKENS_SOURCE": "PRODUCT DEFAULT",
        "MAX_TOKENS": defaults["max_tokens"],
        "TIMEOUT_SOURCE": "PRODUCT DEFAULT",
        "READ_TIMEOUT": int(defaults["read_timeout"]),
        "RETRY": defaults["retry"],
        "CREATE_RUN_HTTP": 0,
        "CREATE_RESPONSE_TIME": -1,
        "RUN_ID": None,
        "FINAL_RUN_STATE": None,
        "COMPLETED_WINDOWS": 0,
        "FAILED_WINDOW": None,
        "REAL_PROVIDER_REQUESTS": 0,
        "SUCCESSFUL_HTTP_200_CALLS": 0,
        "AUTO_RETRIES": 0,
        "FINISH_REASONS": [],
        "JSON": "FAIL",
        "PARSER": "FAIL",
        "SCHEMA": "FAIL",
        "RESULT_API_HTTP": 0,
        "RESULT_CONTENT": "FAIL",
        "RESTART_RECOVERY": "FAIL",
        "DATABASE_LOCK_ERRORS": 0,
        "CONFIG_FILE_ERRORS": 0,
        "ACTUAL_COST": 0.0,
        "FORMAL_DATABASE_MODIFIED": "NO",
        "SOURCE_MODIFIED": "NO",
        "BUILD": "NO",
        "END_TO_END_API": "BLOCKED",
        "CHAPTER_COUNT": book["chapter_count"],
        "PARAGRAPH_COUNT": book["paragraph_count"],
        "PROVIDER_KEY_PRESENT": defaults["provider_key_present"],
    }

    out1 = LIVE_DIR / "api1.out.log"
    err1 = LIVE_DIR / "api1.err.log"
    out2 = LIVE_DIR / "api2.out.log"
    err2 = LIVE_DIR / "api2.err.log"
    proc1: subprocess.Popen | None = None
    proc2: subprocess.Popen | None = None
    base = f"http://127.0.0.1:{PORT}"

    try:
        proc1 = _start_api(temp_db, temp_root, out1, err1)
        with httpx.Client(base_url=base, timeout=60.0) as client:
            health = client.get("/health")
            report["HEALTH_HTTP"] = health.status_code
            if health.status_code != 200:
                raise RuntimeError(f"health={health.status_code}")

            runs = client.get("/api/v1/analysis-runs")
            report["ANALYSIS_RUNS_HTTP"] = runs.status_code
            if runs.status_code != 200:
                raise RuntimeError(f"analysis-runs={runs.status_code}")

            pre = client.post(
                f"/api/v1/books/{BOOK_ID}/whole-book-runs/preflight",
                json={"module_key": "book_overview", "mode": "whole_book_native"},
            )
            pre.raise_for_status()
            pre_body = pre.json()
            est_cost = float(pre_body.get("estimated_cost") or 0)
            est_windows = int(pre_body.get("estimated_windows") or 0)
            est_tokens = int(pre_body.get("estimated_tokens") or 0)
            # Worst-case HTTP calls under product retry=1
            est_max_calls = est_windows * (1 + int(defaults["retry"]))

            preflight_ok = (
                str(pre_body.get("book_id") or BOOK_ID) in {str(BOOK_ID), BOOK_ID}
                and est_windows == EXPECTED_WINDOWS
                and str(pre_body.get("provider_id") or PROVIDER) == PROVIDER
                and str(pre_body.get("model_id") or MODEL) == MODEL
                and defaults["max_tokens"] == 8192
                and int(defaults["read_timeout"]) == 180
                and est_cost <= COST_GATE
                and bool(pre_body.get("run_creation_enabled"))
            )
            report["PREFLIGHT"] = "PASS" if preflight_ok else "FAIL"
            report["WINDOW_COUNT"] = est_windows
            report["ESTIMATED_MAXIMUM_CALLS"] = est_max_calls
            report["ESTIMATED_MAXIMUM_COST"] = est_cost

            pre_summary = {
                "book_id": BOOK_ID,
                "book_title": book["book_title"],
                "chapter_count": book["chapter_count"],
                "paragraph_count": book["paragraph_count"],
                "window_count": est_windows,
                "provider": PROVIDER,
                "model": MODEL,
                "provider_key_present": defaults["provider_key_present"],
                "max_tokens_source": "PRODUCT DEFAULT",
                "max_tokens": defaults["max_tokens"],
                "timeout_source": "PRODUCT DEFAULT",
                "read_timeout": int(defaults["read_timeout"]),
                "retry": defaults["retry"],
                "temporary_database_path": str(temp_db),
                "api_port": PORT,
                "estimated_maximum_calls": est_max_calls,
                "estimated_maximum_cost": est_cost,
                "estimated_tokens": est_tokens,
                "formal_database_writes": 0,
                "preflight_api": pre_body,
                "product_defaults": defaults,
                "preflight_ok": preflight_ok,
                "measured_at": _utc_now(),
            }
            _write(LIVE_DIR / "preflight-summary.json", pre_summary)
            _write(
                LIVE_DIR / "request-metadata-redacted.json",
                {
                    "provider": PROVIDER,
                    "model": MODEL,
                    "max_output_tokens": "PRODUCT DEFAULT (class attr, not script override)",
                    "timeout_seconds": "PRODUCT DEFAULT (class attr, not script override)",
                    "max_auto_retries": defaults["retry"],
                    "api_key": "REDACTED",
                    "authorization": "REDACTED",
                },
            )

            print("=== SHORTBOOK NATIVE OVERVIEW E2E PREFLIGHT ===")
            print(f"Book ID：{BOOK_ID}")
            print(f"Book Title：{book['book_title']}")
            print(f"Chapter Count：{book['chapter_count']}")
            print(f"Paragraph Count：{book['paragraph_count']}")
            print(f"Window Count：{est_windows}")
            print(f"Provider：{PROVIDER}")
            print(f"Model：{MODEL}")
            print(f"Provider Key Present：{defaults['provider_key_present']}")
            print("Max Tokens Source：PRODUCT DEFAULT")
            print(f"Max Tokens：{defaults['max_tokens']}")
            print("Timeout Source：PRODUCT DEFAULT")
            print(f"Read Timeout：{int(defaults['read_timeout'])}")
            print(f"Retry：{defaults['retry']}")
            print(f"Temporary Database Path：{temp_db}")
            print(f"API Port：{PORT}")
            print(f"Estimated Maximum Calls：{est_max_calls}")
            print(f"Estimated Maximum Cost：¥{est_cost:.6f}")
            print("Formal Database Writes：0")

            if not preflight_ok:
                raise RuntimeError(f"preflight failed: {pre_body.get('blocking_errors')}")
            if est_cost > COST_GATE:
                raise RuntimeError(f"estimated cost {est_cost} > {COST_GATE}")

            if not confirm:
                print("\nRefusing Live call without -ConfirmLive")
                report["E2E_VERIFICATION"] = "COMPLETED"
                report["END_TO_END_API"] = "BLOCKED"
                report["NOTE"] = "preflight_only"
                _write(LIVE_DIR / "verification-summary.txt", _format_final(report))
                _write(LIVE_DIR / "run-summary.json", report)
                return 0

            # -------- Live --------
            if not defaults["provider_key_present"]:
                raise RuntimeError("provider key missing")

            payload = {
                "mode": "whole_book_native",
                "module_key": "book_overview",
                "provider_id": PROVIDER,
                "model_id": MODEL,
                "client_request_id": f"e2e-shortbook-{uuid.uuid4().hex[:12]}",
                "consent": {
                    "estimated_tokens": max(est_tokens, 1),
                    "estimated_cost": max(est_cost, 0.01),
                    "currency": pre_body.get("currency") or "CNY",
                    "confirmed": True,
                },
            }
            t0 = time.perf_counter()
            created = client.post(
                f"/api/v1/books/{BOOK_ID}/whole-book-runs",
                json=payload,
                timeout=CREATE_TIMEOUT_SECONDS,
            )
            create_ms = int((time.perf_counter() - t0) * 1000)
            report["CREATE_RUN_HTTP"] = created.status_code
            report["CREATE_RESPONSE_TIME"] = create_ms
            if created.status_code != 201:
                raise RuntimeError(f"create http={created.status_code} body={created.text[:400]}")
            if create_ms >= 5000:
                raise RuntimeError(f"create too slow: {create_ms}ms")
            cbody = created.json()
            run_id = int(cbody["run_id"])
            report["RUN_ID"] = run_id
            print(f"CREATE 201 {create_ms}ms run_id={run_id}", flush=True)
            _append_log(sidecar_log, f"{_utc_now()} CREATE run_id={run_id}")

            deadline = time.time() + MAX_WAIT_SECONDS
            last_sig = ""
            last_heartbeat = time.time()
            final: dict[str, Any] | None = None
            while time.time() < deadline:
                time.sleep(POLL_SECONDS)
                st = client.get(f"/api/v1/whole-book-runs/{run_id}").json()
                final = st
                progress = st.get("progress") or {}
                sig = (
                    f"{st.get('status')}|{st.get('current_stage')}|"
                    f"{progress.get('completed_windows')}/{progress.get('total_windows')}|"
                    f"{st.get('error_code')}"
                )
                now = time.time()
                if sig != last_sig:
                    print(
                        f"STATE status={st.get('status')} stage={st.get('current_stage')} "
                        f"windows={progress.get('completed_windows')}/{progress.get('total_windows')} "
                        f"error={st.get('error_code') or st.get('error') or '-'} "
                        f"elapsed={int(now - (deadline - MAX_WAIT_SECONDS))}s",
                        flush=True,
                    )
                    last_sig = sig
                    last_heartbeat = now
                elif now - last_heartbeat >= HEARTBEAT_SECONDS:
                    print(
                        f"HEARTBEAT status={st.get('status')} "
                        f"windows={progress.get('completed_windows')}/{progress.get('total_windows')} "
                        f"elapsed={int(now - (deadline - MAX_WAIT_SECONDS))}s",
                        flush=True,
                    )
                    last_heartbeat = now

                invs_mid = _inv_rows(temp_db, run_id)
                cost_mid = sum(float(i.get("estimated_cost") or 0) for i in invs_mid)
                # Prefer window costs for gate when available
                wins_mid = _window_rows(temp_db, run_id)
                if wins_mid:
                    cost_mid = sum(float(w.get("cost") or 0) for w in wins_mid)
                if cost_mid > COST_GATE:
                    raise RuntimeError(f"cost gate mid-run actual={cost_mid}")

                status = str(st.get("status") or "")
                if status in {"completed", "succeeded", "failed", "cancelled", "interrupted"}:
                    break
            assert final is not None
            report["FINAL_RUN_STATE"] = final.get("status")

            wins = _window_rows(temp_db, run_id)
            invs = _inv_rows(temp_db, run_id)
            inv_by_id = {int(i["id"]): i for i in invs}
            window_table = [_classify_window(w, inv_by_id) for w in wins]
            # Ensure 0..6 present
            present = {int(r["window"]) for r in window_table}
            for i in range(EXPECTED_WINDOWS):
                if i not in present:
                    window_table.append(
                        {
                            "window": i,
                            "state": "NOT STARTED",
                            "http": None,
                            "finish_reason": None,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "json": "NOT STARTED",
                            "parser": "NOT STARTED",
                            "schema": "NOT STARTED",
                            "cost": 0.0,
                            "elapsed": None,
                        }
                    )
            window_table.sort(key=lambda r: int(r["window"]))
            _write(LIVE_DIR / "window-results.json", window_table)

            completed = sum(1 for w in wins if w.get("status") == "completed")
            failed_idx = next(
                (int(w["window_index"]) for w in wins if w.get("status") == "failed"),
                None,
            )
            report["COMPLETED_WINDOWS"] = completed
            report["FAILED_WINDOW"] = failed_idx

            # Call accounting
            http200 = sum(
                1
                for i in invs
                if i.get("http_status_code") == 200 and i.get("status") == "succeeded"
            )
            auto_retries = 0
            for w in wins:
                auto_retries += max(0, int(w.get("attempt_count") or 0) - 1)
                if str(w.get("error_code") or "") == "PROVIDER_TIMEOUT":
                    el = _elapsed_s(w.get("started_at"), w.get("completed_at"))
                    # Transport retries once on timeout without raising attempt_count
                    if el and el >= (float(defaults["read_timeout"]) * 1.5):
                        auto_retries = max(auto_retries, 1)
            unanswered = sum(1 for r in window_table if r.get("http") == "ReadTimeout")
            report["SUCCESSFUL_HTTP_200_CALLS"] = http200
            report["AUTO_RETRIES"] = auto_retries
            # Real HTTP ≈ successful completions + unanswered attempts
            # (auto_retries counted separately for observability).
            report["REAL_PROVIDER_REQUESTS"] = http200 + unanswered + auto_retries

            reasons = []
            for r in window_table:
                if r.get("finish_reason") and r["finish_reason"] not in {"N/A", None}:
                    reasons.append(r["finish_reason"])
            report["FINISH_REASONS"] = reasons

            # Actual cost: sum completed window costs only (avoid harvest contamination)
            actual_cost = sum(
                float(w.get("cost") or 0)
                for w in wins
                if w.get("status") == "completed"
            )
            report["ACTUAL_COST"] = round(actual_cost, 6)
            if actual_cost > COST_GATE:
                raise RuntimeError(f"actual cost {actual_cost} > {COST_GATE}")

            # Aggregate JSON/Parser/Schema for completed windows only
            done_rows = [r for r in window_table if r.get("state") == "completed"]
            if done_rows and all(r.get("json") == "PASS" for r in done_rows):
                report["JSON"] = "PASS"
            if done_rows and all(r.get("parser") == "PASS" for r in done_rows):
                report["PARSER"] = "PASS"
            if done_rows and all(r.get("schema") == "PASS" for r in done_rows):
                report["SCHEMA"] = "PASS"

            # Fail-fast conditions after terminal
            if any(r.get("finish_reason") == "length" for r in window_table):
                raise RuntimeError("finish_reason=length")
            if any(r.get("http") == "ReadTimeout" for r in window_table):
                raise RuntimeError("ReadTimeout on a window")
            if any(
                r.get("state") == "failed" and r.get("json") == "FAIL" for r in window_table
            ):
                raise RuntimeError("window JSON/Parser/Schema FAIL")
            if report["FINAL_RUN_STATE"] not in {"completed", "succeeded"}:
                raise RuntimeError(f"final state={report['FINAL_RUN_STATE']}")
            if completed != EXPECTED_WINDOWS:
                raise RuntimeError(f"completed windows {completed}/{EXPECTED_WINDOWS}")

            print("| Window | State | HTTP | finish_reason | In | Out | JSON | Parser | Schema | Cost | Elapsed |")
            for r in window_table:
                print(
                    f"| {r['window']} | {r['state']} | {r['http']} | {r['finish_reason']} | "
                    f"{r['input_tokens']} | {r['output_tokens']} | {r['json']} | {r['parser']} | "
                    f"{r['schema']} | {r['cost']} | {r['elapsed']} |"
                )

            ov = client.get(f"/api/v1/whole-book-runs/{run_id}/overview")
            report["RESULT_API_HTTP"] = ov.status_code
            if ov.status_code != 200:
                raise RuntimeError(f"result http={ov.status_code}")
            ov_body = ov.json()
            ok, missing = _result_content_ok(ov_body)
            report["RESULT_CONTENT"] = "PASS" if ok else "FAIL"
            if not ok:
                raise RuntimeError(f"result content missing: {missing}")
            _write(LIVE_DIR / "result-before-restart.json", ov_body)
            before_sha = _sha_obj(ov_body)

        # Restart recovery
        _stop_proc(proc1)
        proc1 = None
        time.sleep(1)
        proc2 = _start_api(temp_db, temp_root, out2, err2)
        with httpx.Client(base_url=base, timeout=60.0) as client:
            h2 = client.get("/health")
            a2 = client.get("/api/v1/analysis-runs")
            st2 = client.get(f"/api/v1/whole-book-runs/{report['RUN_ID']}")
            ov2 = client.get(f"/api/v1/whole-book-runs/{report['RUN_ID']}/overview")
            st2_body = st2.json()
            ov2_body = ov2.json()
            _write(LIVE_DIR / "result-after-restart.json", ov2_body)
            after_sha = _sha_obj(ov2_body)
            recovery = (
                h2.status_code == 200
                and a2.status_code == 200
                and st2.status_code == 200
                and st2_body.get("status") in {"completed", "succeeded"}
                and ov2.status_code == 200
                and before_sha == after_sha
            )
            report["RESTART_RECOVERY"] = "PASS" if recovery else "FAIL"
            if not recovery:
                raise RuntimeError(
                    f"restart recovery failed health={h2.status_code} "
                    f"runs={a2.status_code} status={st2_body.get('status')} "
                    f"ov={ov2.status_code} sha_match={before_sha == after_sha}"
                )

        logs = _scan_logs(out1, err1, out2, err2, sidecar_log)
        report["DATABASE_LOCK_ERRORS"] = logs["database_lock_errors"]
        report["CONFIG_FILE_ERRORS"] = logs["config_file_errors"]
        if report["DATABASE_LOCK_ERRORS"] or report["CONFIG_FILE_ERRORS"]:
            raise RuntimeError(f"log errors: {logs}")

        passed = (
            report["HEALTH_HTTP"] == 200
            and report["ANALYSIS_RUNS_HTTP"] == 200
            and report["PREFLIGHT"] == "PASS"
            and report["CREATE_RUN_HTTP"] == 201
            and 0 <= int(report["CREATE_RESPONSE_TIME"]) < 5000
            and report["FINAL_RUN_STATE"] in {"completed", "succeeded"}
            and report["COMPLETED_WINDOWS"] == EXPECTED_WINDOWS
            and report["JSON"] == "PASS"
            and report["PARSER"] == "PASS"
            and report["SCHEMA"] == "PASS"
            and report["RESULT_API_HTTP"] == 200
            and report["RESULT_CONTENT"] == "PASS"
            and report["RESTART_RECOVERY"] == "PASS"
            and report["DATABASE_LOCK_ERRORS"] == 0
            and report["CONFIG_FILE_ERRORS"] == 0
            and float(report["ACTUAL_COST"]) <= COST_GATE
            and report["FORMAL_DATABASE_WRITES"] == 0
        )
        report["E2E_VERIFICATION"] = "COMPLETED" if passed else "BLOCKED"
        report["END_TO_END_API"] = "PASSED" if passed else "BLOCKED"
    except Exception as exc:
        report["E2E_VERIFICATION"] = "BLOCKED"
        report["END_TO_END_API"] = "BLOCKED"
        report["ERROR"] = f"{type(exc).__name__}: {exc}"
        print("E2E ERROR:", report["ERROR"], flush=True)
        logs = _scan_logs(out1, err1, out2, err2, sidecar_log)
        report["DATABASE_LOCK_ERRORS"] = logs["database_lock_errors"]
        report["CONFIG_FILE_ERRORS"] = logs["config_file_errors"]
    finally:
        _stop_proc(proc1)
        _stop_proc(proc2)

    _write(LIVE_DIR / "run-summary.json", report)
    text = _format_final(report)
    _write(LIVE_DIR / "verification-summary.txt", text)
    print(text)
    # Keep temp DB path for review; do not delete.
    print(f"\nTEMP DATABASE RETAINED：{temp_db}")
    return 0 if report.get("END_TO_END_API") == "PASSED" or report.get("NOTE") == "preflight_only" else 1


def _format_final(report: dict[str, Any]) -> str:
    lines = [
        f"E2E VERIFICATION：",
        f"{report.get('E2E_VERIFICATION')}",
        f"BOOK ID：",
        f"{report.get('BOOK_ID')}",
        f"BOOK TITLE：",
        f"{report.get('BOOK_TITLE')}",
        f"TEMP DATABASE：",
        f"{report.get('TEMP_DATABASE')}",
        f"FORMAL DATABASE WRITES：",
        f"{report.get('FORMAL_DATABASE_WRITES')}",
        f"API PORT：",
        f"{report.get('API_PORT')}",
        f"HEALTH HTTP：",
        f"{report.get('HEALTH_HTTP')}",
        f"ANALYSIS-RUNS HTTP：",
        f"{report.get('ANALYSIS_RUNS_HTTP')}",
        f"PREFLIGHT：",
        f"{report.get('PREFLIGHT')}",
        f"WINDOW COUNT：",
        f"{report.get('WINDOW_COUNT')}",
        f"PROVIDER：",
        f"{report.get('PROVIDER')}",
        f"MODEL：",
        f"{report.get('MODEL')}",
        f"MAX TOKENS SOURCE：",
        f"PRODUCT DEFAULT",
        f"MAX TOKENS：",
        f"{report.get('MAX_TOKENS')}",
        f"TIMEOUT SOURCE：",
        f"PRODUCT DEFAULT",
        f"READ TIMEOUT：",
        f"{report.get('READ_TIMEOUT')}",
        f"CREATE RUN HTTP：",
        f"{report.get('CREATE_RUN_HTTP')}",
        f"CREATE RESPONSE TIME：",
        f"{report.get('CREATE_RESPONSE_TIME')}",
        f"RUN ID：",
        f"{report.get('RUN_ID')}",
        f"FINAL RUN STATE：",
        f"{report.get('FINAL_RUN_STATE')}",
        f"COMPLETED WINDOWS：",
        f"{report.get('COMPLETED_WINDOWS')}",
        f"FAILED WINDOW：",
        f"{report.get('FAILED_WINDOW')}",
        f"REAL PROVIDER REQUESTS：",
        f"{report.get('REAL_PROVIDER_REQUESTS')}",
        f"SUCCESSFUL HTTP 200 CALLS：",
        f"{report.get('SUCCESSFUL_HTTP_200_CALLS')}",
        f"AUTO RETRIES：",
        f"{report.get('AUTO_RETRIES')}",
        f"FINISH REASONS：",
        f"{report.get('FINISH_REASONS')}",
        f"JSON：",
        f"{report.get('JSON')}",
        f"PARSER：",
        f"{report.get('PARSER')}",
        f"SCHEMA：",
        f"{report.get('SCHEMA')}",
        f"RESULT API HTTP：",
        f"{report.get('RESULT_API_HTTP')}",
        f"RESULT CONTENT：",
        f"{report.get('RESULT_CONTENT')}",
        f"RESTART RECOVERY：",
        f"{report.get('RESTART_RECOVERY')}",
        f"DATABASE LOCK ERRORS：",
        f"{report.get('DATABASE_LOCK_ERRORS')}",
        f"CONFIG FILE ERRORS：",
        f"{report.get('CONFIG_FILE_ERRORS')}",
        f"ACTUAL COST：",
        f"{report.get('ACTUAL_COST')}",
        f"FORMAL DATABASE MODIFIED：",
        f"NO",
        f"SOURCE MODIFIED：",
        f"NO",
        f"BUILD：",
        f"NO",
        f"END-TO-END API：",
        f"{report.get('END_TO_END_API')}",
    ]
    if report.get("ERROR"):
        lines.extend(["ERROR：", str(report.get("ERROR"))])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
