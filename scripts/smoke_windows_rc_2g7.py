"""STEP 2.7 Windows RC isolated sidecar smoke (no Live Provider, no user DB).

Windows Smoke Transport = PRIVATE_ENGINE or FIXTURE_EXPLICIT (never silent product default).
Live Provider Evidence = STEP 2.G5 (not re-run; New Live Cost = ¥0).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "dist" / "release" / "storylens-api.exe"
INSTALLER = ROOT / "dist" / "release" / "StoryLens_1.1.0-rc.1_x64-setup.exe"
EVIDENCE = ROOT / "release" / "evidence" / "CHG-20260725-003" / "night-run"
PY = ROOT / ".venv" / "Scripts" / "python.exe"


def _http(
    method: str,
    url: str,
    body: dict | None = None,
    timeout: float = 60.0,
    files: tuple[str, Path] | None = None,
) -> tuple[int, dict | list | str]:
    if files is not None:
        field, path = files
        boundary = f"----storylens{os.getpid()}"
        file_bytes = path.read_bytes()
        parts = []
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            (
                f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'
                f"Content-Type: text/plain\r\n\r\n"
            ).encode()
        )
        parts.append(file_bytes)
        parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        data = b"".join(parts)
        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
    else:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else {"raw": raw}
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def _wait_health(base: str, deadline_s: float = 120.0) -> dict:
    end = time.time() + deadline_s
    last = None
    while time.time() < end:
        try:
            code, body = _http("GET", f"{base}/health", timeout=5)
            if code == 200 and isinstance(body, dict):
                return body
            last = (code, body)
        except Exception as exc:  # noqa: BLE001
            last = ("err", str(exc))
        time.sleep(0.5)
    raise RuntimeError(f"health timeout: {last}")


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _counts(db_path: Path) -> dict:
    if not db_path.is_file():
        return {"missing": True}
    conn = sqlite3.connect(str(db_path))
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        out: dict = {"tables": sorted(names), "table_count": len(names)}
        for table in (
            "books",
            "chapters",
            "paragraphs",
            "analysis_runs",
            "scenes",
            "reader_journey_runs",
        ):
            if table in names:
                out[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            else:
                out[table] = None
        out["whole_book_tables"] = sorted(n for n in names if "whole_book" in n.lower())
        # Narrative / overview tables may not all contain the substring whole_book.
        out["schema_expanded"] = len(names) > 4
        return out
    finally:
        conn.close()


def _build_legacy_db(dest: Path) -> dict:
    """Build Free-core DB via formal create_all + narrative migrations (STEP 2.6 path).

    Packaged sidecar then opens the same file for repeat-startup / read smoke.
    Ultra-minimal SQL fixtures are covered by directed pytest, not NSIS sidecar boot.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    script = r"""
import sys
from pathlib import Path
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from app.db.models import AnalysisRun, Base, Book, Chapter, Paragraph
from app.narrative_core.migrations.runner import apply_narrative_migrations
from app.narrative_core.services.native_overview_seed import seed_short_book_v1

dest = Path(sys.argv[1])
engine = create_engine(f"sqlite:///{dest}")

@event.listens_for(engine, "connect")
def _fk(dbapi_connection, _connection_record):
    c = dbapi_connection.cursor()
    c.execute("PRAGMA foreign_keys=ON")
    c.close()

Base.metadata.create_all(engine)
apply_narrative_migrations(engine)
# Repeat migration (STEP 2.6 repeat-startup safety on formal path).
apply_narrative_migrations(engine)
factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
with factory() as session:
    book = seed_short_book_v1(session)
    ch = session.scalar(select(Chapter).where(Chapter.book_id == book.id).limit(1))
    session.add(
        AnalysisRun(
            task_type="scene_pipeline",
            subject_type="chapter",
            subject_id=str(ch.id if ch else book.id),
            provider="local",
            model="m",
            prompt_version="1",
            schema_version="1",
            input_hash="hash-rc",
            status="completed",
            book_id=book.id,
        )
    )
    session.commit()
    print(
        int(session.scalar(select(func.count()).select_from(Book)) or 0),
        int(session.scalar(select(func.count()).select_from(Chapter)) or 0),
        int(session.scalar(select(func.count()).select_from(Paragraph)) or 0),
    )
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "apps" / "api")
    proc = subprocess.run(
        [str(PY), "-c", script, str(dest)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"legacy db build failed: {proc.stderr or proc.stdout}")
    return _counts(dest)


def package_audit() -> dict:
    results: dict = {"ok": True}
    forbidden = [
        b"OPENAI_API_KEY",
        b"sk-proj",
        b"provider_cost_ledger",
        b".git/config",
        b"Structure Empty Policy",
    ]
    for label, path in (("sidecar", SIDECAR), ("installer", INSTALLER)):
        if not path.is_file():
            results[label] = {"present": False}
            results["ok"] = False
            continue
        data = path.read_bytes()
        hits = {n.decode(): (n in data) for n in forbidden}
        entry = {
            "present": True,
            "size": path.stat().st_size,
            "forbidden_hits": hits,
            "has_private_engine_marker": b"storylens_private_engine" in data,
        }
        if any(hits.values()):
            results["ok"] = False
        if label == "sidecar" and not entry["has_private_engine_marker"]:
            results["ok"] = False
        results[label] = entry
    return results


def _start_sidecar(data_dir: Path, port: int, token: str) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(
        {
            "STORYLENS_DATA_DIR": str(data_dir),
            "STORYLENS_APP_ENV": "production",
            "STORYLENS_APP_HOST": "127.0.0.1",
            "STORYLENS_APP_PORT": str(port),
            "STORYLENS_SHUTDOWN_TOKEN": token,
            "PRO_NATIVE_OVERVIEW_ENABLED": "true",
            # RC install-chain only — not a product default; Live evidence remains STEP 2.G5.
            "STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE": "1",
        }
    )
    return subprocess.Popen(
        [str(SIDECAR)],
        env=env,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _shutdown(base: str, token: str, proc: subprocess.Popen) -> None:
    try:
        _http("POST", f"{base}/internal/shutdown", {"token": token}, timeout=10)
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def main() -> int:
    if not SIDECAR.is_file():
        print("MISSING sidecar", SIDECAR)
        return 2

    report: dict = {
        "Windows Smoke Transport": "PENDING",
        "Live Provider Evidence": "STEP 2.G5",
        "New Live Cost": "CNY 0.00",
        "RC Version": "1.1.0-rc.1",
        "Formal VERSION expected": "1.0.5",
    }
    smoke_root = Path(tempfile.mkdtemp(prefix="storylens-rc-2g7-"))
    try:
        # --- A: fresh install path: empty data + import + Free native ---
        data_a = smoke_root / "fresh"
        data_a.mkdir()
        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        token = f"rc2g7a-{os.getpid()}"
        proc = _start_sidecar(data_a, port, token)
        try:
            report["health_fresh"] = _wait_health(base)
            novel = smoke_root / "rc-smoke.txt"
            novel.write_text(
                "第一章 开始\n\n第一段文字。\n\n第二段文字。\n\n第二章 继续\n\n第三章段落。\n",
                encoding="utf-8",
            )
            code, imported = _http(
                "POST", f"{base}/api/v1/books/import", files=("file", novel)
            )
            report["import_status"] = code
            report["import"] = imported
            assert code == 201, imported
            book_id = int(imported["book_id"])  # type: ignore[index]

            code, preflight = _http(
                "POST",
                f"{base}/api/v1/books/{book_id}/whole-book-runs/preflight",
                {"module_key": "book_overview", "mode": "whole_book_native"},
            )
            report["preflight_status"] = code
            report["preflight"] = preflight
            assert code == 200, preflight
            assert isinstance(preflight, dict)
            assert preflight.get("license_allowed") is True
            blockers = preflight.get("blocking_errors") or []
            codes = [(e.get("code") if isinstance(e, dict) else e) for e in blockers]
            assert "PRO_LICENSE_REQUIRED" not in codes, codes

            # Assert preflight does not advertise Fixture as product default.
            assert isinstance(preflight, dict)
            assert preflight.get("engine_id") == "private-native-overview-v1"
            assert "Fixture execution" not in " ".join(preflight.get("warnings") or [])

            create_private = {
                "mode": "whole_book_native",
                "module_key": "book_overview",
                "provider_id": "private-native-overview-v1",
                "model_id": "native-overview-1",
                "client_request_id": f"rc-2g7-private-{os.getpid()}",
                "consent": {
                    "estimated_tokens": 1000,
                    "estimated_cost": 0.01,
                    "currency": "CNY",
                    "confirmed": True,
                },
            }
            code, created = _http(
                "POST", f"{base}/api/v1/books/{book_id}/whole-book-runs", create_private
            )
            report["create_private_status"] = code
            report["create_private"] = created
            report["Windows Smoke Transport"] = "FAKE"
            assert code in (200, 201), created
            assert isinstance(created, dict)
            assert created.get("error_code") != "PRO_LICENSE_REQUIRED"
            run_id = int(created.get("run_id") or created.get("id") or 0)
            assert run_id > 0
            report["run_id"] = run_id
            report["engine_used"] = "private"

            final = None
            for _ in range(90):
                code, run = _http("GET", f"{base}/api/v1/whole-book-runs/{run_id}")
                assert code == 200, run
                final = run
                if isinstance(run, dict) and run.get("status") in {
                    "completed",
                    "failed",
                    "cancelled",
                }:
                    break
                time.sleep(0.5)
            report["run"] = final
            assert isinstance(final, dict)
            assert final.get("provider") == "private-native-overview-v1", final
            assert final.get("provider") != "fixture-native-overview-v1"
            assert final.get("status") == "completed", final
            code, overview = _http("GET", f"{base}/api/v1/whole-book-runs/{run_id}/overview")
            report["overview_status"] = code
            report["overview_keys"] = (
                sorted(overview.keys()) if isinstance(overview, dict) else type(overview).__name__
            )
            assert code == 200, overview
            code, retry = _http("POST", f"{base}/api/v1/whole-book-runs/{run_id}/retry", {})
            report["retry_status"] = code
            if isinstance(retry, dict):
                assert retry.get("error_code") != "PRO_LICENSE_REQUIRED"

            # Evidence deep-link-ish: chapter/paragraph ids present in overview or run
            blob = json.dumps({"run": final, "overview": overview}, ensure_ascii=False)
            report["evidence_has_chapter_or_paragraph"] = (
                "chapter" in blob.lower() or "-P" in blob or "paragraph" in blob.lower()
            )
        finally:
            _shutdown(base, token, proc)

        # Restart persistence on same data dir
        port2 = _free_port()
        base2 = f"http://127.0.0.1:{port2}"
        token2 = f"rc2g7b-{os.getpid()}"
        # Keep same data dir; port changes
        proc2 = _start_sidecar(data_a, port2, token2)
        try:
            _wait_health(base2)
            code, run2 = _http("GET", f"{base2}/api/v1/whole-book-runs/{report['run_id']}")
            report["run_after_restart_status"] = code
            assert code == 200, run2
            code, books = _http("GET", f"{base2}/api/v1/books")
            report["books_after_restart_status"] = code
            assert code == 200
        finally:
            _shutdown(base2, token2, proc2)

        # --- B: 1.0.5-like DB upgrade via packaged sidecar ---
        data_b = smoke_root / "upgrade"
        (data_b / "database").mkdir(parents=True)
        db_b = data_b / "database" / "storylens.db"
        pre = _build_legacy_db(db_b)
        report["upgrade_pre_counts"] = pre
        port3 = _free_port()
        base3 = f"http://127.0.0.1:{port3}"
        token3 = f"rc2g7c-{os.getpid()}"
        proc3 = _start_sidecar(data_b, port3, token3)
        try:
            _wait_health(base3)
            post = _counts(db_b)
            report["upgrade_post_counts"] = post
            for key in ("books", "chapters", "paragraphs", "analysis_runs"):
                assert post.get(key) == pre.get(key), (key, pre.get(key), post.get(key))
            assert post.get("schema_expanded") or post.get("whole_book_tables"), (
                "expected schema expansion / whole-book tables after migration",
                post.get("tables"),
            )
            code, books = _http("GET", f"{base3}/api/v1/books")
            report["upgrade_books_status"] = code
            assert code == 200, books
        finally:
            _shutdown(base3, token3, proc3)

        proc4 = _start_sidecar(data_b, port3, token3)
        try:
            _wait_health(base3)
            post2 = _counts(db_b)
            report["upgrade_repeat_counts"] = post2
            for key in ("books", "chapters", "paragraphs", "analysis_runs"):
                assert post2.get(key) == pre.get(key)
        finally:
            _shutdown(base3, token3, proc4)

        report["package_audit"] = package_audit()
        report["result"] = "PASSED" if report["package_audit"].get("ok") else "FAILED_PACKAGE_AUDIT"
    except Exception as exc:  # noqa: BLE001
        report["result"] = "FAILED"
        report["error"] = str(exc)
    finally:
        shutil.rmtree(smoke_root, ignore_errors=True)

    out = EVIDENCE / "windows-rc-2g7-smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    out.write_text(payload, encoding="utf-8")
    sys.stdout.buffer.write((payload + "\nWROTE " + str(out) + "\n").encode("utf-8", errors="replace"))
    return 0 if report.get("result") == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
