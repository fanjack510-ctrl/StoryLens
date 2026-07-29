"""CHG-20260729-003 presentation enrich for comprehensive reading (no formula_v2 change)."""

from __future__ import annotations

from typing import Any

from app.services.reader_journey_dimension_insights import composite_role_fit_label

MOMENTUM_DELTA = 7.0
MAX_KEY_NODES = 5


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _score(node: dict[str, Any], key: str) -> float | None:
    scores = node.get("scores") or {}
    if isinstance(scores, dict):
        return _num(scores.get(key))
    return None


def _momentum(node: dict[str, Any]) -> float | None:
    if _num(node.get("overall_reading_score")) is not None:
        return float(node["overall_reading_score"])
    m = _score(node, "reading_momentum")
    if m is not None:
        return m
    eng = node.get("engagement") or {}
    if isinstance(eng, dict):
        return _num(eng.get("engagement_score"))
    return None


def _emotion(node: dict[str, Any]) -> float | None:
    e = _score(node, "emotional_investment")
    if e is not None:
        return e
    a0 = _score(node, "arousal_start")
    a1 = _score(node, "arousal_end")
    if a0 is not None and a1 is not None:
        return (a0 + a1) / 2.0
    return a0 if a0 is not None else a1


def derive_comprehensive_reading_factors_v1(
    node: dict[str, Any],
    *,
    prev: dict[str, Any] | None = None,
) -> dict[str, Any]:
    momentum = _momentum(node)
    fit = node.get("composite_role_fit") or composite_role_fit_label(
        momentum, str(node.get("scene_role") or node.get("role") or "") or None
    )
    role = str(node.get("scene_role") or "").lower()
    plot = _score(node, "plot_progress")
    tension = _score(node, "reading_tension")
    hook = _score(node, "hook")
    payoff = _score(node, "payoff")
    pacing = _score(node, "pacing_speed")
    pacing_fit = _score(node, "pacing_fit")
    emotion = _emotion(node)

    drivers: list[tuple[int, float, str]] = []
    drags: list[tuple[int, float, str]] = []

    def add_driver(text: str, priority: int, strength: float) -> None:
        if strength >= 55:
            drivers.append((priority, strength, text))

    def add_drag(text: str, priority: int, strength: float) -> None:
        if strength >= 40 or fit != "合适":
            drags.append((priority, strength, text))

    if payoff is not None and payoff >= 65 and (hook is None or payoff >= (hook or 0)):
        add_driver("前置钩子得到回应", 10, payoff)
    elif hook is not None and hook >= 65 and (payoff is None or payoff < 45):
        add_driver("新钩子有效建立", 20, hook)

    if plot is not None and plot >= 65 and role not in {"aftermath", "closed_end", "transition"}:
        add_driver("剧情产生实质推进" if plot >= 78 else "信息揭示改变局势", 15 if role in {"climax", "escalation", "reveal"} else 30, plot)

    if tension is not None and tension >= 65 and role in {"climax", "escalation", "reveal", "investigation"}:
        add_driver("冲突明显升级" if tension >= 78 else "风险与不确定性增加", 25, tension)

    if emotion is not None and emotion >= 68 and role not in {"setup", "open_end"}:
        add_driver("情绪变化清晰有效", 40, emotion)

    if fit == "合适" and ((pacing_fit is not None and pacing_fit >= 70) or (pacing is not None and 40 <= pacing <= 70)):
        add_driver("节奏与场景任务匹配", 50, pacing_fit or 72)

    if role in {"aftermath", "closed_end"} and payoff is not None and payoff >= 55:
        add_driver("场景完成有效收束", 18, payoff)

    if fit == "偏强":
        if pacing is not None and pacing >= 70:
            add_drag("节奏偏快", 10, pacing)
        else:
            add_drag("与当前场景任务不匹配", 12, 70)
    if fit == "偏弱":
        add_drag("与当前场景任务不匹配", 11, 68)
    if plot is not None and plot <= 45:
        add_drag("剧情推进有限", 20, 100 - plot)
    if tension is not None and tension <= 42 and role in {"climax", "escalation", "reveal"}:
        add_drag("阅读张力不足", 22, 100 - tension)
    if hook is not None and hook >= 55 and (payoff is None or payoff <= 40):
        add_drag("钩子缺少回应", 18, hook)
    if emotion is not None and emotion <= 42 and role not in {"setup", "open_end"} and plot is not None and plot >= 60:
        add_drag("情绪铺垫不足", 28, 100 - emotion)

    prev_m = _momentum(prev) if prev else None
    if momentum is not None and prev_m is not None and prev_m - momentum >= MOMENTUM_DELTA and plot is not None and plot <= 50:
        add_drag("前后承接较弱", 30, prev_m - momentum)

    drivers.sort(key=lambda item: (item[0], -item[1], item[2]))
    drags.sort(key=lambda item: (item[0], -item[1], item[2]))
    driver = drivers[0][2] if drivers else None
    drag = drags[0][2] if drags else None
    if driver and drag and driver == drag:
        drag = next((item[2] for item in drags if item[2] != driver), None)
    if not driver and not drag:
        return {"primary_driver": None, "primary_drag": None, "explanation_source": "unavailable"}
    return {"primary_driver": driver, "primary_drag": drag, "explanation_source": "derived"}


def _short_label(driver: str | None, drag: str | None) -> str | None:
    if not driver and not drag:
        return None
    if not driver or not drag:
        text = driver or drag or ""
        return text[:12]
    combo = f"{driver[:5]}，{drag[:5]}"
    return combo if len(combo) <= 12 else (driver if len(driver) <= len(drag) else drag)[:12]


def attach_comprehensive_reading_presentation(visualization: dict[str, Any]) -> dict[str, Any]:
    """Mutate visualization nodes/phases with presentation-only CHG-003 fields."""
    nodes = list(visualization.get("scene_nodes") or [])
    nodes = sorted(nodes, key=lambda n: int(n.get("scene_ordinal") or 0))
    enriched: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        prev = nodes[index - 1] if index > 0 else None
        momentum = _momentum(node)
        fit = node.get("composite_role_fit") or composite_role_fit_label(
            momentum, str(node.get("scene_role") or node.get("role") or "") or None
        )
        factors = derive_comprehensive_reading_factors_v1(node, prev=prev)
        node = dict(node)
        if momentum is not None:
            node["overall_reading_score"] = momentum
        node["composite_role_fit"] = fit
        node["primary_driver"] = factors["primary_driver"]
        node["primary_drag"] = factors["primary_drag"]
        node["explanation_source"] = factors["explanation_source"]
        node["comprehensive_short_label"] = _short_label(
            factors["primary_driver"], factors["primary_drag"]
        )
        enriched.append(node)

    visualization["scene_nodes"] = enriched

    # Key nodes (simplified mirror of FE rules)
    key_nodes: list[dict[str, Any]] = []
    for index in range(1, len(enriched)):
        prev = enriched[index - 1]
        curr = enriched[index]
        prev_m = _momentum(prev)
        curr_m = _momentum(curr)
        if prev_m is None or curr_m is None:
            continue
        delta = curr_m - prev_m
        kind = None
        label = None
        detail = curr.get("primary_driver") or curr.get("primary_drag")
        if abs(delta) >= MOMENTUM_DELTA and (
            (curr.get("primary_driver") == "前置钩子得到回应")
            or (delta >= MOMENTUM_DELTA and (_score(curr, "plot_progress") or 0) >= 70 and (_score(curr, "reading_tension") or 0) >= 65)
        ):
            kind, label = "composite_turn", "综合转折"
        elif delta >= MOMENTUM_DELTA:
            kind, label = "reading_rise", "阅读提升"
        elif delta <= -MOMENTUM_DELTA:
            kind, label = "reading_drop", "阅读下降"
        if kind:
            key_nodes.append(
                {
                    "scene_ordinal": int(curr.get("scene_ordinal") or 0),
                    "kind": kind,
                    "label": label,
                    "detail": detail,
                    "_mag": abs(delta),
                    "_pri": 1 if kind == "composite_turn" else 2 if kind == "reading_rise" else 3,
                }
            )
    key_nodes.sort(key=lambda item: (item["_pri"], -item["_mag"], item["scene_ordinal"]))
    dedup: dict[int, dict[str, Any]] = {}
    for item in key_nodes:
        ordinal = int(item["scene_ordinal"])
        if ordinal not in dedup:
            dedup[ordinal] = item
    final_keys = []
    for item in sorted(dedup.values(), key=lambda x: (x["_pri"], -x["_mag"], x["scene_ordinal"]))[:MAX_KEY_NODES]:
        final_keys.append(
            {
                "scene_ordinal": item["scene_ordinal"],
                "kind": item["kind"],
                "label": item["label"],
                "detail": item.get("detail"),
            }
        )
    visualization["comprehensive_key_nodes"] = final_keys

    phases = list(visualization.get("phases") or [])
    out_phases = []
    for phase in phases:
        start = int(phase.get("start_scene_ordinal") or 0)
        end = int(phase.get("end_scene_ordinal") or 0)
        phase_nodes = [n for n in enriched if start <= int(n.get("scene_ordinal") or 0) <= end]
        scores = [_momentum(n) for n in phase_nodes]
        scores_f = [s for s in scores if s is not None]
        title = str(phase.get("title") or "")
        summary = "当前阶段表现较为平稳。"
        if scores_f:
            first, last = scores_f[0], scores_f[-1]
            trend = last - first
            avg = sum(scores_f) / len(scores_f)
            if "开端" in title or "入" in title:
                summary = "进入较慢，主要依靠信息铺垫" if trend < -6 or avg < 55 else "前段稳定，阅读期待逐步建立"
            elif "发展" in title or "推" in title or "转" in title:
                summary = "中段抬升明显，冲突形成主要推动" if trend >= 10 else "推进和张力持续抬升" if avg >= 65 else "推进稳定，但张力变化有限"
            elif "收" in title:
                summary = "完成回应，但结尾推动力回落" if trend <= -8 else "收束平稳，主要问题已得到回应"
        phase = dict(phase)
        phase["stage_judgment_summary"] = summary[:32]
        out_phases.append(phase)
    visualization["phases"] = out_phases
    return visualization


__all__ = [
    "attach_comprehensive_reading_presentation",
    "derive_comprehensive_reading_factors_v1",
]
