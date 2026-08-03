"""Public-side Sample S chapter functions V2 fixture (TEST DATA — not production)."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence

FixtureChapterFunctionsMode = Literal[
    "available",
    "multi_function",
    "primary_null",
    "secondary_empty",
    "partial",
    "insufficient",
    "failed_empty",
    "failed_unknown_label",
    "synonym_normalize",
    "missing_citation",
    "repair_success",
    "long_book",
    "structure_context_absent",
    "structure_context_available",
    "structure_context_insufficient",
]


def _claim(value: str, citation_ids: Sequence[str], *, confidence: float = 0.7) -> dict[str, Any]:
    return {
        "value": value,
        "status": "observed",
        "citation_ids": list(citation_ids),
        "confidence": confidence,
    }


def _chapter(
    *,
    chapter_id: int | str,
    chapter_order: int,
    primary: str | None,
    secondary: Sequence[str],
    summary: str,
    citation_ids: Sequence[str],
    confidence: float = 0.66,
) -> dict[str, Any]:
    cids = list(citation_ids)
    return {
        "chapter_id": chapter_id,
        "chapter_order": chapter_order,
        "primary_function": primary,
        "secondary_functions": list(secondary),
        "observed_summary": _claim(summary, cids),
        "inferred_effect": None,
        "confidence": confidence,
        "supporting_citation_ids": list(cids),
        "limitations": ["FIXTURE_TEST_DATA"],
    }


def build_fixture_chapter_functions_v2(
    *,
    citation_ids: Sequence[str],
    chapter_units: Sequence[Mapping[str, Any]] | None = None,
    mode: FixtureChapterFunctionsMode = "available",
    context_capabilities: dict[str, Any] | None = None,
    structure_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ChapterFunctionsResultV2 wire dict bound to catalog citation_ids."""

    cids = [str(x) for x in citation_ids if str(x).strip()]
    caps = dict(context_capabilities or {})
    if structure_context is not None:
        caps["structure_derived_context"] = {
            "present": True,
            "marker": "DERIVED_CONTEXT_NOT_FACT",
            "coverage_scope": structure_context.get("coverage_scope"),
            "stage_count": len(structure_context.get("stages") or []),
        }
    elif mode == "structure_context_absent":
        caps["structure_derived_context"] = {"present": False, "marker": "DERIVED_CONTEXT_NOT_FACT"}
    elif mode == "structure_context_insufficient":
        caps["structure_derived_context"] = {
            "present": True,
            "marker": "DERIVED_CONTEXT_NOT_FACT",
            "coverage_scope": "insufficient",
            "stage_count": 0,
        }

    if mode == "insufficient":
        return {
            "contract_version": "v2",
            "evidence_contract_version": "v2",
            "coverage_scope": "insufficient",
            "chapters": [],
            "analysis_confidence": 0.0,
            "overall_confidence": 0.0,
            "limitations": [
                "FIXTURE_TEST_DATA",
                "context insufficient for chapter functions",
                "CHAPTER_FN_EMPTY_OBSERVATION_PERMITTED",
            ],
            "context_capabilities": caps,
            "empty_reason": "CHAPTER_FN_EMPTY_OBSERVATION_PERMITTED",
        }

    if mode == "failed_empty":
        return {
            "contract_version": "v2",
            "evidence_contract_version": "v2",
            "coverage_scope": "full_selected_range",
            "chapters": [],
            "analysis_confidence": 0.0,
            "limitations": ["FIXTURE_TEST_DATA"],
            "context_capabilities": caps,
        }

    if mode == "failed_unknown_label":
        if not cids:
            raise ValueError("failed_unknown_label requires citation_ids")
        return {
            "contract_version": "v2",
            "evidence_contract_version": "v2",
            "coverage_scope": "full_selected_range",
            "chapters": [
                _chapter(
                    chapter_id=1,
                    chapter_order=1,
                    primary="修仙境界章",
                    secondary=[],
                    summary="【测试数据】非法标签。",
                    citation_ids=[cids[0]],
                )
            ],
            "limitations": ["FIXTURE_TEST_DATA"],
            "context_capabilities": caps,
        }

    if mode == "missing_citation":
        return {
            "contract_version": "v2",
            "evidence_contract_version": "v2",
            "coverage_scope": "full_selected_range",
            "chapters": [
                {
                    "chapter_id": 1,
                    "chapter_order": 1,
                    "primary_function": "setup",
                    "secondary_functions": [],
                    "observed_summary": {
                        "value": "【测试数据】缺引用。",
                        "status": "observed",
                        "citation_ids": [],
                        "confidence": 0.5,
                    },
                    "inferred_effect": None,
                    "confidence": 0.5,
                    "supporting_citation_ids": [],
                    "limitations": ["FIXTURE_TEST_DATA"],
                }
            ],
            "limitations": ["FIXTURE_TEST_DATA"],
            "context_capabilities": caps,
        }

    if not cids:
        raise ValueError("fixture chapter functions require citation_ids")

    units = list(chapter_units or [])
    if not units:
        # Default Sample S: 3 chapters; map citations round-robin.
        units = [
            {"chapter_id": i + 1, "chapter_order": i + 1, "citation_ids": [cids[min(i, len(cids) - 1)]]}
            for i in range(3)
        ]

    def _cid_for(idx: int, unit: dict[str, Any]) -> list[str]:
        unit_cids = [str(x) for x in (unit.get("citation_ids") or []) if str(x).strip()]
        if unit_cids:
            return unit_cids[:1]
        return [cids[min(idx, len(cids) - 1)]]

    if mode == "long_book":
        chapters = []
        for idx, unit in enumerate(units):
            primary = ("setup", "escalation", "climax", "resolution", "transition")[idx % 5]
            order_raw = unit.get("chapter_order")
            chapter_order = int(order_raw) if order_raw is not None else idx + 1
            chapters.append(
                _chapter(
                    chapter_id=unit.get("chapter_id", idx + 1),
                    chapter_order=chapter_order,
                    primary=primary,
                    secondary=["side_story"] if idx % 4 == 0 else [],
                    summary=f"【测试数据】长书第{idx + 1}章功能。",
                    citation_ids=_cid_for(idx, unit if isinstance(unit, dict) else {}),
                )
            )
        return {
            "contract_version": "v2",
            "evidence_contract_version": "v2",
            "coverage_scope": "full_selected_range",
            "chapters": chapters,
            "analysis_confidence": 0.62,
            "overall_confidence": 0.62,
            "limitations": ["FIXTURE_TEST_DATA", "LONG_BOOK_FIXTURE"],
            "context_capabilities": caps,
            "empty_reason": None,
        }

    if mode == "synonym_normalize":
        # Wire uses synonym aliases; contract normalizer maps to canonical.
        u0 = units[0] if isinstance(units[0], dict) else {}
        u1 = units[1] if len(units) > 1 and isinstance(units[1], dict) else u0
        o0 = u0.get("chapter_order")
        o1 = u1.get("chapter_order")
        chapters = [
            _chapter(
                chapter_id=u0.get("chapter_id", 1),
                chapter_order=int(o0) if o0 is not None else 1,
                primary="rising",
                secondary=["bridge", "aside"],
                summary="【测试数据】同义词规范化。",
                citation_ids=_cid_for(0, u0),
            ),
            _chapter(
                chapter_id=u1.get("chapter_id", 2),
                chapter_order=int(o1) if o1 is not None else 2,
                primary="ending",
                secondary=["none"],
                summary="【测试数据】ending→resolution。",
                citation_ids=_cid_for(1, u1),
            ),
        ]
        # Pre-normalize for fixture transport that skips second pass in some paths.
        from app.narrative_core.services.chapter_functions_output_contract_v2 import (
            normalize_function_labels,
        )

        normalized_chapters = []
        for ch in chapters:
            p, s, err = normalize_function_labels(ch["primary_function"], ch["secondary_functions"])
            assert err is None
            ch = dict(ch)
            ch["primary_function"] = p
            ch["secondary_functions"] = list(s)
            normalized_chapters.append(ch)
        return {
            "contract_version": "v2",
            "evidence_contract_version": "v2",
            "coverage_scope": "full_selected_range",
            "chapters": normalized_chapters,
            "analysis_confidence": 0.7,
            "limitations": ["FIXTURE_TEST_DATA"],
            "context_capabilities": caps,
        }

    chapters_out: list[dict[str, Any]] = []
    for idx, unit in enumerate(units):
        if not isinstance(unit, dict):
            continue
        unit_cids = _cid_for(idx, unit)
        chapter_id = unit.get("chapter_id", idx + 1)
        order_raw = unit.get("chapter_order")
        chapter_order = int(order_raw) if order_raw is not None else idx + 1

        if mode == "partial" and idx >= max(1, len(units) // 2):
            continue
        if mode == "multi_function" and idx == 0:
            chapters_out.append(
                _chapter(
                    chapter_id=chapter_id,
                    chapter_order=chapter_order,
                    primary="setup",
                    secondary=["transition", "side_story"],
                    summary="【测试数据】主功能+次功能。",
                    citation_ids=unit_cids,
                )
            )
            continue
        if mode == "primary_null":
            chapters_out.append(
                _chapter(
                    chapter_id=chapter_id,
                    chapter_order=chapter_order,
                    primary=None,
                    secondary=["flashback"] if idx == 0 else ["transition"],
                    summary="【测试数据】primary 为空的合法章。",
                    citation_ids=unit_cids,
                )
            )
            continue
        if mode == "secondary_empty":
            chapters_out.append(
                _chapter(
                    chapter_id=chapter_id,
                    chapter_order=chapter_order,
                    primary=("setup", "escalation", "climax")[idx % 3],
                    secondary=[],
                    summary="【测试数据】仅 primary。",
                    citation_ids=unit_cids,
                )
            )
            continue
        if mode == "repair_success":
            # Valid payload representing post-repair success.
            chapters_out.append(
                _chapter(
                    chapter_id=chapter_id,
                    chapter_order=chapter_order,
                    primary=("setup", "escalation", "resolution")[idx % 3],
                    secondary=[],
                    summary="【测试数据】repair 后合法结果。",
                    citation_ids=unit_cids,
                )
            )
            continue

        # available / structure_context_*
        chapters_out.append(
            _chapter(
                chapter_id=chapter_id,
                chapter_order=chapter_order,
                primary=("setup", "escalation", "climax")[idx % 3],
                secondary=["transition"] if idx == 1 else [],
                summary=f"【测试数据】第{chapter_order}章叙事功能。",
                citation_ids=unit_cids,
            )
        )

    if mode == "partial" and not chapters_out and units:
        # At least one chapter for partial_span legality.
        u0 = units[0] if isinstance(units[0], dict) else {"chapter_id": 1, "chapter_order": 1}
        order0 = u0.get("chapter_order")
        chapters_out.append(
            _chapter(
                chapter_id=u0.get("chapter_id", 1),
                chapter_order=int(order0) if order0 is not None else 1,
                primary="setup",
                secondary=[],
                summary="【测试数据】partial 覆盖。",
                citation_ids=_cid_for(0, u0),
            )
        )

    coverage = "partial_span" if mode == "partial" else "full_selected_range"
    return {
        "contract_version": "v2",
        "evidence_contract_version": "v2",
        "coverage_scope": coverage,
        "chapters": chapters_out,
        "analysis_confidence": 0.68,
        "overall_confidence": 0.68,
        "limitations": ["FIXTURE_TEST_DATA"],
        "context_capabilities": caps,
        "empty_reason": None,
    }
