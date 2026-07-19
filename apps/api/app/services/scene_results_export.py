"""Deterministic Markdown export for completed Scene Analysis results.

Markdown intentionally omits full chapter prose; it only carries structured
analysis fields plus evidence paragraph IDs and short summaries.
"""

from __future__ import annotations

from app.services.scene_results_service import RunResultsBundle, SceneResultBundle

_FIELD_LABELS = [
    ("entry_state", "进入状态 entry_state"),
    ("goal", "目标 goal"),
    ("obstacle", "阻碍 obstacle"),
    ("turning_point", "转折 turning_point"),
    ("outcome", "结果 outcome"),
    ("unresolved_question", "悬而未决 unresolved_question"),
]


def _field_line(analysis: dict, key: str) -> str:
    field = analysis.get(key) or {}
    summary = (field.get("summary") or "").strip() if isinstance(field, dict) else ""
    ids = field.get("evidence_paragraph_ids") or [] if isinstance(field, dict) else []
    if not summary and not ids:
        return "无"
    ids_text = f"（证据：{', '.join(ids)}）" if ids else ""
    return f"{summary or '无'}{ids_text}"


def _scene_section(item: SceneResultBundle) -> list[str]:
    scene = item.scene
    lines: list[str] = []
    marker = "（离线恢复）" if item.offline_recovered else ""
    lines.append(
        f"## Scene {scene.ordinal:02d} · {scene.start_paragraph_id} → "
        f"{scene.end_paragraph_id}{marker}"
    )
    tags = item.analysis.get("function_tags") or []
    if tags:
        lines.append(f"- function_tags：{', '.join(tags)}")
    if scene.boundary_source:
        lines.append(f"- boundary_source：{scene.boundary_source}")
    for key, label in _FIELD_LABELS:
        lines.append(f"- {label}：{_field_line(item.analysis, key)}")
    key_actions = item.analysis.get("key_actions") or []
    if key_actions:
        lines.append("- key_actions：")
        for action in key_actions:
            if not isinstance(action, dict):
                continue
            summary = (action.get("summary") or "").strip() or "无"
            ids = action.get("evidence_paragraph_ids") or []
            ids_text = f"（证据：{', '.join(ids)}）" if ids else ""
            lines.append(f"  - {summary}{ids_text}")
    else:
        lines.append("- key_actions：无")
    lines.append("")
    return lines


def render_markdown(bundle: RunResultsBundle) -> str:
    summary = bundle.summary
    lines: list[str] = []
    title = bundle.chapter.display_title or bundle.chapter.title
    lines.append(f"# 分析结果：Run #{bundle.run.id} · {title}")
    lines.append("")
    lines.append(f"- Scene 总数：{summary['total_scene_count']}")
    if summary.get("coverage_rate") is not None:
        lines.append(f"- 覆盖率：{round(summary['coverage_rate'] * 100)}%")
    lines.append(f"- 单段 Scene 数量：{summary['single_paragraph_scene_count']}")
    if summary.get("longest_scene_ordinal") is not None:
        lines.append(
            f"- 最长 Scene：Scene {summary['longest_scene_ordinal']:02d}"
            f"（{summary['longest_scene_paragraph_count']} 段）"
        )
    lines.append(f"- 人工新增边界：{summary['manual_added_boundary_count']}")
    lines.append(f"- 模型接受边界：{summary['model_accepted_boundary_count']}")
    lines.append(f"- 人工接受冲突：{summary['user_accepted_conflict_count']}")
    lines.append(f"- Evidence 覆盖率：{round(summary['evidence_coverage_rate'] * 100)}%")
    lines.append("")
    for item in bundle.scenes:
        lines.extend(_scene_section(item))
    return "\n".join(lines).rstrip() + "\n"
