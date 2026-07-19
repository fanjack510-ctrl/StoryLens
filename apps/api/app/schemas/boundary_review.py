from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewStatus = Literal["pending", "in_review", "confirmed", "superseded", "cancelled"]
UserBoundaryDecision = Literal["pending", "accept", "reject", "manually_added"]
ManualBoundaryReason = Literal[
    "location_change",
    "time_jump",
    "viewpoint_change",
    "primary_goal_reset",
    "explicit_scene_separator",
    "other_manual_boundary",
]


class BoundaryDecisionUpdate(BaseModel):
    user_decision: Literal["pending", "accept", "reject"]
    manual_reason_type: ManualBoundaryReason | None = None
    user_reason: str | None = Field(default=None, max_length=1000)


class ManualBoundaryCreate(BaseModel):
    left_paragraph_id: str
    user_reason: str | None = Field(default=None, max_length=1000)


class BoundaryReviewConfirm(BaseModel):
    confirmed_by: str = Field(min_length=1, max_length=255)


class BoundaryReviewDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transition_id: str
    left_paragraph_id: str
    right_paragraph_id: str
    model_candidate: bool
    model_confidence: float
    model_reason_code: str | None
    first_pass_json: str
    adjudication_result: str | None
    review_priority: str
    user_decision: str
    user_reason: str | None
    final_boundary: bool
    semantic_conflict: bool = False
    conflict_code: str | None = None
    deterministic_legal: bool | None = None
    deterministic_reason: str | None = None
    model_boundary_candidate: bool | None = None
    enum_snapshot_json: str = "{}"
    source_batch_index: int | None = None
    manual_reason_type: str | None = None


class ReviewParagraph(BaseModel):
    id: str
    paragraph_index: int
    raw_text: str


class BoundaryReviewResponse(BaseModel):
    id: int
    book_id: int
    chapter_id: int
    analysis_run_id: int
    prompt_version: str
    provider: str
    model: str
    status: ReviewStatus
    candidate_count: int
    accepted_count: int
    rejected_count: int
    manually_added_count: int
    created_at: datetime
    completed_at: datetime | None
    decisions: list[BoundaryReviewDecisionResponse]
    paragraphs: list[ReviewParagraph]


class ScenePreviewItem(BaseModel):
    ordinal: int
    start_paragraph_id: str
    end_paragraph_id: str
    paragraph_count: int


class ScenePreviewResponse(BaseModel):
    review_id: int
    coverage_rate: float
    scenes: list[ScenePreviewItem]


class BoundaryRevisionResponse(BaseModel):
    revision_id: int
    revision_number: int
    scene_count: int
    coverage_rate: float
