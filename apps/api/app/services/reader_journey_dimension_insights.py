"""Per-dimension scene insights for Reader Journey v2 presentation."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Literal

DIMENSION_KEYS = (
    "overall_reading",
    "plot_progression",
    "reading_tension",
    "emotional_intensity",
    "hook_payoff",
    "pacing_speed",
)

InsightSource = Literal["generated", "derived_legacy", "unavailable"]
CompositeRoleFitLabel = Literal["合适", "偏弱", "偏强", "无法判断"]

# Role bands for composite (reading_momentum) fit — aligned with pacing role bands.
COMPOSITE_ROLE_BANDS: dict[str, tuple[int, int]] = {
    "setup": (35, 65),
    "escalation": (55, 85),
    "investigation": (45, 75),
    "reveal": (55, 80),
    "climax": (70, 95),
    "aftermath": (30, 60),
    "transition": (30, 60),
    "open_end": (45, 75),
    "closed_end": (35, 65),
}

_OVERLAP_WARN_THRESHOLD = 0.72
_INSIGHT_MAX_CHARS = 160


def normalize_insight_text(text: str | None) -> str | None:
    if text is None:
        return None
    if not isinstance(text, str):
        return None
    cleaned = unicodedata.normalize("NFKC", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return None
    if len(cleaned) > _INSIGHT_MAX_CHARS:
        cleaned = cleaned[:_INSIGHT_MAX_CHARS].rstrip()
    return cleaned


def _overlap_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def validate_dimension_insights(insights: dict[str, str | None]) -> list[str]:
    """Return validation warnings; raise ValueError on forbidden duplicates."""
    warnings: list[str] = []
    normalized: dict[str, str] = {}
    for key in DIMENSION_KEYS:
        raw = insights.get(key)
        if raw is None:
            continue
        norm = normalize_insight_text(raw)
        if norm is None:
            continue
        for other_key, other_text in normalized.items():
            if norm == other_text:
                raise ValueError(
                    f"dimension_insights exact duplicate between {key} and {other_key}"
                )
            other_norm = normalize_insight_text(other_text)
            if other_norm and norm == other_norm:
                raise ValueError(
                    f"dimension_insights normalized duplicate between {key} and {other_key}"
                )
            if other_norm and _overlap_ratio(norm, other_norm) >= _OVERLAP_WARN_THRESHOLD:
                warnings.append(
                    f"high overlap between {key} and {other_key} "
                    f"(ratio={_overlap_ratio(norm, other_norm):.2f})"
                )
        normalized[key] = norm
    return warnings


def _score(node: dict[str, Any], key: str) -> float | None:
    scores = node.get("scores") or {}
    if isinstance(scores, dict):
        value = scores.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    direct = node.get(key)
    if isinstance(direct, (int, float)):
        return float(direct)
    return None


def _level_label(value: float | None, *, high: float = 65, low: float = 45) -> str:
    if value is None:
        return "暂难判断"
    if value >= high:
        return "偏强"
    if value <= low:
        return "偏弱"
    return "中等"


def derive_legacy_dimension_insights(node_or_profile_dict: dict[str, Any]) -> dict[str, Any]:
    """Deterministic per-dimension Chinese fallbacks from legacy scene fields."""
    node = node_or_profile_dict
    ordinal = int(node.get("scene_ordinal") or node.get("scene_id") or 0)
    role = str(node.get("scene_role") or node.get("role") or "scene")
    summary = normalize_insight_text(str(node.get("scene_value_summary") or "")) or ""
    momentum = _score(node, "reading_momentum")
    plot = _score(node, "plot_progress")
    tension = _score(node, "reading_tension")
    pacing = _score(node, "pacing_speed")
    hook = _score(node, "hook")
    payoff = _score(node, "payoff")
    emotion = _score(node, "emotional_investment")
    if emotion is None:
        arousal_start = _score(node, "arousal_start")
        arousal_end = _score(node, "arousal_end")
        if arousal_start is not None and arousal_end is not None:
            emotion = (arousal_start + arousal_end) / 2.0
        elif arousal_start is not None:
            emotion = arousal_start
        elif arousal_end is not None:
            emotion = arousal_end

    insights: dict[str, str | None] = {
        "overall_reading": None,
        "plot_progression": None,
        "reading_tension": None,
        "emotional_intensity": None,
        "hook_payoff": None,
        "pacing_speed": None,
    }

    if momentum is not None or summary:
        momentum_label = _level_label(momentum)
        summary_hint = f"「{summary[:40]}」" if summary else f"场景{ordinal}"
        insights["overall_reading"] = (
            f"综合阅读贡献{momentum_label}；{summary_hint}对读者继续阅读的整体拉动"
            f"{'明显' if momentum and momentum >= 65 else '有限' if momentum and momentum <= 45 else '一般'}。"
        )

    if plot is not None or summary:
        plot_label = _level_label(plot)
        insights["plot_progression"] = (
            f"剧情推进{plot_label}；"
            f"{'目标或冲突有实质变化' if plot and plot >= 65 else '变化有限，可能以铺垫或消化信息为主' if plot and plot <= 45 else '推进幅度适中'}。"
        )

    if tension is not None:
        tension_label = _level_label(tension)
        insights["reading_tension"] = (
            f"阅读张力{tension_label}；"
            f"{'等待与不确定性较强' if tension and tension >= 65 else '悬念压力较低，读者处于相对安全区' if tension and tension <= 45 else '张力处于章节中段水平'}。"
        )

    if emotion is not None:
        emotion_label = _level_label(emotion)
        insights["emotional_intensity"] = (
            f"情绪强度{emotion_label}；"
            f"{'情绪反应较强烈' if emotion and emotion >= 65 else '情绪较平，尚未建立强投入' if emotion and emotion <= 45 else '情绪起伏适中'}。"
        )

    if hook is not None or payoff is not None:
        hook_label = _level_label(hook, low=40, high=70)
        payoff_label = _level_label(payoff, low=40, high=70)
        if hook is not None and payoff is not None:
            if payoff >= 65 and hook <= 55:
                hook_text = "回报相对充分，钩子压力有所释放。"
            elif hook >= 65 and payoff <= 45:
                hook_text = "钩子建立较强但回报不足，问题仍悬而未决。"
            elif payoff >= 40 and payoff < 70:
                hook_text = "钩子与回报部分呼应，问题链处于推进或部分兑现阶段。"
            else:
                hook_text = f"钩子{hook_label}、回报{payoff_label}，问题链状态需结合前后场景判断。"
        elif hook is not None:
            hook_text = f"钩子{hook_label}，回报信息不足。"
        else:
            hook_text = f"回报{payoff_label}，钩子建立信息不足。"
        insights["hook_payoff"] = hook_text

    if pacing is not None:
        pacing_label = _level_label(pacing)
        role_hint = f"节奏与{role}类场景预期大致匹配"
        insights["pacing_speed"] = (
            f"节奏速度{pacing_label}；"
            f"{'叙事推进较快' if pacing and pacing >= 65 else '停留与观察较多，推进偏慢' if pacing and pacing <= 45 else role_hint}。"
        )

    available_count = sum(1 for value in insights.values() if value)
    if available_count == 0:
        return {
            "insights": {key: None for key in DIMENSION_KEYS},
            "insight_source": "unavailable",
            "warnings": [],
        }

    for key, value in insights.items():
        insights[key] = normalize_insight_text(value)

    try:
        warnings = validate_dimension_insights(insights)
    except ValueError:
        # Degrade conflicting legacy derive to unavailable per field.
        for key in DIMENSION_KEYS:
            insights[key] = None
        return {
            "insights": insights,
            "insight_source": "unavailable",
            "warnings": ["legacy derive produced forbidden duplicates"],
        }

    return {
        "insights": insights,
        "insight_source": "derived_legacy",
        "warnings": warnings,
    }


def _extract_generated_insights(node_or_profile_dict: dict[str, Any]) -> dict[str, str | None]:
    raw = node_or_profile_dict.get("dimension_insights")
    if not isinstance(raw, dict):
        return {key: None for key in DIMENSION_KEYS}
    out: dict[str, str | None] = {}
    for key in DIMENSION_KEYS:
        value = raw.get(key)
        out[key] = normalize_insight_text(value if isinstance(value, str) else None)
    return out


def resolve_scene_dimension_insights(
    node_or_profile_dict: dict[str, Any],
    *,
    persisted_insights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prefer generated/persisted insights; else legacy derive."""
    generated = _extract_generated_insights(node_or_profile_dict)
    if persisted_insights and isinstance(persisted_insights, dict):
        for key in DIMENSION_KEYS:
            if key in persisted_insights and generated.get(key) is None:
                generated[key] = normalize_insight_text(
                    persisted_insights.get(key)
                    if isinstance(persisted_insights.get(key), str)
                    else None
                )

    if any(generated.get(key) for key in DIMENSION_KEYS):
        warnings: list[str] = []
        try:
            warnings = validate_dimension_insights(generated)
        except ValueError as exc:
            legacy = derive_legacy_dimension_insights(node_or_profile_dict)
            legacy["warnings"] = [str(exc), *legacy.get("warnings", [])]
            return legacy
        return {
            "insights": generated,
            "insight_source": "generated",
            "warnings": warnings,
        }

    return derive_legacy_dimension_insights(node_or_profile_dict)


def composite_role_fit_label(
    momentum: float | None,
    scene_role: str | None,
) -> CompositeRoleFitLabel:
    if momentum is None or not isinstance(momentum, (int, float)):
        return "无法判断"
    band = COMPOSITE_ROLE_BANDS.get(scene_role or "", (40, 70))
    low, high = band
    if momentum < low:
        return "偏弱"
    if momentum > high:
        return "偏强"
    return "合适"


def attach_dimension_insights_to_node(
    node: dict[str, Any],
    *,
    persisted_insights: dict[str, Any] | None = None,
) -> None:
    """Mutate visualization node with dimension insights presentation fields."""
    resolved = resolve_scene_dimension_insights(node, persisted_insights=persisted_insights)
    node["dimension_insights"] = resolved["insights"]
    node["insight_source"] = resolved["insight_source"]
    if resolved.get("warnings"):
        node["dimension_insight_warnings"] = list(resolved["warnings"])

    scores = node.get("scores") or {}
    momentum = None
    if isinstance(scores, dict) and scores.get("reading_momentum") is not None:
        momentum = float(scores["reading_momentum"])
    elif node.get("overall_reading_score") is not None:
        momentum = float(node["overall_reading_score"])
    elif isinstance(node.get("engagement"), dict):
        eng = node["engagement"].get("engagement_score")
        if eng is not None:
            momentum = float(eng)

    if momentum is not None:
        node["overall_reading_score"] = momentum

    scene_role = node.get("scene_role") or node.get("role")
    node["composite_role_fit"] = composite_role_fit_label(momentum, str(scene_role) if scene_role else None)


__all__ = [
    "COMPOSITE_ROLE_BANDS",
    "DIMENSION_KEYS",
    "InsightSource",
    "CompositeRoleFitLabel",
    "attach_dimension_insights_to_node",
    "composite_role_fit_label",
    "derive_legacy_dimension_insights",
    "normalize_insight_text",
    "resolve_scene_dimension_insights",
    "validate_dimension_insights",
]
