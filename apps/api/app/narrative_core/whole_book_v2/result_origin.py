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
        "unknown",
    }:
        origin = "unknown"
    if origin in {"unknown", ""} and detect_scaffold(result):
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
    }


def enrich_v2_payload(result: WholeBookAnalysisV2) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    flags = product_flags_for_result(result)
    # Backfill origin for older persisted results without rewriting DB.
    meta = payload.setdefault("analysis_metadata", {})
    if not meta.get("result_origin") or meta.get("result_origin") == "unknown":
        meta["result_origin"] = flags["result_origin"]
    payload["product_flags"] = flags
    return payload
