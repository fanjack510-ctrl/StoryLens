"""Central task routing policy for cloud / local model selection (CHG-20260808-065).

Policies describe *how* a task picks a provider — not which provider is currently active.
Resolution is performed by ``cloud_provider_resolver_v1.resolve_provider_for_task``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RoutingMode(StrEnum):
    FOLLOW_DEFAULT = "FOLLOW_DEFAULT"
    INHERIT_RUN = "INHERIT_RUN"
    FIXED_PROVIDER = "FIXED_PROVIDER"
    LOCAL_ONLY = "LOCAL_ONLY"


@dataclass(frozen=True)
class TaskRoutingEntry:
    task_type: str
    mode: RoutingMode
    # Human label for routing preview / settings.
    display_name: str
    # Only for FIXED_PROVIDER / LOCAL_ONLY.
    fixed_provider: str | None = None
    fixed_model: str | None = None
    requires_structured_output: bool = False
    notes: str = ""


# Stable task type keys used by resolver + preview + tests.
TASK_SCENE_BOUNDARY = "scene_boundary"
TASK_SCENE_STRUCTURE = "scene_structure"
TASK_JSON_SCHEMA_REPAIR = "json_schema_repair"
TASK_RETRY = "retry"
TASK_RESUME = "resume"
TASK_WHOLE_BOOK = "whole_book"
TASK_WHOLE_BOOK_REPAIR = "whole_book_repair"
TASK_HIGH_DIFFICULTY_REVIEW = "high_difficulty_review"
TASK_LOCAL_MANUAL = "local_manual"
TASK_LOCAL_27B_MANUAL = "local_27b_manual"

TASK_ROUTING_POLICY: dict[str, TaskRoutingEntry] = {
    TASK_SCENE_BOUNDARY: TaskRoutingEntry(
        task_type=TASK_SCENE_BOUNDARY,
        mode=RoutingMode.FOLLOW_DEFAULT,
        display_name="场景边界",
        requires_structured_output=True,
        notes="Follows active_cloud_provider default model.",
    ),
    TASK_SCENE_STRUCTURE: TaskRoutingEntry(
        task_type=TASK_SCENE_STRUCTURE,
        mode=RoutingMode.FOLLOW_DEFAULT,
        display_name="场景结构",
        requires_structured_output=True,
        notes="Follows active_cloud_provider default model.",
    ),
    TASK_JSON_SCHEMA_REPAIR: TaskRoutingEntry(
        task_type=TASK_JSON_SCHEMA_REPAIR,
        mode=RoutingMode.INHERIT_RUN,
        display_name="JSON/Schema修复",
        requires_structured_output=True,
        notes="Always inherits the run-frozen provider/model (DEFECT-CANARY-015).",
    ),
    TASK_RETRY: TaskRoutingEntry(
        task_type=TASK_RETRY,
        mode=RoutingMode.INHERIT_RUN,
        display_name="重试",
        notes="Inherits run pin.",
    ),
    TASK_RESUME: TaskRoutingEntry(
        task_type=TASK_RESUME,
        mode=RoutingMode.INHERIT_RUN,
        display_name="继续执行",
        notes="Inherits run pin.",
    ),
    TASK_WHOLE_BOOK: TaskRoutingEntry(
        task_type=TASK_WHOLE_BOOK,
        mode=RoutingMode.FOLLOW_DEFAULT,
        display_name="全书分析",
        requires_structured_output=True,
        notes="New whole-book runs follow active_cloud_provider; existing runs stay pinned.",
    ),
    TASK_WHOLE_BOOK_REPAIR: TaskRoutingEntry(
        task_type=TASK_WHOLE_BOOK_REPAIR,
        mode=RoutingMode.INHERIT_RUN,
        display_name="全书修复",
        requires_structured_output=True,
        notes="Whole-book repair inherits WholeBookRun provider/model pin.",
    ),
    TASK_HIGH_DIFFICULTY_REVIEW: TaskRoutingEntry(
        task_type=TASK_HIGH_DIFFICULTY_REVIEW,
        mode=RoutingMode.FIXED_PROVIDER,
        display_name="高难度人工复核",
        fixed_provider="aliyun_qwen_max",
        fixed_model=None,
        notes="V1.2.0 keeps Max as verified fixed override; not migrated this change.",
    ),
    TASK_LOCAL_MANUAL: TaskRoutingEntry(
        task_type=TASK_LOCAL_MANUAL,
        mode=RoutingMode.LOCAL_ONLY,
        display_name="本地人工测试",
        fixed_provider="local_qwen14",
        notes="Local-only; never routed to cloud defaults.",
    ),
    TASK_LOCAL_27B_MANUAL: TaskRoutingEntry(
        task_type=TASK_LOCAL_27B_MANUAL,
        mode=RoutingMode.LOCAL_ONLY,
        display_name="27B手工短任务",
        fixed_provider="local_qwen27_manual",
        notes="Local-only.",
    ),
}


def get_task_routing_entry(task_type: str) -> TaskRoutingEntry:
    key = str(task_type or "").strip()
    entry = TASK_ROUTING_POLICY.get(key)
    if entry is None:
        raise KeyError(f"unknown task_type for routing policy: {task_type}")
    return entry


def list_routing_preview_tasks() -> list[TaskRoutingEntry]:
    """Ordered entries for the ProvidersPage routing preview panel."""
    order = (
        TASK_SCENE_BOUNDARY,
        TASK_SCENE_STRUCTURE,
        TASK_JSON_SCHEMA_REPAIR,
        TASK_HIGH_DIFFICULTY_REVIEW,
        TASK_WHOLE_BOOK,
        TASK_LOCAL_MANUAL,
        TASK_LOCAL_27B_MANUAL,
    )
    return [TASK_ROUTING_POLICY[k] for k in order]
