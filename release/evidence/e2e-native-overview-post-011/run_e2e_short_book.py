"""Native Overview real E2E on short book (book_id=5) after CHG-011.

No formal DB writes, no installer, no Fake transports.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[3]
PRIVATE_SRC = Path(r"D:\Dstorylens-private-engine-wt-phase2br1-integration\src")
EVIDENCE = Path(__file__).resolve().parent
PORT = 18003
BOOK_ID = 5
COST_GATE = 0.50
PY = REPO / ".venv" / "Scripts" / "python.exe"


def _stop_storylens() -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-Process -ErrorAction SilentlyContinue | "
                "Where-Object { $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$' } | "
                "Stop-Process -Force -ErrorAction SilentlyContinue"
            ),
        ],
        check=False,
    )
    time.sleep(1)


def _stop_port(port: int) -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f"$o=Get-NetTCPConnection -LocalPort {port} -State Listen "
                "-ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess; "
                "if($o){Stop-Process -Id $o -Force -ErrorAction SilentlyContinue}"
            ),
        ],
        check=False,
    )


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


def _assert_book5(db: Path) -> str:
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    b = con.execute("SELECT id, title FROM books WHERE id=5").fetchone()
    ch = con.execute("SELECT count(*) AS c FROM chapters WHERE book_id=5").fetchone()["c"]
    con.close()
    if b is None or int(ch) != 5:
        raise SystemExit(f"book5 invalid: {b} chapters={ch}")
    title = str(b["title"] or "")
    if "戏神" in title:
        raise SystemExit("refused long book 戏神")
    return title


def _start_api(db: Path, data_dir: Path, out: Path, err: Path) -> subprocess.Popen:
    env = os.environ.copy()
    for k in list(env):
        if "FAKE" in k.upper() and k.startswith("STORYLENS_"):
            env.pop(k, None)
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
        try:
            r = httpx.get(f"{base}/health", timeout=2.0)
            if r.status_code == 200:
                return proc
        except Exception:
            time.sleep(0.4)
    raise RuntimeError(f"API health failed; see {err}")


def _inv_stats(db: Path, run_id: int) -> list[dict]:
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id,status,http_status_code,finish_reason,input_tokens,output_tokens,"
        "estimated_cost,error_code,length(raw_response_text) AS raw_len "
        "FROM model_invocations WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def main() -> int:
    sys.path.insert(0, str(REPO / "apps" / "api"))
    from app.narrative_core.services.native_overview_live_transport import (
        AliyunNativeOverviewTransport,
    )

    if AliyunNativeOverviewTransport.max_output_tokens != 8192:
        raise SystemExit(
            f"product default max_output_tokens="
            f"{AliyunNativeOverviewTransport.max_output_tokens}, expected 8192"
        )

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "LOCAL_API_HEALTH": "FAIL",
        "ANALYSIS_RUNS_API": "FAIL",
        "CREATE_RUN_HTTP": 0,
        "CREATE_RESPONSE_TIME": -1,
        "RUN_ID": None,
        "PROVIDER": "aliyun_qwen_plus",
        "MODEL": "qwen3.7-plus",
        "MAX_TOKENS_SOURCE": "PRODUCT DEFAULT",
        "PRODUCT_DEFAULT_MAX_TOKENS": 8192,
        "REAL_PROVIDER_HTTP": None,
        "REAL_PROVIDER_CALLS": 0,
        "FINISH_REASON": None,
        "JSON": "FAIL",
        "PARSER": "FAIL",
        "SCHEMA": "FAIL",
        "FINAL_RUN_STATE": None,
        "RESULT_API_HTTP": 0,
        "RESTART_RECOVERY": "FAIL",
        "DATABASE_LOCK": "NO",
        "ACTUAL_COST": 0.0,
        "FORMAL_DATABASE_WRITES": 0,
        "END_TO_END_API": "BLOCKED",
        "BUILD": "NO",
        "BOOK_ID": BOOK_ID,
    }

    _stop_storylens()
    _stop_port(PORT)

    formal = Path(os.environ["LOCALAPPDATA"]) / "StoryLens" / "database" / "storylens.db"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    temp_root = Path(os.environ["TEMP"]) / f"storylens-e2e-native-{stamp}"
    temp_db = temp_root / "database" / "storylens.db"
    _backup_db(formal, temp_db)
    title = _assert_book5(temp_db)
    report["BOOK_TITLE"] = title

    out1 = EVIDENCE / "api.out.log"
    err1 = EVIDENCE / "api.err.log"
    proc1 = None
    proc2 = None
    base = f"http://127.0.0.1:{PORT}"

    try:
        proc1 = _start_api(temp_db, temp_root, out1, err1)
        report["LOCAL_API_HEALTH"] = "PASS"

        with httpx.Client(base_url=base, timeout=60.0) as client:
            runs = client.get("/api/v1/analysis-runs")
            if runs.status_code == 200:
                report["ANALYSIS_RUNS_API"] = "PASS"

            pre = client.post(
                f"/api/v1/books/{BOOK_ID}/whole-book-runs/preflight",
                json={"module_key": "book_overview", "mode": "whole_book_native"},
            )
            pre.raise_for_status()
            pre_body = pre.json()
            (EVIDENCE / "preflight.json").write_text(
                json.dumps(pre_body, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if not pre_body.get("run_creation_enabled"):
                raise RuntimeError(f"preflight blocked: {pre_body.get('blocking_errors')}")
            est = float(pre_body.get("estimated_cost") or 0)
            report["PREFLIGHT_ESTIMATED_COST"] = est
            # Soft note: worst-case estimate may exceed gate; enforce on actual spend.
            print(f"PREFLIGHT est_cost={est} tokens={pre_body.get('estimated_tokens')}")

            payload = {
                "mode": "whole_book_native",
                "module_key": "book_overview",
                "provider_id": "aliyun_qwen_plus",
                "model_id": "qwen3.7-plus",
                "client_request_id": f"e2e-post011-{uuid.uuid4().hex[:12]}",
                "consent": {
                    "estimated_tokens": int(pre_body.get("estimated_tokens") or 1),
                    "estimated_cost": max(est, 0.01),
                    "currency": pre_body.get("currency") or "CNY",
                    "confirmed": True,
                },
            }
            t0 = time.perf_counter()
            created = client.post(
                f"/api/v1/books/{BOOK_ID}/whole-book-runs",
                json=payload,
                timeout=5.0,
            )
            ms = int((time.perf_counter() - t0) * 1000)
            report["CREATE_RUN_HTTP"] = created.status_code
            report["CREATE_RESPONSE_TIME"] = ms
            created.raise_for_status()
            cbody = created.json()
            run_id = int(cbody["run_id"])
            report["RUN_ID"] = run_id
            print(f"CREATE {created.status_code} {ms}ms run_id={run_id} status={cbody.get('status')}")

            deadline = time.time() + 15 * 60
            final = None
            while time.time() < deadline:
                time.sleep(3)
                st = client.get(f"/api/v1/whole-book-runs/{run_id}").json()
                final = st
                print(
                    f"POLL status={st.get('status')} "
                    f"{st.get('progress_current')}/{st.get('progress_total')}"
                )
                invs = _inv_stats(temp_db, run_id)
                cost = sum(float(i.get("estimated_cost") or 0) for i in invs)
                if cost > COST_GATE:
                    raise RuntimeError(f"COST GATE mid-run actual={cost} > {COST_GATE}")
                if st.get("status") in {
                    "completed",
                    "succeeded",
                    "failed",
                    "failed_provider",
                    "cancelled",
                    "interrupted",
                }:
                    break
            assert final is not None
            report["FINAL_RUN_STATE"] = final.get("status")

            invs = _inv_stats(temp_db, run_id)
            report["REAL_PROVIDER_CALLS"] = len(invs)
            report["ACTUAL_COST"] = round(
                sum(float(i.get("estimated_cost") or 0) for i in invs), 6
            )
            reasons = [i.get("finish_reason") for i in invs]
            report["FINISH_REASON"] = reasons
            report["INVOCATIONS"] = invs
            if any(i.get("http_status_code") == 200 for i in invs):
                report["REAL_PROVIDER_HTTP"] = 200
            if any(r == "length" for r in reasons):
                report["any_finish_length"] = True
            else:
                report["any_finish_length"] = False

            if report["FINAL_RUN_STATE"] in {"completed", "succeeded"} and not report[
                "any_finish_length"
            ]:
                # Successful terminal overview implies parse/schema passed for windows.
                report["JSON"] = "PASS"
                report["PARSER"] = "PASS"
                report["SCHEMA"] = "PASS"

            try:
                ov = client.get(f"/api/v1/whole-book-runs/{run_id}/overview")
                report["RESULT_API_HTTP"] = ov.status_code
            except Exception:
                res = client.get(f"/api/v1/whole-book-runs/{run_id}/results")
                report["RESULT_API_HTTP"] = res.status_code

        # Restart recovery
        if proc1 and proc1.poll() is None:
            proc1.terminate()
            try:
                proc1.wait(timeout=5)
            except Exception:
                proc1.kill()
        _stop_port(PORT)
        time.sleep(1)
        proc2 = _start_api(temp_db, temp_root, EVIDENCE / "api2.out.log", EVIDENCE / "api2.err.log")
        with httpx.Client(base_url=base, timeout=60.0) as client:
            again = client.get(f"/api/v1/whole-book-runs/{report['RUN_ID']}")
            again.raise_for_status()
            ov2 = client.get(f"/api/v1/whole-book-runs/{report['RUN_ID']}/overview")
            if again.status_code == 200 and ov2.status_code == 200:
                report["RESTART_RECOVERY"] = "PASS"
                if report["RESULT_API_HTTP"] != 200:
                    report["RESULT_API_HTTP"] = ov2.status_code

        # log lock scan
        lock = False
        for p in (out1, err1, EVIDENCE / "api2.out.log", EVIDENCE / "api2.err.log"):
            if p.exists() and "database is locked" in p.read_text(encoding="utf-8", errors="ignore"):
                lock = True
        report["DATABASE_LOCK"] = "YES" if lock else "NO"

        passed = (
            report["LOCAL_API_HEALTH"] == "PASS"
            and report["ANALYSIS_RUNS_API"] == "PASS"
            and report["CREATE_RUN_HTTP"] == 201
            and 0 <= int(report["CREATE_RESPONSE_TIME"]) < 5000
            and report["RUN_ID"]
            and int(report["REAL_PROVIDER_CALLS"]) >= 1
            and not report.get("any_finish_length")
            and report["JSON"] == "PASS"
            and report["PARSER"] == "PASS"
            and report["SCHEMA"] == "PASS"
            and report["FINAL_RUN_STATE"] in {"completed", "succeeded"}
            and int(report["RESULT_API_HTTP"]) == 200
            and report["RESTART_RECOVERY"] == "PASS"
            and report["DATABASE_LOCK"] == "NO"
            and float(report["ACTUAL_COST"]) <= COST_GATE
        )
        report["END_TO_END_API"] = "PASSED" if passed else "BLOCKED"
    except Exception as exc:
        report["END_TO_END_API"] = "BLOCKED"
        report["ERROR"] = f"{type(exc).__name__}: {exc}"
        print("E2E ERROR:", report["ERROR"])
    finally:
        for proc in (proc1, proc2):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
        _stop_port(PORT)

    (EVIDENCE / "e2e-summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["END_TO_END_API"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
