"""CHG-080 helpers: V2 result origin / scaffold detection / prepare enrichment."""
from __future__ import annotations

from typing import Any

from app.narrative_core.whole_book_v2.contracts import WholeBookAnalysisV2

SCAFFOLD_SUMMARY = "围绕目标、阻力与选择形成完整阶段"


def detect_scaffold(result: WholeBookAnalysisV2) -> bool:
    for stage in result.story.structure_stages:
        title = (stage.title or "").strip()
        if title.startswith("阶段") and any(ch.isdigit() for ch in title):
            if SCAFFOLD_SUMMARY in (stage.summary or ""):
                return True
            if title.replace(" ", "") in {f"阶段{i}" for i in range(1, 20)} or title.startswith("阶段 "):
                return True
        if SCAFFOLD_SUMMARY in (stage.summary or ""):
            return True
    for life in result.suspense.lifecycles:
        if "悬念@" in (life.question or ""):
            return True
    for stage in result.characters.protagonist.stages:
        joined = " ".join(
            [
                stage.entry_state or "",
                stage.exit_state or "",
                stage.goal or "",
            ]
        )
        if "阶段起点" in joined:
            return True
    return False


def resolve_result_origin(result: WholeBookAnalysisV2) -> str:
    origin = getattr(result.analysis_metadata, "result_origin", None) or "unknown"
    if origin not in {
        "real_provider",
        "deterministic_local_merge",
        "deterministic_test",
        "fixture",
        "mock",
        "legacy_migration",
        "legacy",
        "unknown",
    }:
        origin = "unknown"
    if detect_scaffold(result):
        # Read-time NON_REAL_RESULT — do not rewrite user DB.
        if origin == "real_provider":
            return "deterministic_local_merge"
        if origin in {"unknown", ""}:
            return "deterministic_local_merge"
    return origin


def product_flags_for_result(result: WholeBookAnalysisV2) -> dict[str, Any]:
    origin = resolve_result_origin(result)
    scaffold = detect_scaffold(result)
    is_real = origin == "real_provider" and not scaffold
    return {
        "is_real_provider_result": is_real,
        "needs_reanalysis": not is_real,
        "scaffold_detected": scaffold,
        "result_origin": origin,
        "non_real_result": not is_real,
        "non_real_message": (
            None
            if is_real
            else "当前结果不是完整真实 V2 分析，需要重新分析。"
        ),
    }


def enrich_v2_payload(result: WholeBookAnalysisV2, session: Any | None = None) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    flags = product_flags_for_result(result)
    # Backfill origin for older persisted results without rewriting DB.
    meta = payload.setdefault("analysis_metadata", {})
    if not meta.get("result_origin") or meta.get("result_origin") == "unknown":
        meta["result_origin"] = flags["result_origin"]
    payload["product_flags"] = flags
    _attach_confirmed_axes(payload, session)
    return payload


def _attach_confirmed_axes(payload: dict[str, Any], session: Any | None) -> None:
    """Put the confirmed profile on the document at read time.

    The report's 作品画像 card printed 主类型 and three cells — 副类型, 核心叙事驱动力,
    重点分析方向 — that nothing on the long-novel engine fills; every book showed one value
    and three blanks. What a person actually confirmed about the book is the five axes, and
    they live on the book, not in the run's document.

    Done here rather than at write time so books analysed before this change get it too:
    rewriting stored documents to fix a display would be a migration, and this is not one.
    Any failure is swallowed — an enrichment must never take the report down with it.
    """
    if session is None:
        return
    try:
        from app.narrative_core.long_novel.contracts.profile import confirmed_axis_rows
        from app.narrative_core.long_novel.profile_repository import BookProfileRepository

        book_id = int((payload.get("book_metadata") or {}).get("book_id") or 0)
        if book_id <= 0:
            return
        stored = BookProfileRepository(session).get(book_id) or {}
        if str(stored.get("status") or "") != "confirmed":
            return
        rows = confirmed_axis_rows(stored.get("axes") or {})
        if rows:
            payload.setdefault("type_profile", {})["confirmed_axes"] = rows
    except Exception:  # noqa: BLE001 — an enrichment must never take the report down
        return
