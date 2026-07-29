"""Partition edit helpers for manual scene boundary review (CHG-041)."""

from __future__ import annotations

from copy import deepcopy


def _ordered(scenes: list[dict]) -> list[dict]:
    return sorted(scenes, key=lambda item: int(item["scene_order"]))


def move_boundary(
    scenes: list[dict],
    *,
    boundary_index: int,
    direction: str,
    paragraph_ids: list[str],
) -> list[dict]:
    """Move a split line between adjacent scenes. direction: 'left' | 'right'."""
    ordered = _ordered(scenes)
    if boundary_index < 0 or boundary_index >= len(ordered) - 1:
        raise ValueError("SCENE_PARTITION_ORDER_INVALID")
    left = deepcopy(ordered[boundary_index])
    right = deepcopy(ordered[boundary_index + 1])
    pos = {pid: index for index, pid in enumerate(paragraph_ids)}
    left_start = pos[left["start_paragraph_id"]]
    left_end = pos[left["end_paragraph_id"]]
    right_start = pos[right["start_paragraph_id"]]
    if left_end + 1 != right_start:
        raise ValueError("SCENE_PARTITION_GAP")
    if direction == "left":
        if left_start >= left_end:
            raise ValueError("SCENE_PARTITION_EMPTY_SCENE")
        new_end_idx = left_end - 1
        left["end_paragraph_id"] = paragraph_ids[new_end_idx]
        right["start_paragraph_id"] = paragraph_ids[new_end_idx + 1]
    elif direction == "right":
        right_end_pos = pos[right["end_paragraph_id"]]
        if right_start >= right_end_pos:
            raise ValueError("SCENE_PARTITION_EMPTY_SCENE")
        new_start_idx = right_start + 1
        right["start_paragraph_id"] = paragraph_ids[new_start_idx]
        left["end_paragraph_id"] = paragraph_ids[new_start_idx - 1]
    else:
        raise ValueError("SCENE_PARTITION_ORDER_INVALID")
    ordered[boundary_index] = left
    ordered[boundary_index + 1] = right
    return ordered


def add_boundary(
    scenes: list[dict],
    *,
    after_paragraph_id: str,
    paragraph_ids: list[str],
) -> list[dict]:
    """Split one scene after after_paragraph_id (boundary after this paragraph).

    Raises ValueError with:
    - SCENE_SPLIT_INVALID_POSITION
    - SCENE_SPLIT_EMPTY_SCENE
    - SCENE_BOUNDARY_ALREADY_EXISTS
    - SCENE_PARTITION_PARAGRAPH_MISSING
    """
    ordered = _ordered(scenes)
    pos = {pid: index for index, pid in enumerate(paragraph_ids)}
    if after_paragraph_id not in pos:
        raise ValueError("SCENE_PARTITION_PARAGRAPH_MISSING")
    split_idx = pos[after_paragraph_id]
    if split_idx >= len(paragraph_ids) - 1:
        # Cannot split after the chapter's last paragraph.
        raise ValueError("SCENE_SPLIT_INVALID_POSITION")

    # Existing boundary after this paragraph?
    for scene in ordered[:-1]:
        if scene["end_paragraph_id"] == after_paragraph_id:
            raise ValueError("SCENE_BOUNDARY_ALREADY_EXISTS")

    target_idx = None
    for index, scene in enumerate(ordered):
        start_i = pos[scene["start_paragraph_id"]]
        end_i = pos[scene["end_paragraph_id"]]
        if start_i <= split_idx <= end_i:
            target_idx = index
            break
    if target_idx is None:
        raise ValueError("SCENE_SPLIT_INVALID_POSITION")

    scene = deepcopy(ordered[target_idx])
    start_i = pos[scene["start_paragraph_id"]]
    end_i = pos[scene["end_paragraph_id"]]
    # Must be strictly inside the scene (not last paragraph of the scene).
    if split_idx < start_i or split_idx >= end_i:
        raise ValueError("SCENE_SPLIT_INVALID_POSITION")
    if start_i == end_i:
        raise ValueError("SCENE_SPLIT_EMPTY_SCENE")

    left = {
        **scene,
        "end_paragraph_id": paragraph_ids[split_idx],
    }
    right = {
        "scene_order": int(scene["scene_order"]) + 1,
        "start_paragraph_id": paragraph_ids[split_idx + 1],
        "end_paragraph_id": scene["end_paragraph_id"],
        # Inherit journey participation from the parent scene.
        "included_in_journey": bool(scene.get("included_in_journey", True)),
    }
    if pos[left["start_paragraph_id"]] > pos[left["end_paragraph_id"]]:
        raise ValueError("SCENE_SPLIT_EMPTY_SCENE")
    if pos[right["start_paragraph_id"]] > pos[right["end_paragraph_id"]]:
        raise ValueError("SCENE_SPLIT_EMPTY_SCENE")

    updated = ordered[:target_idx] + [left, right] + ordered[target_idx + 1 :]
    for index, item in enumerate(updated, start=1):
        item["scene_order"] = index
    return updated


def delete_boundary(
    scenes: list[dict],
    *,
    boundary_index: int,
    paragraph_ids: list[str],
) -> list[dict]:
    """Remove a split line by merging adjacent scenes (delete_boundary / merge)."""
    return delete_scene_merge(scenes, boundary_index=boundary_index, paragraph_ids=paragraph_ids)


def delete_scene_merge(
    scenes: list[dict],
    *,
    boundary_index: int | None = None,
    paragraph_ids: list[str],
    direction: str | None = None,
    scene_order: int | None = None,
    included_in_journey: bool | None = None,
) -> list[dict]:
    """Merge adjacent scenes.

    - boundary_index: merge scenes at [i] and [i+1] (delete divider)
    - scene_order + direction: delete that scene into 'prev' or 'next'
    - included_in_journey: explicit merge result; when None and sides agree, inherit;
      when sides disagree and None, raise SCENE_MERGE_INCLUDED_CONFLICT
    """
    ordered = _ordered(scenes)
    if len(ordered) <= 1:
        raise ValueError("SCENE_PARTITION_EMPTY")
    if scene_order is not None:
        idx = next(
            (i for i, s in enumerate(ordered) if int(s["scene_order"]) == int(scene_order)),
            None,
        )
        if idx is None:
            raise ValueError("SCENE_PARTITION_ORDER_INVALID")
        if direction == "prev":
            if idx == 0:
                raise ValueError("SCENE_PARTITION_ORDER_INVALID")
            boundary_index = idx - 1
        elif direction == "next":
            if idx >= len(ordered) - 1:
                raise ValueError("SCENE_PARTITION_ORDER_INVALID")
            boundary_index = idx
        else:
            raise ValueError("SCENE_PARTITION_ORDER_INVALID")
    if boundary_index is None:
        raise ValueError("SCENE_PARTITION_ORDER_INVALID")
    if boundary_index < 0 or boundary_index >= len(ordered) - 1:
        raise ValueError("SCENE_PARTITION_ORDER_INVALID")
    pos = {pid: index for index, pid in enumerate(paragraph_ids)}
    left = deepcopy(ordered[boundary_index])
    right = deepcopy(ordered[boundary_index + 1])
    if pos[left["end_paragraph_id"]] + 1 != pos[right["start_paragraph_id"]]:
        raise ValueError("SCENE_PARTITION_GAP")
    left_inc = bool(left.get("included_in_journey", True))
    right_inc = bool(right.get("included_in_journey", True))
    if included_in_journey is not None:
        merged_included = bool(included_in_journey)
    elif left_inc == right_inc:
        merged_included = left_inc
    else:
        raise ValueError("SCENE_MERGE_INCLUDED_CONFLICT")
    merged = {
        "scene_order": left["scene_order"],
        "start_paragraph_id": left["start_paragraph_id"],
        "end_paragraph_id": right["end_paragraph_id"],
        "included_in_journey": merged_included,
    }
    updated = ordered[:boundary_index] + [merged] + ordered[boundary_index + 2 :]
    for index, item in enumerate(updated, start=1):
        item["scene_order"] = index
    return updated


def set_included(scenes: list[dict], *, scene_order: int, included: bool) -> list[dict]:
    ordered = _ordered(scenes)
    found = False
    for item in ordered:
        if int(item["scene_order"]) == scene_order:
            item["included_in_journey"] = included
            found = True
            break
    if not found:
        raise ValueError("SCENE_PARTITION_ORDER_INVALID")
    return ordered
