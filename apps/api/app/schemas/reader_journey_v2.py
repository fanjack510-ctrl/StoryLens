"""Reader Journey v2.0 Pydantic contracts — independent from v1.3 / prompt v1.6."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION_V2 = "2.0"
SCENE_CONTRACT_VERSION_V2 = "2.0"
CHAPTER_CONTRACT_VERSION_V2 = "2.0"
SCENE_PROMPT_VERSION_V2 = "v2.0"
CHAPTER_PROMPT_VERSION_V2 = "v2.0"
SCENE_CONTRACT_MAJOR_V2 = "2"
FORMULA_VERSION_V2 = "2.0"
SCENE_ROLE_TARGETS_VERSION = "1.0"

LEGACY_CONTRACT_VERSIONS = frozenset({"1.0", "1.1", "1.2", "1.3"})
LEGACY_PROMPT_PREFIXES = ("v1",)

NodeTypeV2 = Literal["scene", "beat"]
SceneRoleV2 = Literal[
    "setup",
    "escalation",
    "investigation",
    "reveal",
    "climax",
    "aftermath",
    "transition",
    "open_end",
    "closed_end",
]
QuestionLifecycleStatus = Literal[
    "open",
    "progressing",
    "paid_off",
    "abandoned",
    "overdue",
]
DiagnosisCode = Literal[
    "plot_stagnation",
    "empty_fast_pacing",
    "weak_progress",
    "pacing_too_slow",
    "pacing_too_fast",
    "information_overload",
    "weak_curiosity",
    "weak_tension",
    "weak_emotional_investment",
    "suspended_tension",
    "tension_overload",
    "weak_hook",
    "empty_hook",
    "delayed_payoff",
    "abrupt_reveal",
    "effective_payoff",
    "unclear_expression",
    "scene_boundary_anomaly",
    "low_confidence",
]
DiagnosisSeverity = Literal["info", "low", "medium", "high", "critical"]

LEVEL_METRIC_KEYS = (
    "goal_progress",
    "conflict_change",
    "state_change",
    "information_gain",
    "character_agency",
    "causal_coherence",
    "curiosity",
    "tension",
    "emotional_investment",
    "pacing_speed",
    "hook",
    "payoff",
    "setup_consistency",
    "question_lifecycle",
    "emotional_valence_start",
    "emotional_valence_end",
    "arousal_start",
    "arousal_end",
    "clarity",
    "cognitive_load",
    "redundancy",
)


def _require_text_len(value: str, *, field_name: str, max_chars: int) -> str:
    text = value.strip() if isinstance(value, str) else value
    if not isinstance(text, str):
        raise ValueError(f"{field_name} must be a string")
    if len(text) > max_chars:
        raise ValueError(f"{field_name} exceeds {max_chars} characters")
    return text


class DimensionInsightsV2(BaseModel):
    """Optional per-dimension scene insight texts (model-generated or persisted)."""

    model_config = ConfigDict(extra="forbid")
    overall_reading: str | None = Field(default=None, max_length=160)
    plot_progression: str | None = Field(default=None, max_length=160)
    reading_tension: str | None = Field(default=None, max_length=160)
    emotional_intensity: str | None = Field(default=None, max_length=160)
    hook_payoff: str | None = Field(default=None, max_length=160)
    pacing_speed: str | None = Field(default=None, max_length=160)

    @field_validator(
        "overall_reading",
        "plot_progression",
        "reading_tension",
        "emotional_intensity",
        "hook_payoff",
        "pacing_speed",
    )
    @classmethod
    def _insight_len(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_text_len(value, field_name="dimension_insight", max_chars=160)


class ScoredLevelField(BaseModel):
    """Model emits level only; mapped_score is program-derived."""

    model_config = ConfigDict(extra="forbid")
    level: int = Field(ge=0, le=5)
    mapped_score: int | None = Field(default=None, ge=0, le=100)
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=8)
    rationale: str = Field(default="", max_length=200)
    confidence: float = Field(ge=0, le=1)

    @field_validator("rationale")
    @classmethod
    def _rationale_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="rationale", max_chars=200)

    @field_validator("evidence_paragraph_ids")
    @classmethod
    def _evidence_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_paragraph_ids must be unique")
        return value


class SceneReaderJourneyProfileItemV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: int
    scene_ordinal: int
    node_type: NodeTypeV2 = "scene"
    scene_role: SceneRoleV2
    scene_value_summary: str = Field(max_length=160)
    goal_progress: ScoredLevelField
    conflict_change: ScoredLevelField
    state_change: ScoredLevelField
    information_gain: ScoredLevelField
    character_agency: ScoredLevelField
    causal_coherence: ScoredLevelField
    curiosity: ScoredLevelField
    tension: ScoredLevelField
    emotional_investment: ScoredLevelField
    pacing_speed: ScoredLevelField
    hook: ScoredLevelField
    payoff: ScoredLevelField
    setup_consistency: ScoredLevelField
    question_lifecycle: ScoredLevelField
    emotional_valence_start: ScoredLevelField
    emotional_valence_end: ScoredLevelField
    arousal_start: ScoredLevelField
    arousal_end: ScoredLevelField
    clarity: ScoredLevelField
    cognitive_load: ScoredLevelField
    redundancy: ScoredLevelField
    confidence: float = Field(ge=0, le=1)
    evidence_paragraph_ids: list[str] = Field(default_factory=list, max_length=16)
    # Program-derived fields (optional on model output; filled by derivation).
    plot_progress: float | None = None
    reading_tension: float | None = None
    pacing_fit: float | None = None
    hook_payoff_fit: float | None = None
    reading_momentum: float | None = None
    dropoff_risk: float | None = None
    include_in_main_curve: bool | None = None
    include_in_chapter_mean: bool | None = None
    data_quality_issue: str | None = None
    # Fit availability (CHG-20260727-013). Null/absent on legacy artifacts.
    pacing_fit_status: Literal["ok", "unavailable"] | None = None
    pacing_fit_reason_code: str | None = None
    hook_payoff_fit_status: Literal["ok", "unavailable"] | None = None
    hook_payoff_fit_reason_code: str | None = None
    # Optional model-generated per-dimension insights (absent on legacy artifacts).
    dimension_insights: DimensionInsightsV2 | None = None
    # Persistence/integrity metadata written by pipeline; not model output.
    source_context_fingerprint: str | None = None

    @field_validator("scene_value_summary")
    @classmethod
    def _summary_len(cls, value: str) -> str:
        return _require_text_len(value, field_name="scene_value_summary", max_chars=160)

    @field_validator("evidence_paragraph_ids")
    @classmethod
    def _top_evidence_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_paragraph_ids must be unique")
        return value

    @model_validator(mode="after")
    def _beat_defaults(self) -> SceneReaderJourneyProfileItemV2:
        if self.node_type == "beat":
            object.__setattr__(self, "include_in_main_curve", False)
            object.__setattr__(self, "include_in_chapter_mean", False)
        elif self.include_in_main_curve is None:
            object.__setattr__(self, "include_in_main_curve", True)
            object.__setattr__(self, "include_in_chapter_mean", True)
        return self


class SceneReaderJourneyBatchResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str = SCENE_CONTRACT_VERSION_V2
    profiles: list[SceneReaderJourneyProfileItemV2]


class QuestionLifecycleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    question_text: str = Field(max_length=200)
    setup_scene: int
    development_scenes: list[int] = Field(default_factory=list)
    payoff_scene: int | None = None
    status: QuestionLifecycleStatus
    strength: int = Field(default=50, ge=0, le=100)


class DiagnosticEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_ordinals: list[int] = Field(default_factory=list)
    metric_keys: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=240)


class SceneDiagnosisV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_ordinal: int
    primary_diagnosis: DiagnosisCode | None = None
    secondary_diagnoses: list[DiagnosisCode] = Field(default_factory=list, max_length=4)
    positive_mechanism: DiagnosisCode | None = None
    severity: DiagnosisSeverity = "info"
    diagnostic_evidence: DiagnosticEvidence = Field(default_factory=DiagnosticEvidence)
    confidence: float = Field(ge=0, le=1, default=0.5)
    data_quality_issue: str | None = None


class ChapterReaderJourneySynthesisResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str = CHAPTER_CONTRACT_VERSION_V2
    chapter_reader_question_chain: list[str] = Field(default_factory=list)
    question_lifecycle: list[QuestionLifecycleRecord] = Field(default_factory=list)
    scene_diagnoses: list[SceneDiagnosisV2] = Field(default_factory=list)
    pacing_diagnosis: list[str] = Field(default_factory=list)
    chapter_strengths: list[str] = Field(default_factory=list)
    chapter_risks: list[str] = Field(default_factory=list)
    one_sentence_diagnosis: str = ""
    average_reading_momentum: float | None = None


class DerivedMetricsV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plot_progress: float
    reading_tension: float
    pacing_fit: float | None = None
    hook_payoff_fit: float | None = None
    clarity_penalty: float
    cognitive_load_penalty: float
    redundancy_penalty: float
    reading_momentum: float
    dropoff_risk: float
    formula_version: str = FORMULA_VERSION_V2
