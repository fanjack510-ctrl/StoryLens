from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_file_name: Mapped[str] = mapped_column(String(500))
    source_file_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    import_status: Mapped[str] = mapped_column(String(32), default="imported")
    language: Mapped[str] = mapped_column(String(32), default="zh-CN")
    source_content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    import_diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")
    import_warning: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revision_of_book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    fixture_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fixture_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="book", cascade="all, delete-orphan", order_by="Chapter.chapter_index"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    chapter_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    start_paragraph_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    end_paragraph_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    section_type: Mapped[str] = mapped_column(String(32), default="chapter")
    chapter_number_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chapter_number_normalized: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chapter_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    chapter_title: Mapped[str] = mapped_column(String(500), default="")
    display_title: Mapped[str] = mapped_column(String(600), default="")
    source_title_line: Mapped[str] = mapped_column(String(600), default="")
    # Phase 1P: persisted chapter text hash (nullable until Agent A backfill).
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    book: Mapped[Book] = relationship(back_populates="chapters")
    paragraphs: Mapped[list["Paragraph"]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan", order_by="Paragraph.paragraph_index"
    )


class ReparseAudit(Base):
    __tablename__ = "reparse_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    strategy: Mapped[str] = mapped_column(String(32))
    old_chapter_count: Mapped[int] = mapped_column(Integer)
    new_chapter_count: Mapped[int] = mapped_column(Integer)
    old_file_hash: Mapped[str] = mapped_column(String(64))
    new_file_hash: Mapped[str] = mapped_column(String(64))
    parsing_rule_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)



class Paragraph(Base):
    __tablename__ = "paragraphs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    paragraph_index: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Phase 1P: persisted paragraph text hash (nullable until Agent A backfill).
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    chapter: Mapped[Chapter] = relationship(back_populates="paragraphs")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(String(100), default="scene_pipeline")
    subject_type: Mapped[str] = mapped_column(String(50), default="chapter")
    subject_id: Mapped[str] = mapped_column(String(100), index=True, default="")
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(50))
    schema_version: Mapped[str] = mapped_column(String(50))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retry_of_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    legacy_started_at: Mapped[datetime] = mapped_column(
        "started_at", DateTime(timezone=True), default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(
        "run_started_at", DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    root_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failed_invocation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_health_at_failure: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[bool] = mapped_column(default=False)
    user_action_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(16), default="local")
    analysis_mode: Mapped[str] = mapped_column(String(40), default="automatic")
    cloud_consent: Mapped[bool] = mapped_column(default=False)
    cloud_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sends_content_to_cloud: Mapped[bool] = mapped_column(default=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    recovered_from_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # CHG-20260729-006 cooperative cancellation (nullable / defaults for legacy rows).
    status_version: Mapped[int] = mapped_column(Integer, default=0)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Phase 1P narrative scope skeleton (nullable for 1.0.5 row compatibility).
    # Legacy chapter binding remains subject_type/subject_id — there is no chapter_id column.
    analysis_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    scope_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    book_id: Mapped[int | None] = mapped_column(
        ForeignKey("books.id", ondelete="SET NULL"), nullable=True, index=True
    )
    start_chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    end_chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    book_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    configuration_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("created_by_run_id", "scene_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scene_key: Mapped[str] = mapped_column(String(40), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    start_paragraph_id: Mapped[str] = mapped_column(ForeignKey("paragraphs.id"))
    end_paragraph_id: Mapped[str] = mapped_column(ForeignKey("paragraphs.id"))
    content_hash: Mapped[str] = mapped_column(String(64))
    created_by_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    boundary_detected: Mapped[bool] = mapped_column(default=False)
    boundary_confidence: Mapped[float] = mapped_column(Float)
    boundary_reason_json: Mapped[str] = mapped_column(Text, default="[]")
    boundary_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("boundary_revisions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    boundary_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    included_in_journey: Mapped[bool] = mapped_column(default=True)
    source_scene_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AnalysisArtifact(Base):
    __tablename__ = "analysis_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(50))
    subject_type: Mapped[str] = mapped_column(String(50))
    subject_id: Mapped[str] = mapped_column(String(100), index=True)
    schema_version: Mapped[str] = mapped_column(String(50))
    prompt_version: Mapped[str] = mapped_column(String(50))
    payload_json: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    validation_status: Mapped[str] = mapped_column(String(32), default="valid")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnalysisEvidence(Base):
    __tablename__ = "analysis_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_artifacts.id", ondelete="CASCADE"), index=True
    )
    field_path: Mapped[str] = mapped_column(String(255))
    paragraph_id: Mapped[str] = mapped_column(ForeignKey("paragraphs.id"), index=True)
    paragraph_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ModelInvocation(Base):
    __tablename__ = "model_invocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    task_type: Mapped[str] = mapped_column(String(100))
    provider_name: Mapped[str] = mapped_column(String(100))
    model_name: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(50))
    schema_version: Mapped[str] = mapped_column(String(50))
    attempt_no: Mapped[int] = mapped_column(Integer)
    invocation_kind: Mapped[str] = mapped_column(String(32), default="initial")
    request_hash: Mapped[str] = mapped_column(String(64))
    input_snapshot_json: Mapped[str] = mapped_column(Text)
    raw_response_text: Mapped[str] = mapped_column(Text)
    parsed_response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[int] = mapped_column(Integer)
    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    structured_output_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grammar_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    thinking_enabled: Mapped[bool] = mapped_column(default=False)
    thinking_control_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_parameters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_cloud: Mapped[bool] = mapped_column(default=False)
    cloud_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cloud_region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sends_content_to_cloud: Mapped[bool] = mapped_column(default=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pricing_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_logging_enabled: Mapped[bool] = mapped_column(default=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_request_sent: Mapped[bool] = mapped_column(default=True, index=True)
    audit_type: Mapped[str] = mapped_column(String(32), default="provider_invocation")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_parameter_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    candidate_transition_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_transition_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapped_after_paragraph_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_transition_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_transition_classifications_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    transition_contract_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    canonical_schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BoundaryDetectionBatchCheckpoint(Base):
    __tablename__ = "boundary_detection_batch_checkpoints"
    __table_args__ = (
        UniqueConstraint("run_id", "batch_index", "prompt_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    batch_index: Mapped[int] = mapped_column(Integer)
    window_index: Mapped[int] = mapped_column(Integer, default=0)
    prompt_version: Mapped[str] = mapped_column(String(50))
    contract_version: Mapped[str] = mapped_column(String(32), default="3.5")
    owned_transition_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    context_paragraph_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    transition_map_json: Mapped[str] = mapped_column(Text, default="{}")
    invocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_invocations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parsed_response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    valid_decisions_json: Mapped[str] = mapped_column(Text, default="[]")
    conflicted_decisions_json: Mapped[str] = mapped_column(Text, default="[]")
    issues_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RequestGateDecision(Base):
    __tablename__ = "request_gate_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    allowed: Mapped[bool] = mapped_column(index=True)
    reason_code: Mapped[str] = mapped_column(String(100))
    budget_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    estimated_request_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CloudBudgetReservation(Base):
    """Cloud budget reservation with initial / remaining / consumed / released ledger.

    Field mapping (DEFECT-UAT-003):
    - reservation_initial_*  → reserved_requests / reserved_tokens / reserved_cost
    - reservation_remaining_* → remaining_requests / remaining_tokens / remaining_cost
    - reservation_consumed_* → consumed_requests / consumed_tokens / consumed_cost
    - reservation_released_* → released_requests / released_tokens / released_cost

    Invariant per dimension:
    initial = remaining + consumed + released (never negative).
    """

    __tablename__ = "cloud_budget_reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    stage: Mapped[str] = mapped_column(String(64), default="legacy", index=True)
    # reservation_initial (immutable after create)
    reserved_requests: Mapped[int] = mapped_column(Integer)
    reserved_tokens: Mapped[int] = mapped_column(Integer)
    reserved_cost: Mapped[float] = mapped_column(Float)
    # reservation_remaining / consumed / released
    remaining_requests: Mapped[int] = mapped_column(Integer, default=0)
    consumed_requests: Mapped[int] = mapped_column(Integer, default=0)
    released_requests: Mapped[int] = mapped_column(Integer, default=0)
    remaining_tokens: Mapped[int] = mapped_column(Integer, default=0)
    consumed_tokens: Mapped[int] = mapped_column(Integer, default=0)
    released_tokens: Mapped[int] = mapped_column(Integer, default=0)
    remaining_cost: Mapped[float] = mapped_column(Float, default=0.0)
    consumed_cost: Mapped[float] = mapped_column(Float, default=0.0)
    released_cost: Mapped[float] = mapped_column(Float, default=0.0)
    expected_requests: Mapped[int] = mapped_column(Integer, default=0)
    worst_case_requests: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProviderConfiguration(Base):
    __tablename__ = "provider_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    region: Mapped[str] = mapped_column(String(64), default="cn-beijing")
    workspace_id: Mapped[str] = mapped_column(String(255), default="")
    base_url: Mapped[str] = mapped_column(String(1000), default="")
    plus_model: Mapped[str] = mapped_column(String(255), default="qwen3.7-plus")
    max_model: Mapped[str] = mapped_column(String(255), default="qwen3.7-max")
    flash_model: Mapped[str] = mapped_column(String(255), default="qwen3.6-flash")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    enabled: Mapped[bool] = mapped_column(default=False)
    disconnected: Mapped[bool] = mapped_column(default=True)
    allow_auto_route: Mapped[bool] = mapped_column(default=False)
    raw_logging_enabled: Mapped[bool] = mapped_column(default=False)
    credential_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ApplicationSetting(Base):
    __tablename__ = "application_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LocalLicense(Base):
    """Offline-verified StoryLens Pro license persisted on this machine only."""

    __tablename__ = "local_licenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    license_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product_code: Mapped[str] = mapped_column(String(64), index=True)
    edition: Mapped[str] = mapped_column(String(32), default="pro")
    major_version: Mapped[int] = mapped_column(Integer)
    license_status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    signed_license: Mapped[str] = mapped_column(Text)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    key_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BoundaryReviewSession(Base):
    __tablename__ = "boundary_review_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    prompt_version: Mapped[str] = mapped_column(String(50))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    manually_added_count: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BoundaryReviewDecision(Base):
    __tablename__ = "boundary_review_decisions"
    __table_args__ = (UniqueConstraint("review_session_id", "transition_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    review_session_id: Mapped[int] = mapped_column(
        ForeignKey("boundary_review_sessions.id", ondelete="CASCADE"), index=True
    )
    transition_id: Mapped[str] = mapped_column(String(64))
    left_paragraph_id: Mapped[str] = mapped_column(ForeignKey("paragraphs.id"))
    right_paragraph_id: Mapped[str] = mapped_column(ForeignKey("paragraphs.id"))
    model_candidate: Mapped[bool] = mapped_column(default=True)
    model_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_pass_json: Mapped[str] = mapped_column(Text, default="{}")
    adjudication_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_priority: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    user_decision: Mapped[str] = mapped_column(String(32), default="pending")
    user_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_boundary: Mapped[bool] = mapped_column(default=False)
    semantic_conflict: Mapped[bool] = mapped_column(default=False, index=True)
    conflict_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    deterministic_legal: Mapped[bool | None] = mapped_column(nullable=True)
    deterministic_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_boundary_candidate: Mapped[bool | None] = mapped_column(nullable=True)
    enum_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    source_batch_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manual_reason_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class BoundaryRevision(Base):
    __tablename__ = "boundary_revisions"
    __table_args__ = (UniqueConstraint("review_session_id", "revision_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    review_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("boundary_review_sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    final_boundaries_json: Mapped[str] = mapped_column(Text)
    confirmed_by: Mapped[str] = mapped_column(String(255))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    coverage_rate: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(32), default="confirmed", index=True)
    source: Mapped[str] = mapped_column(String(32), default="legacy")
    based_on_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("boundary_revisions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chapter_text_hash: Mapped[str] = mapped_column(String(64), default="")
    boundary_hash: Mapped[str] = mapped_column(String(64), default="")
    revision_etag: Mapped[str] = mapped_column(String(64), default="")
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ReaderJourneyRun(Base):
    __tablename__ = "reader_journey_runs"
    __table_args__ = (UniqueConstraint("analysis_run_id", "client_request_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_name: Mapped[str] = mapped_column(String(100))
    model_name: Mapped[str] = mapped_column(String(255))
    scene_prompt_version: Mapped[str] = mapped_column(String(50), default="v1")
    chapter_prompt_version: Mapped[str] = mapped_column(String(50), default="v1")
    scene_contract_version: Mapped[str] = mapped_column(String(32), default="1.0")
    chapter_contract_version: Mapped[str] = mapped_column(String(32), default="1.0")
    formula_version: Mapped[str] = mapped_column(String(32), default="1.0")
    genre: Mapped[str] = mapped_column(String(32), default="suspense")
    planner_version: Mapped[str] = mapped_column(String(32), default="1.0")
    total_scene_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_scene_count: Mapped[int] = mapped_column(Integer, default=0)
    remaining_scene_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_scene_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    remaining_scene_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    root_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    root_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_scene_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_scene_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_invocation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retryable: Mapped[bool] = mapped_column(default=False)
    failure_details_json: Mapped[str] = mapped_column(Text, default="{}")
    cloud_consent: Mapped[bool] = mapped_column(default=False)
    client_request_id: Mapped[str] = mapped_column(String(64), index=True)
    scene_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("boundary_revisions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scene_revision_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scene_boundary_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chapter_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    included_scene_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    included_scene_input_hashes_json: Mapped[str] = mapped_column(Text, default="{}")
    result_status: Mapped[str] = mapped_column(String(48), default="current", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SceneReaderJourneyProfile(Base):
    __tablename__ = "scene_reader_journey_profiles"
    __table_args__ = (UniqueConstraint("reader_journey_run_id", "scene_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reader_journey_run_id: Mapped[int] = mapped_column(
        ForeignKey("reader_journey_runs.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    scene_ordinal: Mapped[int] = mapped_column(Integer)
    scene_value_summary: Mapped[str] = mapped_column(Text)
    dominant_emotion: Mapped[str] = mapped_column(String(100))
    emotional_valence_start: Mapped[int] = mapped_column(Integer, default=0)
    emotional_valence_end: Mapped[int] = mapped_column(Integer, default=0)
    arousal_start: Mapped[int] = mapped_column(Integer, default=0)
    arousal_end: Mapped[int] = mapped_column(Integer, default=0)
    curiosity_score: Mapped[int] = mapped_column(Integer, default=0)
    tension_score: Mapped[int] = mapped_column(Integer, default=0)
    payoff_score: Mapped[int] = mapped_column(Integer, default=0)
    hook_score: Mapped[int] = mapped_column(Integer, default=0)
    information_gain_score: Mapped[int] = mapped_column(Integer, default=0)
    emotional_resonance_score: Mapped[int] = mapped_column(Integer, default=0)
    cognitive_load_score: Mapped[int] = mapped_column(Integer, default=0)
    dropoff_risk_score: Mapped[int] = mapped_column(Integer, default=0)
    engagement_score: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    validation_status: Mapped[str] = mapped_column(String(32), default="valid")
    artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ReaderJourneyPhase(Base):
    __tablename__ = "reader_journey_phases"
    __table_args__ = (UniqueConstraint("reader_journey_run_id", "ordinal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reader_journey_run_id: Mapped[int] = mapped_column(
        ForeignKey("reader_journey_runs.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    start_scene_ordinal: Mapped[int] = mapped_column(Integer)
    end_scene_ordinal: Mapped[int] = mapped_column(Integer)
    primary_reader_question: Mapped[str] = mapped_column(Text)
    dominant_emotion: Mapped[str] = mapped_column(String(100))
    reading_payoff: Mapped[str] = mapped_column(Text)
    continuation_motivation: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ChapterReaderJourneySummary(Base):
    __tablename__ = "chapter_reader_journey_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    reader_journey_run_id: Mapped[int] = mapped_column(
        ForeignKey("reader_journey_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    chapter_value_summary: Mapped[str] = mapped_column(Text, default="")
    chapter_reader_question_chain_json: Mapped[str] = mapped_column(Text, default="[]")
    overall_engagement_score: Mapped[int] = mapped_column(Integer, default=0)
    strongest_hook_scene_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    strongest_payoff_scene_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    risk_scene_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    positive_feedback_distribution_json: Mapped[str] = mapped_column(Text, default="{}")
    hook_distribution_json: Mapped[str] = mapped_column(Text, default="{}")
    emotion_trend_summary: Mapped[str] = mapped_column(Text, default="")
    pacing_diagnosis_json: Mapped[str] = mapped_column(Text, default="[]")
    one_sentence_diagnosis: Mapped[str] = mapped_column(Text, default="")
    deterministic_statistics_json: Mapped[str] = mapped_column(Text, default="{}")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    validation_status: Mapped[str] = mapped_column(String(32), default="valid")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReaderJourneyRevision(Base):
    """Reserved for future manual revisions; originals are never overwritten."""

    __tablename__ = "reader_journey_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    reader_journey_run_id: Mapped[int] = mapped_column(
        ForeignKey("reader_journey_runs.id", ondelete="CASCADE"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    revised_by: Mapped[str] = mapped_column(String(255))
    revision_payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


# ---------------------------------------------------------------------------
# Phase 1P Narrative Intelligence Core shared schema skeleton
# Agents A/B must not redefine these tables; implement services against them.
# ---------------------------------------------------------------------------


class SchemaMigration(Base):
    """Applied narrative / phase migration ledger (Phase 1P)."""

    __tablename__ = "schema_migrations"

    migration_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    app_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.5")
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BookSnapshot(Base):
    __tablename__ = "book_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "book_id",
            "content_hash",
            name="uq_book_snapshots_book_content_hash",
        ),
        Index("ix_book_snapshots_book_status", "book_id", "snapshot_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    paragraph_count: Mapped[int] = mapped_column(Integer, default=0)
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_status: Mapped[str] = mapped_column(String(32), default="building", index=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    chapters: Mapped[list["BookSnapshotChapter"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="BookSnapshotChapter.chapter_order",
    )


class BookSnapshotChapter(Base):
    __tablename__ = "book_snapshot_chapters"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "chapter_order",
            name="uq_book_snapshot_chapters_order",
        ),
        UniqueConstraint(
            "snapshot_id",
            "source_chapter_id",
            name="uq_book_snapshot_chapters_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), index=True
    )
    source_chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chapter_order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(600), default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    snapshot: Mapped[BookSnapshot] = relationship(back_populates="chapters")
    paragraphs: Mapped[list["BookSnapshotParagraph"]] = relationship(
        back_populates="snapshot_chapter",
        cascade="all, delete-orphan",
        order_by="BookSnapshotParagraph.paragraph_order",
    )


class BookSnapshotParagraph(Base):
    __tablename__ = "book_snapshot_paragraphs"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_chapter_id",
            "paragraph_order",
            name="uq_book_snapshot_paragraphs_order",
        ),
        CheckConstraint("start_offset >= 0", name="ck_bsp_start_offset_nonneg"),
        CheckConstraint("end_offset >= start_offset", name="ck_bsp_end_ge_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), index=True
    )
    snapshot_chapter_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshot_chapters.id", ondelete="CASCADE"), index=True
    )
    source_paragraph_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    stable_paragraph_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    paragraph_order: Mapped[int] = mapped_column(Integer, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    snapshot_chapter: Mapped[BookSnapshotChapter] = relationship(back_populates="paragraphs")


class AnalysisRunStage(Base):
    __tablename__ = "analysis_run_stages"
    __table_args__ = (
        UniqueConstraint("run_id", "stage_key", name="uq_analysis_run_stages_run_key"),
        CheckConstraint("stage_order >= 0", name="ck_ars_stage_order_nonneg"),
        CheckConstraint("attempt_count >= 0", name="ck_ars_attempt_count_nonneg"),
        Index("ix_analysis_run_stages_run_order", "run_id", "stage_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    output_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    checkpoint_json: Mapped[str] = mapped_column(Text, default="{}")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


# ---------------------------------------------------------------------------
# Phase 1B-P — Narrative Entity / Asset / Relation skeleton (shared ORM).
# Agents D/E/F must NOT alter these table structures; implement services only.
# ---------------------------------------------------------------------------


class NarrativeEntity(Base):
    """Stable narrative entity identity (not a model interpretation)."""

    __tablename__ = "narrative_entities"
    __table_args__ = (
        Index("ix_narrative_entities_book_type", "book_id", "entity_type"),
        Index("ix_narrative_entities_book_normalized", "book_id", "normalized_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_locked: Mapped[bool] = mapped_column(default=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("narrative_entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    aliases: Mapped[list["NarrativeEntityAlias"]] = relationship(
        back_populates="entity",
        cascade="all, delete-orphan",
    )


class NarrativeEntityAlias(Base):
    __tablename__ = "narrative_entity_aliases"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "normalized_alias",
            name="uq_narrative_entity_aliases_entity_normalized",
        ),
        Index("ix_narrative_entity_aliases_normalized", "normalized_alias"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("narrative_entities.id", ondelete="CASCADE"), index=True
    )
    alias_text: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(500), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False, default="display")
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    is_locked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    entity: Mapped[NarrativeEntity] = relationship(back_populates="aliases")


class NarrativeAsset(Base):
    """Stable narrative asset identity — interpretations live on versions."""

    __tablename__ = "narrative_assets"
    __table_args__ = (
        UniqueConstraint("book_id", "asset_key", name="uq_narrative_assets_book_key"),
        Index("ix_narrative_assets_book_lifecycle", "book_id", "lifecycle_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    asset_key: Mapped[str] = mapped_column(String(128), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_locked: Mapped[bool] = mapped_column(default=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("narrative_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    versions: Mapped[list["NarrativeAssetVersion"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
    )


class NarrativeAssetVersion(Base):
    """One analysis or user-correction interpretation of a stable Asset."""

    __tablename__ = "narrative_asset_versions"
    __table_args__ = (
        Index("ix_narrative_asset_versions_asset_review", "asset_id", "review_status"),
        Index("ix_narrative_asset_versions_snapshot", "book_snapshot_id"),
        # Partial unique: at most one canonical version per asset (SQLite).
        Index(
            "uq_narrative_asset_versions_one_canonical",
            "asset_id",
            unique=True,
            sqlite_where=text("is_canonical = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("narrative_assets.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    book_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    narrative_function: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attributes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False, default="model")
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    is_canonical: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    asset: Mapped[NarrativeAsset] = relationship(back_populates="versions")
    evidence: Mapped[list["NarrativeAssetEvidence"]] = relationship(
        back_populates="asset_version",
        cascade="all, delete-orphan",
    )


class NarrativeAssetEvidence(Base):
    """Evidence bound to an Asset Version + completed Book Snapshot paragraph."""

    __tablename__ = "narrative_asset_evidence"
    __table_args__ = (
        CheckConstraint("start_offset >= 0", name="ck_nae_start_offset_nonneg"),
        CheckConstraint("end_offset >= start_offset", name="ck_nae_end_ge_start"),
        Index("ix_narrative_asset_evidence_version", "asset_version_id"),
        Index("ix_narrative_asset_evidence_snapshot", "book_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_version_id: Mapped[int] = mapped_column(
        ForeignKey("narrative_asset_versions.id", ondelete="CASCADE"), index=True
    )
    book_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), index=True
    )
    snapshot_chapter_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshot_chapters.id", ondelete="CASCADE"), index=True
    )
    snapshot_paragraph_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshot_paragraphs.id", ondelete="CASCADE"), index=True
    )
    source_scene_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    paragraph_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_role: Mapped[str] = mapped_column(String(32), nullable=False, default="support")
    evidence_label: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    asset_version: Mapped[NarrativeAssetVersion] = relationship(back_populates="evidence")


class NarrativeRelation(Base):
    """Stable relation identity between two Assets (endpoints never mutate)."""

    __tablename__ = "narrative_relations"
    __table_args__ = (
        UniqueConstraint("book_id", "relation_key", name="uq_narrative_relations_book_key"),
        Index("ix_narrative_relations_source", "source_asset_id"),
        Index("ix_narrative_relations_target", "target_asset_id"),
        CheckConstraint(
            "source_asset_id != target_asset_id",
            name="ck_narrative_relations_distinct_ends",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    source_asset_id: Mapped[int] = mapped_column(
        ForeignKey("narrative_assets.id", ondelete="CASCADE"), index=True
    )
    target_asset_id: Mapped[int] = mapped_column(
        ForeignKey("narrative_assets.id", ondelete="CASCADE"), index=True
    )
    relation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_locked: Mapped[bool] = mapped_column(default=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_relation_id: Mapped[int | None] = mapped_column(
        ForeignKey("narrative_relations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    versions: Mapped[list["NarrativeRelationVersion"]] = relationship(
        back_populates="relation",
        cascade="all, delete-orphan",
    )


class NarrativeRelationVersion(Base):
    __tablename__ = "narrative_relation_versions"
    __table_args__ = (
        Index("ix_narrative_relation_versions_rel_review", "relation_id", "review_status"),
        Index("ix_narrative_relation_versions_snapshot", "book_snapshot_id"),
        Index(
            "uq_narrative_relation_versions_one_canonical",
            "relation_id",
            unique=True,
            sqlite_where=text("is_canonical = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    relation_id: Mapped[int] = mapped_column(
        ForeignKey("narrative_relations.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    book_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attributes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False, default="model")
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    is_canonical: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    relation: Mapped[NarrativeRelation] = relationship(back_populates="versions")
    evidence: Mapped[list["NarrativeRelationEvidence"]] = relationship(
        back_populates="relation_version",
        cascade="all, delete-orphan",
    )


class NarrativeRelationEvidence(Base):
    __tablename__ = "narrative_relation_evidence"
    __table_args__ = (
        CheckConstraint("start_offset >= 0", name="ck_nre_start_offset_nonneg"),
        CheckConstraint("end_offset >= start_offset", name="ck_nre_end_ge_start"),
        Index("ix_narrative_relation_evidence_version", "relation_version_id"),
        Index("ix_narrative_relation_evidence_snapshot", "book_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    relation_version_id: Mapped[int] = mapped_column(
        ForeignKey("narrative_relation_versions.id", ondelete="CASCADE"), index=True
    )
    book_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), index=True
    )
    snapshot_chapter_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshot_chapters.id", ondelete="CASCADE"), index=True
    )
    snapshot_paragraph_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshot_paragraphs.id", ondelete="CASCADE"), index=True
    )
    source_scene_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    paragraph_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_role: Mapped[str] = mapped_column(String(32), nullable=False, default="support")
    evidence_label: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    relation_version: Mapped[NarrativeRelationVersion] = relationship(back_populates="evidence")


class AnalysisConflict(Base):
    """Persisted analysis conflicts — no auto-adjudication in Phase 1B-P."""

    __tablename__ = "analysis_conflicts"
    __table_args__ = (
        Index("ix_analysis_conflicts_book_status", "book_id", "status"),
        Index("ix_analysis_conflicts_run", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    book_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    conflict_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    left_ref_type: Mapped[str] = mapped_column(String(64), nullable=False)
    left_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    right_ref_type: Mapped[str] = mapped_column(String(64), nullable=False)
    right_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="warning")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", index=True)
    resolution_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


# ---------------------------------------------------------------------------
# STEP 2.1 — Native Whole-Book Overview runtime (minimal additive tables)
# ---------------------------------------------------------------------------


class WholeBookRunWindow(Base):
    """Window execution rows for native Overview production runs."""

    __tablename__ = "whole_book_run_windows"
    __table_args__ = (
        UniqueConstraint("run_id", "window_index", name="uq_wb_run_windows_run_index"),
        UniqueConstraint("run_id", "input_hash", name="uq_wb_run_windows_run_input_hash"),
        CheckConstraint("window_index >= 0", name="ck_wb_run_windows_index_nonneg"),
        CheckConstraint("attempt_count >= 0", name="ck_wb_run_windows_attempt_nonneg"),
        Index("ix_wb_run_windows_run_status", "run_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    window_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_paragraph_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    end_paragraph_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    start_chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    end_chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state_version_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state_version_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_invocations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    token_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class WholeBookRunStateVersion(Base):
    """Recoverable minimal global state after window materialization."""

    __tablename__ = "whole_book_run_state_versions"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "version_number", name="uq_wb_run_state_versions_run_version"
        ),
        CheckConstraint("version_number >= 0", name="ck_wb_run_state_version_nonneg"),
        Index("ix_wb_run_state_versions_run", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    after_window_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source_stage_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
