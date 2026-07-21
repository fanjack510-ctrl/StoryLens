"""Post-process scene boundaries to merge weak short fragments.

Does not mutate paragraph IDs, chapter content, or Scene schema — only filters
which boundary IDs are kept when materializing new scene ranges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

STRONG_REASON_CODES = frozenset(
    {
        "location_change",
        "time_jump",
        "viewpoint_change",
        "primary_goal_reset",
        "explicit_scene_separator",
        "conflict_state_change",
        "new_event_unit",
    }
)

STRONG_REASON_LABELS = frozenset(
    {
        "时间发生变化",
        "地点发生变化",
        "视角人物发生变化",
        "当前目标发生变化",
        "冲突阶段发生变化",
        "叙事任务明显变化",
    }
)

# Soft short-fragment thresholds (combined heuristics, not a single char cutoff).
MAX_SHORT_PARAGRAPHS = 1
SOFT_CHAR_LIMIT = 28
HARD_CHAR_LIMIT = 48

_DIALOGUE_ONLY = re.compile(
    r"^[\s\"“”‘’「」『』（）()【】\[\]…·・—\-–—~～!！?？.。,，、:：;；]*"
    r"[\u4e00-\u9fffA-Za-z0-9]{0,16}"
    r"[\s\"“”‘’「」『』（）()【】\[\]…·・—\-–—~～!！?？.。,，、:：;；]*$"
)
_ONOMATOPOEIA = re.compile(
    r"^(?:[啊呵哦噢嗯欸哎唉哇呜哼哈嘿嗨砰啪咚哐嗖呼呼呼隆隆咔嚓]+|[A-Za-z]{1,6})[\s!！?？.。…—\-–—~～]*$"
)
_NAME_SHOUT = re.compile(
    r"^[\s\"“”‘’「」『』]*"
    r"[\u4e00-\u9fff·]{1,8}"
    r"(?:——+|…+|!+|！+|\?+|？+)?"
    r"[\s\"“”‘’「」『』]*$"
)
_HARD_CUT_MARKERS = (
    "※",
    "＊",
    "***",
    "——本章完",
    "【梦境】",
    "【插叙】",
    "【闪回】",
    "【短信】",
    "【新闻】",
)
_INDEPENDENT_FORM = re.compile(
    r"(短信|微信|邮件|新闻|报纸|公告|梦境|梦里|插叙|旁白|日记|电报)"
)


class _ParagraphLike(Protocol):
    id: str
    paragraph_index: int
    normalized_text: str


@dataclass(frozen=True)
class BoundaryMeta:
    reason_codes: frozenset[str] = frozenset()
    reason_labels: frozenset[str] = frozenset()
    concise_reason: str = ""


def _paragraph_text(paragraph: _ParagraphLike) -> str:
    return (getattr(paragraph, "normalized_text", None) or "").strip()


def _char_count(paragraphs: list[_ParagraphLike]) -> int:
    return sum(len(_paragraph_text(item)) for item in paragraphs)


def _joined_text(paragraphs: list[_ParagraphLike]) -> str:
    return "".join(_paragraph_text(item) for item in paragraphs).strip()


def has_strong_boundary_evidence(meta: BoundaryMeta | None) -> bool:
    if meta is None:
        return False
    if meta.reason_codes & STRONG_REASON_CODES:
        return True
    if meta.reason_labels & STRONG_REASON_LABELS:
        return True
    reason = meta.concise_reason or ""
    strong_hints = (
        "时间",
        "地点",
        "视角",
        "POV",
        "pov",
        "目标",
        "冲突",
        "跳转",
        "切换",
        "硬切",
        "分隔",
        "梦境",
        "插叙",
        "短信",
        "新闻",
    )
    return any(hint in reason for hint in strong_hints)


def looks_like_dialogue_or_shout_fragment(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return True
    if _ONOMATOPOEIA.match(compact):
        return True
    if _NAME_SHOUT.match(compact) and len(compact) <= SOFT_CHAR_LIMIT:
        return True
    if len(compact) <= SOFT_CHAR_LIMIT and _DIALOGUE_ONLY.match(compact):
        return True
    return False


def looks_like_independent_form(text: str) -> bool:
    if any(marker in text for marker in _HARD_CUT_MARKERS):
        return True
    return bool(_INDEPENDENT_FORM.search(text)) and len(text) <= HARD_CHAR_LIMIT * 2


def looks_like_chapter_end_hook(text: str, *, is_last_scene: bool) -> bool:
    if not is_last_scene:
        return False
    compact = text.strip()
    if len(compact) < 8:
        return False
    # Complete narrative beat: not a bare shout / onomatopoeia residue.
    if looks_like_dialogue_or_shout_fragment(compact) and len(compact) <= SOFT_CHAR_LIMIT:
        return False
    hookish = ("？" in compact) or ("?" in compact) or ("……" in compact) or ("..." in compact)
    actionish = len(compact) >= 12 and not looks_like_dialogue_or_shout_fragment(compact)
    return hookish or actionish


def looks_like_incomplete_residue(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return True
    if compact.endswith(("——", "—", "…", "...", "～", "~")):
        return True
    if looks_like_dialogue_or_shout_fragment(compact):
        return True
    return False


def is_weak_short_fragment(
    scene_paragraphs: list[_ParagraphLike],
    *,
    opening_boundary: BoundaryMeta | None,
    closing_boundary: BoundaryMeta | None,
    is_last_scene: bool,
) -> bool:
    """True when this candidate scene should merge with neighbors by default."""
    if not scene_paragraphs:
        return True
    text = _joined_text(scene_paragraphs)
    para_count = len(scene_paragraphs)
    chars = _char_count(scene_paragraphs)
    strong_open = has_strong_boundary_evidence(opening_boundary)

    if looks_like_independent_form(text) and (
        strong_open or has_strong_boundary_evidence(closing_boundary)
    ):
        return False
    if looks_like_chapter_end_hook(text, is_last_scene=is_last_scene):
        return False

    residual = looks_like_incomplete_residue(text) and chars <= HARD_CHAR_LIMIT
    very_short = para_count <= MAX_SHORT_PARAGRAPHS and chars <= SOFT_CHAR_LIMIT
    short_body = para_count <= MAX_SHORT_PARAGRAPHS and chars <= HARD_CHAR_LIMIT

    # Strong cut into a non-residual body keeps the scene, even if brief.
    if strong_open and not residual:
        return False

    if residual:
        return True
    if very_short:
        return True
    if short_body and not strong_open:
        # One brief paragraph with no strong cut evidence — treat as continuation.
        return True
    return False


def _scene_slices(
    paragraphs: list[_ParagraphLike], boundary_ids: list[str]
) -> list[tuple[int, int, str | None]]:
    """Return (start_idx, end_idx, end_boundary_id|None) covering the chapter."""
    positions = {item.id: index for index, item in enumerate(paragraphs)}
    ends = [positions[item] for item in boundary_ids] + [len(paragraphs) - 1]
    slices: list[tuple[int, int, str | None]] = []
    start = 0
    for index, end in enumerate(ends):
        end_boundary = boundary_ids[index] if index < len(boundary_ids) else None
        slices.append((start, end, end_boundary))
        start = end + 1
    return slices


def consolidate_boundary_ids(
    paragraphs: list[_ParagraphLike],
    boundary_ids: list[str],
    boundary_meta: dict[str, BoundaryMeta] | None = None,
) -> list[str]:
    """Drop boundaries that produce weak short fragment scenes.

    Prefer merging fragments into the previous scene (dialogue/action continuation).
    First-scene fragments merge forward unless that would delete a strong cut.
    """
    if not paragraphs or not boundary_ids:
        return list(boundary_ids)

    meta = boundary_meta or {}
    positions = {item.id: index for index, item in enumerate(paragraphs)}
    ordered = sorted({item for item in boundary_ids if item in positions}, key=positions.get)
    if not ordered:
        return []

    current = list(ordered)
    for _ in range(len(paragraphs) + 2):
        slices = _scene_slices(paragraphs, current)
        drop: set[str] = set()
        for scene_index, (start, end, end_boundary) in enumerate(slices):
            scene_paragraphs = paragraphs[start : end + 1]
            opening_id = current[scene_index - 1] if scene_index > 0 else None
            opening_meta = meta.get(opening_id) if opening_id else None
            closing_meta = meta.get(end_boundary) if end_boundary else None
            is_last = scene_index == len(slices) - 1
            if not is_weak_short_fragment(
                scene_paragraphs,
                opening_boundary=opening_meta,
                closing_boundary=closing_meta,
                is_last_scene=is_last,
            ):
                continue
            if scene_index > 0 and opening_id:
                # Keep strong cuts unless the fragment is a pure residual shout.
                text = _joined_text(scene_paragraphs)
                if has_strong_boundary_evidence(opening_meta) and not looks_like_incomplete_residue(
                    text
                ):
                    continue
                drop.add(opening_id)
            elif end_boundary is not None:
                # Do not delete a strong following cut just to enlarge scene 1.
                if has_strong_boundary_evidence(closing_meta):
                    continue
                drop.add(end_boundary)
        if not drop:
            break
        current = [item for item in current if item not in drop]
    return current
