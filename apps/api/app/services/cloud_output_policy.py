from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ApplicationSetting
from app.schemas.settings import CloudBudgetUpdate


class CloudOutputLimitTooLow(ValueError):
    error_code = "CLOUD_OUTPUT_LIMIT_TOO_LOW"


@dataclass(frozen=True)
class OutputLimitDecision:
    task_type: str
    configured_limit: int
    user_hard_limit: int
    effective_limit: int
    provider_parameter_name: str = "max_tokens"


def _configured_limit(task_type: str, invocation_kind: str) -> int:
    settings = get_settings()
    journey_task = task_type.startswith("reader_journey")
    if journey_task:
        if invocation_kind == "json_repair":
            return settings.cloud_output_reader_journey_json_repair
        if invocation_kind == "schema_repair":
            return settings.cloud_output_reader_journey_schema_repair
        if invocation_kind == "evidence_repair":
            return settings.cloud_output_reader_journey_evidence_repair
        if invocation_kind in {
            "business_repair",
            "structural_repair",
            "repair_provider_retry",
        }:
            return settings.cloud_output_reader_journey_business_repair
        if task_type == "reader_journey_chapter":
            return settings.cloud_output_reader_journey_chapter
        return settings.cloud_output_reader_journey_scene
    if invocation_kind in {"json_repair", "schema_repair"}:
        return settings.cloud_output_json_schema_repair
    if invocation_kind in {
        "business_repair",
        "evidence_repair",
        "structural_repair",
        "repair_provider_retry",
    }:
        return settings.cloud_output_business_repair
    limits = {
        "connection_test": settings.cloud_output_connection_test,
        "minimal_json_test": settings.cloud_output_minimal_json_test,
        "scene_boundary": settings.cloud_output_scene_boundary,
        "scene_boundary_adjudication": settings.cloud_output_scene_boundary,
        "full_run_boundary": settings.cloud_output_full_run_boundary,
        "scene_analysis": settings.cloud_output_scene_analysis,
        "full_run_scene_analysis": settings.cloud_output_full_run_scene_analysis,
        "reader_journey_scene": settings.cloud_output_reader_journey_scene,
        "reader_journey_chapter": settings.cloud_output_reader_journey_chapter,
        "reader_journey_json_repair": settings.cloud_output_reader_journey_json_repair,
        "reader_journey_schema_repair": settings.cloud_output_reader_journey_schema_repair,
        "reader_journey_evidence_repair": settings.cloud_output_reader_journey_evidence_repair,
        "reader_journey_business_repair": settings.cloud_output_reader_journey_business_repair,
    }
    return limits.get(task_type, settings.cloud_output_scene_analysis)


def resolve_output_limit(
    session: Session,
    *,
    task_type: str,
    invocation_kind: str,
    cloud: bool,
) -> OutputLimitDecision:
    configured = _configured_limit(task_type, invocation_kind)
    if not cloud:
        local_limit = get_settings().local_llama_max_output_tokens
        return OutputLimitDecision(task_type, local_limit, local_limit, local_limit)
    # Keep the analysis transaction from holding a SQLite read lock while the
    # request gate writes its audit decision in a separate session.
    with Session(session.get_bind()) as settings_session:
        row = settings_session.get(ApplicationSetting, "cloud_budget_settings")
        budget = CloudBudgetUpdate.model_validate_json(row.value_json if row else "{}")
    hard_limit = budget.cloud_max_output_tokens_per_request
    if hard_limit < configured:
        raise CloudOutputLimitTooLow(
            f"CLOUD_OUTPUT_LIMIT_TOO_LOW: {task_type} requires {configured}, hard limit is {hard_limit}"
        )
    return OutputLimitDecision(task_type, configured, hard_limit, configured)
