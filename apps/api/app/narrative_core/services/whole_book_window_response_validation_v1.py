"""Public secondary validation for window analysis responses (Wave C)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import BookSnapshot, WholeBookRun, WholeBookWindow
from app.narrative_core.contracts.whole_book_contract_v1 import (
    WHOLE_BOOK_CONTRACT_VERSION,
    EntityType,
    ResultOrigin,
    SnapshotParagraphV1,
    WholeBookWindowAnalysisResponseV1,
)
from app.narrative_core.contracts.whole_book_contract_v1.common import sha256_hex
from app.narrative_core.contracts.whole_book_contract_v1.validators import (
    validate_evidence_locator,
    validate_window_analysis_response_v1,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import MINIMAL_ASSET_TYPES, MINIMAL_RELATION_TYPES


class WindowResponseValidationResult:
    def __init__(self, *, valid: bool, warnings: list[str], errors: list[str]) -> None:
        self.valid = valid
        self.warnings = warnings
        self.errors = errors


def validate_window_response_against_snapshot_v1(
    session: Session,
    run: WholeBookRun,
    snapshot: BookSnapshot,
    window: WholeBookWindow,
    paragraphs: list[SnapshotParagraphV1],
    response: WholeBookWindowAnalysisResponseV1,
) -> WindowResponseValidationResult:
    """Strict Public validation; invalid → whole response invalid."""
    warnings: list[str] = []
    errors: list[str] = []

    try:
        validate_window_analysis_response_v1(response)
    except ValueError as exc:
        errors.append(str(exc))
        return WindowResponseValidationResult(valid=False, warnings=warnings, errors=errors)

    if response.run_id != run.id:
        errors.append("run_id mismatch")
    if response.snapshot_id != snapshot.id:
        errors.append("snapshot_id mismatch")
    if response.window_id != window.id:
        errors.append("window_id mismatch")
    if response.contract_version != WHOLE_BOOK_CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    if response.provenance.result_origin == ResultOrigin.formal and run.result_origin != ResultOrigin.formal.value:
        errors.append("result_origin formal impersonation")
    if response.provenance.result_origin == ResultOrigin.formal:
        errors.append("fixture pipeline forbids formal provenance")

    para_by_id = {p.snapshot_paragraph_id: p for p in paragraphs}
    global_set = {p.global_paragraph_index for p in paragraphs}
    if paragraphs:
        if paragraphs[0].global_paragraph_index != window.first_global_paragraph_index:
            errors.append("paragraph window start mismatch")
        if paragraphs[-1].global_paragraph_index != window.last_global_paragraph_index:
            errors.append("paragraph window end mismatch")

    for entity in response.entities:
        if entity.entity_type != EntityType.character:
            warnings.append("unsupported_entity_type_in_minimal_pipeline")
            errors.append(f"unsupported entity_type: {entity.entity_type}")

    for asset in response.assets:
        if asset.asset_type not in MINIMAL_ASSET_TYPES:
            warnings.append(f"unsupported_asset_type:{asset.asset_type}")
            errors.append(f"unsupported asset_type: {asset.asset_type}")

    for relation in response.relations:
        if relation.relation_type not in MINIMAL_RELATION_TYPES:
            warnings.append(f"unsupported_relation_type:{relation.relation_type}")
            errors.append(f"unsupported relation_type: {relation.relation_type}")

    for evidence in response.evidences:
        locator = evidence.locator
        if locator.snapshot_id != snapshot.id:
            errors.append(f"evidence {evidence.evidence_key} snapshot_id mismatch")
            continue
        if locator.global_paragraph_index not in global_set:
            errors.append(f"evidence {evidence.evidence_key} paragraph outside window")
            continue
        paragraph = para_by_id.get(locator.snapshot_paragraph_id)
        if paragraph is None:
            errors.append(f"evidence {evidence.evidence_key} paragraph not found")
            continue
        if paragraph.text_hash != locator.paragraph_text_hash:
            errors.append(f"evidence {evidence.evidence_key} paragraph hash mismatch")
            continue
        if locator.start_offset < 0 or locator.end_offset > len(paragraph.text):
            errors.append(f"evidence {evidence.evidence_key} offset out of range")
            continue
        slice_text = paragraph.text[locator.start_offset : locator.end_offset]
        if slice_text != locator.quote_text:
            errors.append(f"evidence {evidence.evidence_key} quote offset mismatch")
        if sha256_hex(locator.quote_text) != locator.quote_hash:
            errors.append(f"evidence {evidence.evidence_key} quote_hash mismatch")
        state = validate_evidence_locator(locator, paragraph.text)
        if state.value != "valid":
            errors.append(f"evidence {evidence.evidence_key} locator state={state.value}")

    valid = not errors
    return WindowResponseValidationResult(valid=valid, warnings=warnings, errors=errors)
