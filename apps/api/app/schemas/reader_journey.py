"""Reader Journey Pydantic contracts — single source for prompts and validation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONTRACT_VERSION = "1.3"
SCENE_CONTRACT_VERSION = "1.3"
CHAPTER_CONTRACT_VERSION = "1.2"
SCENE_PROMPT_VERSION = "v1.6"
CHAPTER_PROMPT_VERSION = "v1.2"
REPAIR_PROMPT_VERSION = "v1"
SCENE_CONTRACT_MAJOR = "1"

ReaderQuestionSource = Literal["carried_from_previous"]
QuestionOrigin = Literal["carried", "created_here", "transformed"]
AnswerDegree = Literal["partial", "full", "misleading"]
HookType = Literal[
    "identity",
    "danger",
    "information",
    "goal",
    "relationship",
    "world_rule",
    "space_threshold",
    "other",
]
PayoffType = Literal[
    "goal",
    "information",
    "emotion",
    "identity",
    "relationship",
    "rule",
    "horror_payoff",
    "stage_completion",
    "counterattack",
    "relief",
    "other",
]
JourneyNodeRole = Literal["primary", "beat", "secondary"]
RiskType = Literal[
    "slow_progress",
    "weak_hook",
    "over_explanation",
    "repetition",
    "fragmented_scene",
    "low_payoff",
    "high_cognitive_load",
    "consecutive_no_payoff",
    "other",
]
InfoChangeType = Literal[
    "new_information",
    "confirmation",
    "misdirection",
    "foreshadowing",
    "payoff",
    "identity_clue",
    "rule_clue",
]
Certainty = Literal["fact", "supported_inference", "speculation"]
CharacterEffectMethod = Literal[
    "action",
    "dialogue",
    "choice",
    "contrast",
    "reaction",
    "memory",
    "other",
]

ReaderJourneyRunStatus = Literal[
    "queued",
    "scene_profiles_running",
    "scene_profiles_partial",
    "chapter_synthesis_running",
    "succeeded",
    "failed",
    "budget_blocked",
    "cancelled",
]


def _require_text_len(value: str, *, field_name: str, max_chars: int) -> str:
    text = value.strip() if isinstance(value, str) else value
    if not isinstance(text, str):
        raise ValueError(f"{field_name} must be a string")
    if len(text) > max_chars:
        raise ValueError(f"{field_name} exceeds {max_chars} characters")
    return text


class ReaderQuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(max_length=160)
    source: ReaderQuestionSource
    confidence: float = Field(ge=0, le=1)

    @field_validator("question")
    @classmethod
    def _question_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="question", max_chars=160)

    @field_validator("source")
    @classmethod
    def _reject_created_in_scene(cls, value: str) -> str:
        if value == "created_in_scene":
            raise ValueError("created_in_scene must use reader_question_created, not reader_question_in")
        return value


class ReaderQuestionCreated(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(max_length=160)
    trigger_summary: str = Field(max_length=160)
    strength: int = Field(ge=0, le=100)
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=2)

    @field_validator("question", "trigger_summary")
    @classmethod
    def _created_text_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="text", max_chars=160)


class ReaderQuestionAnswered(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(max_length=160)
    answer_summary: str = Field(max_length=160)
    answer_degree: AnswerDegree
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("question", "answer_summary")
    @classmethod
    def _answered_text_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="text", max_chars=160)


class ReaderQuestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(max_length=160)
    origin: QuestionOrigin
    strength: int = Field(ge=0, le=100)
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=8)
    hook_type: HookType = "other"

    @field_validator("question")
    @classmethod
    def _out_question_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="question", max_chars=160)


class PayoffItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: PayoffType
    summary: str = Field(max_length=160)
    strength: int = Field(ge=0, le=100)
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("summary")
    @classmethod
    def _payoff_summary_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="summary", max_chars=160)


class HookItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: HookType
    summary: str = Field(max_length=160)
    strength: int = Field(ge=0, le=100)
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=8)
    # 已知—缺口—继续动力—下一场承接（v1.3；旧 payload 可缺省，由离线校准补全）
    known: str = Field(default="", max_length=80)
    gap: str = Field(default="", max_length=80)
    continue_drive: str = Field(default="", max_length=80)
    next_handoff: str = Field(default="", max_length=80)

    @field_validator("summary")
    @classmethod
    def _hook_summary_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="summary", max_chars=160)

    @field_validator("known", "gap", "continue_drive", "next_handoff")
    @classmethod
    def _hook_structure_len(cls, value: str) -> str:
        text = value.strip() if isinstance(value, str) else ""
        if len(text) > 80:
            raise ValueError("hook structure field exceeds 80 characters")
        return text


class TechniqueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(max_length=64)
    name: str = Field(max_length=80)
    mechanism: str = Field(max_length=180)
    reader_effect: str = Field(max_length=120)
    transfer_formula: str = Field(default="", max_length=160)
    risk: str = Field(default="", max_length=120)
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("mechanism")
    @classmethod
    def _mechanism_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="mechanism", max_chars=180)

    @field_validator("reader_effect")
    @classmethod
    def _reader_effect_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="reader_effect", max_chars=120)

    @field_validator("transfer_formula")
    @classmethod
    def _transfer_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="transfer_formula", max_chars=160)

    @field_validator("risk")
    @classmethod
    def _risk_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="risk", max_chars=120)


class RiskPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: RiskType
    summary: str = Field(max_length=160)
    severity: int = Field(ge=0, le=100)
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("summary")
    @classmethod
    def _risk_summary_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="summary", max_chars=160)


class EmotionBeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(max_length=80)
    valence: int = Field(ge=-100, le=100)
    arousal: int = Field(ge=0, le=100)
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=8)


class InformationChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: InfoChangeType
    summary: str = Field(max_length=160)
    certainty: Certainty
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("summary")
    @classmethod
    def _info_summary_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="summary", max_chars=160)


class CharacterEffect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    character_name: str = Field(max_length=80)
    trait_or_change: str = Field(max_length=160)
    method: CharacterEffectMethod
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("trait_or_change")
    @classmethod
    def _trait_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="trait_or_change", max_chars=160)


class WritingTakeaway(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(max_length=160)
    applicable_when: str = Field(default="", max_length=120)
    avoid_when: str = Field(default="", max_length=120)

    @field_validator("summary")
    @classmethod
    def _takeaway_summary_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="summary", max_chars=160)


class SceneReaderJourneyProfileItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: int
    scene_ordinal: int
    scene_value_summary: str = Field(max_length=160)
    reader_question_in: list[ReaderQuestionIn] = Field(default_factory=list, max_length=2)
    reader_question_created: list[ReaderQuestionCreated] = Field(
        default_factory=list, max_length=2
    )
    reader_question_answered: list[ReaderQuestionAnswered] = Field(
        default_factory=list, max_length=2
    )
    reader_question_out: list[ReaderQuestionOut] = Field(default_factory=list, max_length=2)
    dominant_emotion: str = Field(max_length=80)
    emotional_valence_start: int = Field(default=0, ge=-100, le=100)
    emotional_valence_end: int = Field(default=0, ge=-100, le=100)
    arousal_start: int = Field(default=0, ge=0, le=100)
    arousal_end: int = Field(default=0, ge=0, le=100)
    curiosity_score: int = Field(ge=0, le=100)
    tension_score: int = Field(ge=0, le=100)
    payoff_score: int = Field(ge=0, le=100)
    hook_score: int = Field(ge=0, le=100)
    information_gain_score: int = Field(ge=0, le=100)
    emotional_resonance_score: int = Field(ge=0, le=100)
    cognitive_load_score: int = Field(ge=0, le=100)
    dropoff_risk_score: int = Field(ge=0, le=100)
    payoffs: list[PayoffItem] = Field(default_factory=list, max_length=2)
    hooks: list[HookItem] = Field(default_factory=list, max_length=2)
    techniques: list[TechniqueItem] = Field(default_factory=list, max_length=3)
    risk_points: list[RiskPoint] = Field(default_factory=list, max_length=2)
    emotion_beats: list[EmotionBeat] = Field(default_factory=list, max_length=4)
    information_changes: list[InformationChange] = Field(default_factory=list, max_length=3)
    character_effects: list[CharacterEffect] = Field(default_factory=list, max_length=2)
    writing_takeaways: list[WritingTakeaway] = Field(default_factory=list, max_length=2)
    confidence: float = Field(ge=0, le=1)
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("scene_value_summary")
    @classmethod
    def _summary_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="scene_value_summary", max_chars=160)

    @field_validator("evidence_paragraph_ids")
    @classmethod
    def _evidence_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_paragraph_ids must be unique")
        return value


class SceneReaderJourneyBatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str = CONTRACT_VERSION
    profiles: list[SceneReaderJourneyProfileItem]


class ReaderJourneyPhaseItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordinal: int = Field(ge=1)
    title: str
    start_scene_ordinal: int = Field(ge=1)
    end_scene_ordinal: int = Field(ge=1)
    primary_reader_question: str
    dominant_emotion: str
    reading_payoff: str
    continuation_motivation: str
    summary: str
    confidence: float = Field(ge=0, le=1)


class ChapterReaderJourneySynthesisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str = CHAPTER_CONTRACT_VERSION
    phases: list[ReaderJourneyPhaseItem]
    chapter_reader_question_chain: list[str] = Field(default_factory=list)
    pacing_diagnosis: list[str] = Field(default_factory=list)
    chapter_strengths: list[str] = Field(default_factory=list)
    chapter_risks: list[str] = Field(default_factory=list)
    one_sentence_diagnosis: str = ""


class EngagementBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")
    curiosity: int
    tension: int
    hook: int
    payoff: int
    information_gain: int
    emotional_resonance: int
    cognitive_load: int
    dropoff_risk: int
    engagement_score: int
    formula_version: str
    genre: str
    weights: dict[str, float]


class ReaderJourneyPreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_name: str | None = None
    cloud_consent: bool = False


class ReaderJourneyPreflightResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_run_id: int
    total_scenes: int
    remaining_scenes: int
    scene_batch_count: int
    expected_requests: int
    worst_case_requests: int
    estimated_tokens: int
    worst_case_tokens: int
    estimated_cost: float
    worst_case_cost: float
    within_budget: bool
    exceeded_dimensions: list[str]
    pricing_version: str | None
    provider_state_version: str
    provider_name: str
    eligible: bool
    blockers: list[str]
    requires_cloud_consent: bool
    currency: str
    estimated: bool = True
    stage1_scene_profiles: dict[str, object]
    stage2_chapter_synthesis: dict[str, object]
    planner_version: str | None = None
    scene_prompt_version: str | None = None
    scene_contract_version: str | None = None
    pipeline_id: str | None = None
    source_mode: str | None = None
    batch_plan: list[str] = Field(default_factory=list)
    recovery_mode: bool = False
    existing_journey_run_id: int | None = None


class ReaderJourneyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: str
    cloud_consent: bool
    provider_name: str | None = None
    provider_state_version: str | None = None
    confirmed: bool = True
    force_new_version: bool = False

    @field_validator("client_request_id")
    @classmethod
    def _strip_client_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("client_request_id required")
        return text


class ReaderJourneyRunAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journey_run_id: int
    status: str
    existing_journey_run_id: int | None = None
    idempotent_replay: bool = False
    recovery_recommended: bool = False
    creation_blocked_reason: str | None = None


class ReaderJourneyResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: str
    cloud_consent: bool
    provider_state_version: str | None = None
    confirmed: bool = True


class ReaderJourneyProgressResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journey_run_id: int
    analysis_run_id: int
    status: str
    current_stage: str | None
    total_scene_count: int
    completed_scene_count: int
    remaining_scene_count: int
    completed_scene_ids: list[int]
    remaining_scene_ids: list[int]
    phase_count: int
    has_chapter_summary: bool
    retryable: bool
    failed_stage: str | None = None
    root_error_code: str | None = None
    root_error_message: str | None = None
    failed_scene_id: int | None = None
    failed_scene_ordinal: int | None = None
    failed_invocation_id: int | None = None
    completed_at: datetime | None = None
    planner_version: str | None = None
    current_planner_version: str | None = None
    scene_prompt_version: str | None = None
    scene_contract_version: str | None = None
    recovery_safe: bool = False
    blind_resume_blocked: bool = False
    resume_block_reason: str | None = None
    reservation_released: bool = False
    request_count: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    currency: str = "CNY"
    failure_details: dict[str, object] | None = None
    resume_preflight: dict[str, object] | None = None
    user_error_message: str | None = None
    offline_replay_available: bool = False
    offline_replayable_scene_count: int = 0
    offline_replayable_invocation_ids: list[int] = Field(default_factory=list)
    current_contract_version: str | None = None
    recoverable_contract_version: str | None = None


class ReaderJourneyOfflineReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invocation_ids: list[int] | None = None
    confirmed: bool = True


class ReaderJourneyOfflineReplayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journey_run_id: int
    replayed_scene_ids: list[int] = Field(default_factory=list)
    completed_count: int = 0
    remaining_count: int = 0
    source_invocation_ids: list[int] = Field(default_factory=list)
    migrated_from_contract_version: str | None = None
    current_contract_version: str = SCENE_CONTRACT_VERSION
    http_requests: int = 0
    tokens: int = 0
    cost: float = 0.0
    idempotent_replay: bool = False
    errors: list[str] = Field(default_factory=list)


class ReaderJourneySemanticRecalibrateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = True


class ReaderJourneySemanticRecalibrateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journey_run_id: int
    calibrated_profile_count: int = 0
    empty_qin_remaining: int = 0
    journey_nodes: list[dict[str, object]] = Field(default_factory=list)
    question_chain_count: int = 0
    one_sentence_diagnosis: str = ""
    scene_contract_version: str = SCENE_CONTRACT_VERSION
    http_requests: int = 0
    tokens: int = 0
    cost: float = 0.0


class ReaderJourneyProfileSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: int
    scene_ordinal: int
    scene_value_summary: str
    dominant_emotion: str
    engagement: EngagementBreakdown
    reader_question_in: list[str]
    reader_question_out: list[str]
    payoffs: list[str]
    hooks: list[str]
    risk_points: list[str]
    evidence_paragraph_ids: list[str]
    confidence: float


class ReaderJourneyPhaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordinal: int
    title: str
    start_scene_ordinal: int
    end_scene_ordinal: int
    primary_reader_question: str
    dominant_emotion: str
    reading_payoff: str
    continuation_motivation: str
    summary: str
    confidence: float


class ReaderJourneyResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    journey_run_id: int
    analysis_run_id: int
    book_id: int
    chapter_id: int
    status: str
    provider_name: str
    model_name: str
    scene_prompt_version: str
    chapter_prompt_version: str
    formula_version: str
    scene_contract_version: str | None = None
    contract_version: str | None = None
    calibration_status_label: str | None = None
    legacy_uncalibrated: bool = False
    display_mode: str | None = None
    phases: list[ReaderJourneyPhaseSummary]
    scene_profiles: list[ReaderJourneyProfileSummary]
    chapter_summary: dict[str, object] | None = None
    deterministic_statistics: dict[str, object] | None = None
    one_sentence_diagnosis: str | None = None
    visualization: dict[str, object] | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    # v2.0 optional payload (present only for contract 2.x runs; never auto-billed).
    v2_question_lifecycle: list[dict[str, object]] | None = None
    v2_scene_diagnoses: list[dict[str, object]] | None = None
