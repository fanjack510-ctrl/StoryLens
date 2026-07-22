from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.model_gateway.base import ProviderCapabilities

BoundaryReason = Literal[
    "时间发生变化",
    "地点发生变化",
    "视角人物发生变化",
    "当前目标发生变化",
    "冲突阶段发生变化",
    "叙事任务明显变化",
]
BoundaryReasonCode = Literal[
    "location_change", "time_jump", "viewpoint_change", "primary_goal_reset",
    "explicit_scene_separator",
]
GoalRelation = Literal["same", "refined", "interrupted", "completed_then_new", "replaced", "unclear"]
ActionChainRelation = Literal["continuous", "resumed", "new_chain", "unclear"]
TemporalRelation = Literal["continuous", "brief_flashback", "major_jump", "unclear"]
LocationRelation = Literal["same", "minor_move", "new_scene_location", "unclear"]
ViewpointRelation = Literal["same", "changed", "unclear"]
TransitionTrigger = Literal[
    "none", "location", "time", "viewpoint", "goal", "object", "explicit_separator"
]
FunctionTag = Literal["事件推进", "人物塑造", "冲突升级", "信息揭示", "过渡", "悬念设置"]


class SceneBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_paragraph_id: str
    reason_code: BoundaryReasonCode | None = None
    reason_summary: str = ""
    previous_scene_end_state: str = ""
    next_scene_start_state: str = ""
    reasons: list[BoundaryReason] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class SceneBoundaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter_id: str
    boundaries: list[SceneBoundary] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0, le=1)


class SceneTransitionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transition_id: str
    previous_primary_goal: str
    next_primary_goal: str
    goal_relation: GoalRelation
    action_chain_relation: ActionChainRelation
    temporal_relation: TemporalRelation
    location_relation: LocationRelation
    viewpoint_relation: ViewpointRelation
    trigger_type: TransitionTrigger
    sustained_change: bool
    boundary_decision: bool
    reason_code: BoundaryReasonCode | None = None
    confidence: float = Field(ge=0, le=1)
    concise_reason: str
    evidence_paragraph_ids: list[str] = Field(default_factory=list)


class SceneTransitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter_id: str
    transitions: list[SceneTransitionDecision]
    overall_confidence: float = Field(ge=0, le=1)


class CompactTransitionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transition_id: str
    boundary: bool
    goal_relation: GoalRelation
    action_chain_relation: ActionChainRelation
    temporal_relation: TemporalRelation
    location_relation: LocationRelation
    viewpoint_relation: ViewpointRelation
    trigger_type: TransitionTrigger
    confidence: float = Field(ge=0, le=1)


class CompactSelectedTransitionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transition_id: str
    reason_code: BoundaryReasonCode
    previous_primary_goal: str = Field(max_length=24)
    next_primary_goal: str = Field(max_length=24)
    concise_reason: str = Field(max_length=40)
    evidence_paragraph_ids: list[str] = Field(min_length=1, max_length=2)


class CompactTransitionClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["3.3"]
    decisions: list[CompactTransitionDecision]
    selected_details: list[CompactSelectedTransitionDetail] = Field(default_factory=list)


class BoundaryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transition_id: str
    evidence_paragraph_ids: list[str] = Field(min_length=1, max_length=2)


class CompactTransitionClassificationResultV34(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["3.4"]
    decisions: list[CompactTransitionDecision]
    boundary_evidence: list[BoundaryEvidence] = Field(default_factory=list)


class CompactTransitionCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transition_id: str
    boundary_candidate: bool
    goal_relation: GoalRelation
    action_chain_relation: ActionChainRelation
    temporal_relation: TemporalRelation
    location_relation: LocationRelation
    viewpoint_relation: ViewpointRelation
    trigger_type: TransitionTrigger
    confidence: float = Field(ge=0, le=1)


class CompactTransitionClassificationResultV35(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["3.5"]
    decisions: list[CompactTransitionCandidateDecision]


CandidateConflictCode = Literal[
    "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
    "CANDIDATE_FALSE_WITH_LEGAL_REASON",
    "INVALID_ENUM_COMBINATION",
    "LOW_CONFIDENCE_SEMANTIC_CONFLICT",
    "UNKNOWN_DETERMINISTIC_REASON",
]


class CandidateReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transition_id: str
    conflict_code: CandidateConflictCode
    boundary_candidate: bool
    deterministic_legal: bool
    deterministic_reason: str | None
    goal_relation: GoalRelation
    action_chain_relation: ActionChainRelation
    temporal_relation: TemporalRelation
    location_relation: LocationRelation
    viewpoint_relation: ViewpointRelation
    trigger_type: TransitionTrigger
    confidence: float = Field(ge=0, le=1)
    review_priority: Literal["high", "medium", "low"]
    safe_message: str


class CandidateReviewValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid_decisions: list[CompactTransitionCandidateDecision]
    conflicted_decisions: list[CompactTransitionCandidateDecision]
    issues: list[CandidateReviewIssue]


CandidateScopeRelation = Literal[
    "primary_scene_change",
    "local_subgoal_change",
    "temporary_interruption",
    "narrative_detail_change",
    "unclear",
]
CandidateContinuityRelation = Literal[
    "new_scene_chain", "same_scene_chain", "resumes_previous_chain", "unclear"
]


class BoundaryCandidateVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transition_id: str
    accept: bool
    scope_relation: CandidateScopeRelation
    continuity_relation: CandidateContinuityRelation
    confidence: float = Field(ge=0, le=1)


class BoundaryCandidateAdjudicationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["1.0"]
    verdicts: list[BoundaryCandidateVerdict]


class EvidenceField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    evidence_paragraph_ids: list[str] = Field(default_factory=list)


class SceneAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: str
    entry_state: EvidenceField
    goal: EvidenceField
    obstacle: EvidenceField
    key_actions: list[EvidenceField] = Field(default_factory=list)
    turning_point: EvidenceField
    outcome: EvidenceField
    unresolved_question: EvidenceField
    function_tags: list[FunctionTag] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @field_validator("key_actions")
    @classmethod
    def unique_actions(cls, value: list[EvidenceField]) -> list[EvidenceField]:
        summaries = [item.summary for item in value]
        if len(summaries) != len(set(summaries)):
            raise ValueError("key_actions 不得重复")
        return value


class RunTemporaryRequestAllowance(BaseModel):
    """Create-time / run-scoped request headroom (does not mutate daily settings)."""

    extra_requests: int = Field(ge=0, default=0)
    mode: Literal["recommended_worst_case", "estimated_usage"] = "recommended_worst_case"


class AnalysisRunCreate(BaseModel):
    task_type: Literal["scene_pipeline"] = "scene_pipeline"
    provider_name: str
    force: bool = False
    execution_mode: Literal["local", "cloud", "hybrid"] = "local"
    cloud_consent: bool = False
    analysis_mode: Literal["automatic", "assisted_boundary_review"] = "automatic"
    selected_provider: str | None = None
    capability_schema_version: str | None = None
    provider_state_version: str | None = None
    client_request_id: str | None = Field(default=None, min_length=8, max_length=64)
    run_temporary_request_allowance: RunTemporaryRequestAllowance | None = None


class AnalysisPreflightRequest(BaseModel):
    chapter_id: int
    provider: str
    execution_mode: Literal["local", "cloud", "hybrid"]
    analysis_mode: Literal["automatic", "assisted_boundary_review"]
    cloud_consent: bool
    capability_schema_version: str
    provider_state_version: str


class AnalysisPreflightResponse(BaseModel):
    eligible: bool
    blockers: list[str]
    provider_health_state: Literal["healthy", "unhealthy", "unknown", "stale"]
    health_source: str
    evaluated_at: str
    provider_state_version: str
    estimated_requests: int
    estimated_tokens: int
    estimated_cost: float
    within_budget: bool
    capability_schema_version: Literal["1c-a-2"]
    analysis_mode: Literal["automatic", "assisted_boundary_review"] | None = None
    stage: str | None = None
    paragraph_count: int | None = None
    transition_count: int | None = None
    detection_batch_count: int | None = None
    adjudication_batch_count_estimated: int | None = None
    scene_count: int | None = None
    expected_request_count: int | None = None
    worst_case_request_count: int | None = None
    estimated_input_tokens: int | None = None
    worst_case_input_tokens: int | None = None
    estimated_output_tokens: int | None = None
    worst_case_output_tokens: int | None = None
    estimated_total_tokens: int | None = None
    worst_case_total_tokens: int | None = None
    worst_case_cost: float | None = None
    currency: str | None = None
    remaining: dict[str, float | int] | None = None
    exceeded_dimensions: list[str] = Field(default_factory=list)
    pricing_version: str | None = None
    estimated: bool = True
    reserved: dict[str, float | int] | None = None


class ProviderWorkflowPrompts(BaseModel):
    boundary_candidate: str
    boundary_adjudication: str
    scene_analysis: str
    thinking: bool
    boundary_confirmation: str


class ProviderStatusResponse(BaseModel):
    capability_schema_version: Literal["1c-a-2"]
    name: str
    default_model: str
    capabilities: ProviderCapabilities
    enabled: bool
    configured: bool
    connected: bool
    healthy: bool
    supports_boundary_candidates: bool
    requires_boundary_review: bool
    automatic_boundary_routing: bool
    manual_boundary_candidate_eligible: bool
    automatic_route_eligible: bool
    manual_short_task_eligible: bool
    manual_selection_blockers: list[str]
    automatic_route_blockers: list[str]
    allow_auto_route: bool
    workflow_prompts: ProviderWorkflowPrompts | None
    running: bool | None
    status: str
    detail: str | None
    eligible_for_automatic_analysis: bool
    eligibility_status: Literal["eligible", "blocked", "unknown"]
    evaluated_at: str
    health_state: Literal["healthy", "unhealthy", "unknown", "stale"]
    health_source: str
    health_checked_at: str | None
    provider_state_version: str


class SceneAnalysisPreflightResponse(BaseModel):
    analysis_mode: Literal["assisted_boundary_review"] = "assisted_boundary_review"
    stage: Literal["scene_analysis"] = "scene_analysis"
    scene_count: int
    expected_request_count: int
    worst_case_request_count: int
    estimated_input_tokens: int
    worst_case_input_tokens: int
    estimated_output_tokens: int
    worst_case_output_tokens: int
    estimated_total_tokens: int
    worst_case_total_tokens: int
    estimated_cost: float
    worst_case_cost: float
    currency: str
    remaining: dict[str, float | int]
    reserved: dict[str, float | int]
    within_budget: bool
    exceeded_dimensions: list[str]
    pricing_version: str | None
    estimated: bool = True


class BoundaryConfirmResponse(BaseModel):
    revision_id: int
    revision_number: int
    scene_count: int
    coverage_rate: float
    run_status: str
    scene_analysis_started: bool
    budget_blocked: bool = False
    stage: str | None = None
    required: dict[str, float | int] | None = None
    remaining: dict[str, float | int] | None = None
    exceeded_dimensions: list[str] = Field(default_factory=list)
    user_action_hint: str | None = None


class AnalysisRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_type: str
    subject_type: str
    subject_id: str
    provider: str
    model: str
    status: str
    progress_current: int
    progress_total: int
    error_code: str | None
    error_message: str | None
    root_error_code: str | None
    root_error_message: str | None
    failed_stage: str | None
    failed_invocation_id: int | None
    provider_health_at_failure: str | None
    retryable: bool
    user_action_hint: str | None
    retry_of_run_id: int | None
    created_at: datetime
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    execution_mode: str
    analysis_mode: str
    cloud_consent: bool
    cloud_consent_at: datetime | None
    sends_content_to_cloud: bool
    budget_required: dict[str, float | int] | None = None
    budget_remaining: dict[str, float | int] | None = None
    exceeded_dimensions: list[str] | None = None
    reservation_status: str | None = None
    current_stage: str | None = None
    failure_details: dict | None = None
    legacy_classification_warning: bool = False
    exception_type: str | None = None
    transport_kind: str | None = None
    actual_failed_stage: str | None = None
    failed_invocation: dict | None = None
    validation_error_code: str | None = None
    failed_transition_id: str | None = None
    failed_batch_index: int | None = None
    reusable_checkpoint_count: int = 0
    conflicted_checkpoint_count: int = 0
    checkpoint_total_count: int = 0
    checkpoint_available: bool = False
    recovered_from_run_id: int | None = None
    scene_analysis_resume_available: bool = False
    detection_recovery_available: bool = False
    remaining_detection_batch_count: int = 0
    boundary_revision_id: int | None = None
    total_scene_count: int = 0
    completed_scene_count: int = 0
    remaining_scene_count: int = 0
    failed_scene_id: int | None = None
    failed_scene_index: int | None = None
    historical_failed_scene_id: int | None = None
    historical_failed_scene_index: int | None = None
    historical_failed_invocation_id: int | None = None
    scene_analysis_coverage_rate: float | None = None
    offline_replay_available: bool = False
    failed_scene_http_attempts: int = 0
    scene_analysis_max_http_attempts: int = 4
    completed_scene_ids: list[int] = Field(default_factory=list)
    remaining_scene_ids: list[int] = Field(default_factory=list)
    scene_validation_detail: dict | None = None
    chapter_complete: bool = False
    scene_pipeline_complete: bool = False
    effective_status: str | None = None
    checkpoint_stage: str | None = None
    resume_stage: str | None = None
    journey_run_id: int | None = None
    journey_status: str | None = None


class SceneAnalysisOfflineReplayRequest(BaseModel):
    scene_id: int | None = None
    invocation_id: int | None = None
    confirmed: bool = True
    client_request_id: str | None = Field(default=None, min_length=8, max_length=64)


class SceneAnalysisOfflineReplayResponse(BaseModel):
    run_id: int
    scene_id: int
    artifact_id: int
    invocation_id: int
    status: str
    completed_scene_count: int
    remaining_scene_count: int
    remaining_scene_ids: list[int] = Field(default_factory=list)
    offline_replay_available: bool = False
    idempotent_replay: bool = False
    message: str
    http_request_sent: bool = False
    request_id: str | None = None


class SceneAnalysisResumePreflightRequest(BaseModel):
    cloud_consent: bool = False


class SceneAnalysisResumePreflightResponse(BaseModel):
    run_id: int
    boundary_revision_id: int | None
    total_scene_count: int
    completed_scene_count: int
    remaining_scene_count: int
    remaining_scene_ids: list[int] = Field(default_factory=list)
    expected_requests: int
    worst_case_requests: int
    estimated_tokens: int
    worst_case_tokens: int
    estimated_cost: float
    worst_case_cost: float
    remaining_budget: dict[str, float | int] = Field(default_factory=dict)
    within_budget: bool
    exceeded_dimensions: list[str] = Field(default_factory=list)
    provider_state_version: str
    provider_name: str
    eligible: bool
    blockers: list[str] = Field(default_factory=list)
    requires_cloud_consent: bool = True
    estimated: bool = True
    currency: str = "CNY"
    coverage_rate: float | None = None


class SceneAnalysisResumeRequest(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=64)
    cloud_consent: bool = False
    confirmed: bool = False
    provider_state_version: str | None = None



class BoundaryRecoveryContinueRequest(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=64)
    cloud_consent: bool = False
    confirmed: bool = False
    provider_state_version: str | None = None


class BoundaryRecoveryPreflightRequest(BaseModel):
    cloud_consent: bool = False


class BoundaryRecoveryPreflightResponse(BaseModel):
    source_run_id: int
    chapter_id: int
    recovered_batch_count: int
    total_detection_batch_count: int
    remaining_detection_batch_count: int
    semantic_conflict_count: int
    expected_request_count: int
    worst_case_request_count: int
    estimated_total_tokens: int
    worst_case_total_tokens: int
    estimated_cost: float
    worst_case_cost: float
    currency: str
    pricing_version: str | None
    remaining: dict[str, float | int]
    within_budget: bool
    exceeded_dimensions: list[str] = Field(default_factory=list)
    requires_cloud_consent: bool
    creates_new_run: bool = True
    existing_recovery_run_id: int | None = None
    blockers: list[str] = Field(default_factory=list)


class BoundaryRecoverPreflightResponse(BaseModel):
    source_run_id: int
    provider_name: str
    eligible: bool
    blockers: list[str] = Field(default_factory=list)
    provider_state_version: str
    capability_schema_version: str = "1c-a-2"
    health_state: str
    health_source: str
    reused_batch_count: int
    remaining_batch_count: int
    expected_requests: int
    worst_case_requests: int
    estimated_tokens: int
    worst_case_tokens: int
    estimated_cost: float
    worst_case_cost: float
    currency: str
    remaining_budget: dict[str, float | int]
    within_budget: bool
    exceeded_dimensions: list[str] = Field(default_factory=list)
    requires_cloud_consent: bool = True


class AnalysisRunAccepted(BaseModel):
    run_id: int
    status: str


class BoundaryRecoveryContinueResponse(BaseModel):
    run_id: int
    recovered_from_run_id: int
    status: str
    reused_batch_count: int
    remaining_batch_count: int
    reservation_id: int | None = None
    request_id: str | None = None
    idempotent_replay: bool = False


class SceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scene_key: str
    book_id: int
    chapter_id: int
    ordinal: int
    start_paragraph_id: str
    end_paragraph_id: str
    created_by_run_id: int
    boundary_confidence: float
    boundary_detected: bool


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    artifact_type: str
    subject_type: str
    subject_id: str
    payload_json: str
    confidence: float
    validation_status: str


class SceneEvidenceItem(BaseModel):
    field_path: str
    group: str
    paragraph_id: str
    in_scope: bool
    order_index: int


class SceneResultScene(BaseModel):
    id: int
    scene_key: str
    ordinal: int
    start_paragraph_id: str
    end_paragraph_id: str
    paragraph_count: int
    is_single_paragraph: bool
    boundary_source: str | None = None
    boundary_revision_id: int | None = None
    boundary_detected: bool = False
    boundary_confidence: float = 0.0


class SceneResultArtifact(BaseModel):
    id: int
    schema_version: str
    prompt_version: str
    provider: str
    model: str
    confidence: float
    validation_status: str
    created_at: datetime | None = None
    offline_recovered: bool = False
    analysis: dict


class SceneResultItem(BaseModel):
    scene: SceneResultScene
    analysis_artifact: SceneResultArtifact | None = None
    evidence: list[SceneEvidenceItem] = Field(default_factory=list)
    illegal_evidence: list[dict] = Field(default_factory=list)
    revision: dict | None = None


class RunResultsSummary(BaseModel):
    total_scene_count: int
    coverage_rate: float | None = None
    single_paragraph_scene_count: int
    longest_scene_ordinal: int | None = None
    longest_scene_paragraph_count: int
    manual_added_boundary_count: int
    model_accepted_boundary_count: int
    user_accepted_conflict_count: int
    artifact_coverage_rate: float
    evidence_coverage_rate: float
    offline_recovered_scene_count: int


class RunResultsRunInfo(BaseModel):
    id: int
    status: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    analysis_mode: str
    execution_mode: str
    completed_at: datetime | None = None


class RunResultsChapterInfo(BaseModel):
    id: int
    book_id: int
    chapter_index: int
    title: str
    display_title: str | None = None


class RunResultsBoundaryRevisionInfo(BaseModel):
    id: int
    revision_number: int
    coverage_rate: float
    confirmed_by: str
    confirmed_at: datetime | None = None


class RunResultsResponse(BaseModel):
    run: RunResultsRunInfo
    chapter: RunResultsChapterInfo
    boundary_revision: RunResultsBoundaryRevisionInfo | None = None
    summary: RunResultsSummary
    scenes: list[SceneResultItem] = Field(default_factory=list)


class SceneParagraphItem(BaseModel):
    id: str
    paragraph_index: int
    raw_text: str
    in_scene: bool


class SceneParagraphsResponse(BaseModel):
    scene_id: int
    scene_key: str
    ordinal: int
    start_paragraph_id: str
    end_paragraph_id: str
    paragraphs: list[SceneParagraphItem] = Field(default_factory=list)


class ModelInvocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_type: str
    provider_name: str
    model_name: str
    attempt_no: int
    invocation_kind: str
    status: str
    latency_ms: int
    error_code: str | None
    error_message: str | None
    http_status_code: int | None
    response_model_name: str | None
    structured_output_mode: str | None
    schema_hash: str | None
    grammar_hash: str | None
    thinking_enabled: bool
    thinking_control_method: str | None
    is_cloud: bool
    cloud_provider: str | None
    cloud_region: str | None
    sends_content_to_cloud: bool
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cached_tokens: int | None
    request_id: str | None
    estimated_cost: float | None
    currency: str | None
    pricing_version: str | None
    raw_logging_enabled: bool
    content_hash: str | None
    candidate_transition_count: int | None
    selected_transition_ids_json: str | None
    mapped_after_paragraph_ids_json: str | None
    rejected_transition_ids_json: str | None
    rejected_transition_classifications_json: str | None
    transition_contract_version: str | None
    canonical_schema_hash: str | None
    created_at: datetime
    raw_response_text: str | None = None
    input_snapshot_json: str | None = None
