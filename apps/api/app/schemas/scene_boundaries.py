"""Schemas for manual scene boundary review API (CHG-041)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScenePartitionItem(BaseModel):
    scene_order: int
    start_paragraph_id: str
    end_paragraph_id: str
    included_in_journey: bool = True


class SceneBoundaryRevisionSummary(BaseModel):
    revision_id: int
    revision_number: int
    status: str
    source: str
    revision_etag: str
    boundary_hash: str
    chapter_text_hash: str
    scenes: list[ScenePartitionItem]
    confirmed_at: str | None = None


class SceneBoundariesOverviewResponse(BaseModel):
    chapter_id: int
    chapter_text_hash: str
    confirmed_revision: SceneBoundaryRevisionSummary | None = None
    draft_revision: SceneBoundaryRevisionSummary | None = None
    model_revision: SceneBoundaryRevisionSummary | None = None
    awaiting_confirmation: bool = False


class SceneBoundaryDraftCreateResponse(BaseModel):
    revision_id: int
    revision_etag: str
    scenes: list[ScenePartitionItem]
    boundary_hash: str | None = None
    status: str | None = None
    updated_at: str | None = None


class SceneBoundaryDraftSaveResponse(BaseModel):
    revision_id: int
    revision_etag: str
    boundary_hash: str
    scenes: list[ScenePartitionItem]
    status: str = "draft"
    updated_at: str | None = None


class SceneBoundaryDraftSaveRequest(BaseModel):
    expected_etag: str
    scenes: list[ScenePartitionItem]


class SceneBoundarySplitRequest(BaseModel):
    expected_etag: str
    boundary_after_paragraph_id: str
    client_request_id: str | None = None
    scene_order: int | None = None


class SceneBoundarySplitResponse(BaseModel):
    revision_id: int
    revision_etag: str
    boundary_hash: str
    scenes: list[ScenePartitionItem]
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None
    already_split: bool = False
    status: str = "draft"


class SceneBoundaryConfirmRequest(BaseModel):
    expected_etag: str
    start_journey: bool = False
    journey_options: dict[str, Any] = Field(default_factory=dict)
    client_request_id: str | None = None


class SceneBoundaryConfirmResponse(BaseModel):
    revision_id: int
    revision_etag: str
    boundary_hash: str
    journey_run_id: int | None = None
    journey_started: bool = False
    journey_status: str | None = None
    already_confirmed: bool = False
    journey_error_code: str | None = None
    journey_error_message: str | None = None
    # CHG-20260730-013 confirm-and-start contract
    analysis_run_id: int | None = None
    confirmed_revision_id: int | None = None
    confirmed_scene_count: int | None = None
    workflow_state: str | None = None
    already_started: bool = False
    client_request_id: str | None = None


class SceneBoundaryDiffResponse(BaseModel):
    revision_id: int
    against_revision_id: int | None = None
    changes: list[dict[str, Any]]
    scene_count_delta: int
